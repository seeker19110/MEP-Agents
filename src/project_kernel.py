"""Project Kernel — canonical project state cho Engineering OS.

Đặc tả đầy đủ: [`docs/DAC_TA_PROJECT_KERNEL.md`](../docs/DAC_TA_PROJECT_KERNEL.md). Đây là
bước 1 ("schema + module trơn") trong kế hoạch triển khai ở đặc tả đó (mục 11): module
đứng **độc lập**, không có tool nào gọi vào, không có route API — đúng bài học "ghép sai
khi chạy chung" từ PR #32 (`progress.md` mục 3.4–3.5). Nối vào hệ thống là việc của lượt
sau. Mục 13 của đặc tả (4 câu hỏi nghiệp vụ) đã được quyết — xem "Bốn quyết định" bên dưới.

## Ba quyết định thiết kế nền, và lý do

**1. SQLite mặc định, Postgres khi có `DATABASE_URL` thật — đúng khuôn
`checkpointer_factory.py`.** Không có `DATABASE_URL` (dev cục bộ, mặc định) → SQLite riêng
file (`project_kernel.sqlite`), qua `sqlite3` thư viện chuẩn, không thêm phụ thuộc — cùng
lựa chọn và lý do đã ghi ở `src/users.py`. Có `DATABASE_URL` **và** đã cài `psycopg`
(`uv sync --extra phase-c`) → dùng Postgres thật. Khác với lúc viết đặc tả (khi đó "chưa có
instance Postgres thật để chạy thử" là lý do hoãn — `TECH_DEBT.md` mục 1), việc thêm nhánh
Postgres ở đây **đã chạy thử thật** trên một instance Postgres 16 cục bộ (xem
`tests/test_project_kernel.py::TestPostgresBackend`, bỏ qua tự động nếu không có
`TEST_DATABASE_URL`) — không còn là đoán mò. Toàn bộ câu lệnh SQL viết bằng placeholder `?`
dùng chung, dịch sang `%s` cho Postgres ở đúng một chỗ (`_exec`) — không viết SQL hai lần.

**2. `object_id` (và `project_id`/`revision_id`/`source_id`) là ID nội bộ bất biến, tách
khỏi `tag` (nhãn nghiệp vụ có thể đổi).** Sinh bằng `uuid.uuid4().hex`, không bao giờ tái
sử dụng, không được parse để suy luận gì ngoài mục đích đọc log bằng mắt.

**3. Chuyển trạng thái đối tượng được canh ở một chỗ duy nhất** (`update_object_status`),
không để tầng gọi tự `UPDATE status`. `ALLOWED_TRANSITIONS` bên dưới là nguồn duy nhất cho
luật này.

## Bốn quyết định trả lời mục 13 của đặc tả

**1. Schema `properties` theo discipline:** KHÔNG hardcode trường bắt buộc cho từng loại
thiết bị trong module này — không ai duyệt danh sách đó, đoán là sai văn hóa dự án. Thay
vào đó có `register_property_schema(type_, required_fields)`, một điểm mở rộng cùng khuôn
`standards_backend.register_backend`: discipline module nào cần ép trường bắt buộc cho
`type` của mình thì tự đăng ký; `type` chưa đăng ký chỉ cần `properties` là JSON hợp lệ,
đúng hành vi mặc định ban đầu.

**2. Quan hệ với revision file CAD (`cad_revision.py`):** GIỮ TÁCH BIỆT, không tự động hóa
ở lượt này. Revision dự án (bảng `revisions`) là mốc canonical cấp dự án, tạo tường minh
qua `create_revision`; revision file CAD là lịch sử chỉnh sửa cấp file, không đổi. Bước 2
(nối vào tool) sẽ KHÔNG tự tạo revision dự án mỗi khi `snapshot_cad` chạy — ngưỡng "khi nào
chốt một revision dự án" vẫn là quyết định của người gọi (tool/route), không suy luận ngầm
trong Project Kernel.

**3. Mô hình quyền truy cập dự án:** bảng `project_members` (project_id, username, role)
với 3 vai trò dùng chung ngữ nghĩa `src/users.py::ROLES` (viewer/engineer/admin) nhưng
**phạm vi riêng từng dự án** — vai trò hệ thống của một người (từ `users.py`) và vai trò
của họ trong một dự án cụ thể là hai khái niệm độc lập. `create_project` tự thêm owner làm
thành viên `admin` đầu tiên.

**4. Ngưỡng `confidence`:** `PROJECT_KERNEL_AUTO_ACTIVATE_CONFIDENCE` (mặc định 0.8, đọc
qua `config.py`, cùng khuôn `OCR_MIN_CONFIDENCE`). `try_auto_activate()` tự chuyển
`validated` → `active` nếu `confidence` đạt ngưỡng; dưới ngưỡng thì giữ nguyên `validated`,
chờ người duyệt tay qua `update_object_status`. Đây là ngưỡng MẶC ĐỊNH kỹ thuật, không thay
thế việc người có kinh nghiệm QS/thiết kế hiệu chỉnh lại bằng số liệu thật — đúng tinh thần
`OCR_MIN_CONFIDENCE` đã cần đo bằng hồ sơ scan thật (`TECH_DEBT.md` mục 13).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()

#: Loại nguồn hợp lệ cho bảng `sources` — khớp mục 6.3 của đặc tả.
SOURCE_KINDS = ("dwg", "dxf", "ifc", "pdf", "xlsx", "spec", "standard")

#: Từ điển quan hệ hợp lệ cho `object_relations` — khớp nguyên văn `progress.md` mục 9.1.
RELATION_TYPES = (
    "contains", "located_in", "serves", "connects_to", "powered_by", "supplied_by",
    "drains_to", "controls", "depends_on", "feeds", "returns_to", "intersects", "near",
    "clearance_to", "replaces", "derived_from", "belongs_to_system",
)

#: Vai trò trong PHẠM VI MỘT DỰ ÁN — cùng tên/ngữ nghĩa với `users.ROLES` nhưng độc lập:
#: một người có thể là 'viewer' hệ thống mà vẫn là 'admin' của riêng dự án họ tạo.
PROJECT_ROLES = ("viewer", "engineer", "admin")

#: Vòng đời đối tượng — khớp mục 8 của đặc tả. Chỉ cho đi tới trong chuỗi
#: discovered → normalized → validated → active → modified → superseded → archived,
#: cộng thêm vòng lặp active ↔ modified. Không cho nhảy lùi tùy ý (VD archived → active
#: phải qua thao tác phục hồi tường minh của lượt sau, chưa có ở đây).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "discovered": {"normalized"},
    "normalized": {"validated"},
    "validated": {"active"},
    "active": {"modified", "superseded"},
    "modified": {"active", "superseded"},
    "superseded": {"archived"},
    "archived": set(),
}

#: Registry mở của `type` -> trường bắt buộc trong `properties` (quyết định #1 ở trên).
#: KHÔNG có mục nào được nạp sẵn — mỗi discipline module tự đăng ký lấy khi cần.
_PROPERTY_SCHEMAS: dict[str, tuple[str, ...]] = {}


# --- Backend: SQLite (mặc định) hoặc Postgres (khi có DATABASE_URL + đã cài psycopg) ---

def db_path() -> str:
    """Đường dẫn file CSDL SQLite. Đọc mỗi lần gọi để test đổi được bằng biến môi trường.
    Không dùng khi backend là Postgres."""
    from src.workspace import get_project_root

    configured = os.environ.get("PROJECT_KERNEL_DB_PATH", "").strip()
    if configured:
        return configured
    return os.path.join(get_project_root(), "data", "project_kernel.sqlite")


def _database_url() -> str:
    configured = os.environ.get("DATABASE_URL", "").strip()
    if configured:
        return configured
    try:
        from src.config import settings
        return (settings.database_url or "").strip()
    except Exception:
        return ""


def _use_postgres() -> bool:
    """Đọc lại mỗi lần gọi (không cache) — cùng lý do `db_path()` đọc lại mỗi lần: test
    phải đổi được backend bằng biến môi trường mà không cần khởi động lại tiến trình."""
    if os.environ.get("PROJECT_KERNEL_BACKEND", "").strip().lower() == "sqlite":
        return False
    if not _database_url():
        return False
    try:
        import psycopg  # noqa: F401
    except ImportError:
        logger.info(
            "DATABASE_URL có cấu hình nhưng chưa cài psycopg (uv sync --extra phase-c) — "
            "Project Kernel dùng SQLite."
        )
        return False
    return True


def _connect():
    """Trả về `sqlite3.Connection` hoặc `psycopg.Connection` tùy `_use_postgres()`. Cả hai
    đều hỗ trợ `with _connect() as conn:` (commit khi thành công, rollback khi lỗi) và
    `conn.execute(sql, params).fetchone()/.fetchall()` — đủ cho toàn bộ module này không
    cần phân nhánh gì thêm ngoài `_exec()`."""
    if _use_postgres():
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(_database_url(), row_factory=dict_row)

    path = db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _is_postgres_conn(conn) -> bool:
    return conn.__class__.__module__.startswith("psycopg")


def _is_unique_violation(conn, exc: Exception) -> bool:
    """`True` nếu `exc` là lỗi va chạm khóa duy nhất/khóa chính — tên lớp khác nhau giữa
    hai thư viện (`sqlite3.IntegrityError` vs `psycopg.errors.UniqueViolation`)."""
    if _is_postgres_conn(conn):
        import psycopg
        return isinstance(exc, psycopg.errors.UniqueViolation)
    return isinstance(exc, sqlite3.IntegrityError)


def _exec(conn, sql: str, params: tuple = ()):
    """Điểm duy nhất dịch placeholder `?` (quy ước chung của module) sang `%s` khi backend
    là Postgres. Viết SQL một lần, không nhân đôi theo dialect."""
    if _is_postgres_conn(conn):
        sql = sql.replace("?", "%s")
    return conn.execute(sql, params)


def _insert_ignore(conn, table: str, columns: tuple[str, ...]) -> str:
    """SQL "chèn, bỏ qua nếu trùng khóa" — `INSERT OR IGNORE` (SQLite) hay
    `INSERT ... ON CONFLICT DO NOTHING` (Postgres) tùy backend đang dùng."""
    cols = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    if _is_postgres_conn(conn):
        placeholders = placeholders.replace("?", "%s")
        return f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    return f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})"


#: DDL viết chung cho cả hai backend — không dùng `AUTOINCREMENT`/`SERIAL` (mọi khóa chính
#: đều là TEXT sinh bằng uuid4) nên không cần cú pháp riêng theo dialect. `executescript`
#: (chỉ SQLite có) tránh dùng — chạy từng câu một để giống nhau trên cả hai backend.
_DDL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS projects (
        project_id TEXT PRIMARY KEY,
        name       TEXT NOT NULL,
        owner      TEXT NOT NULL,
        status     TEXT NOT NULL DEFAULT 'active',
        created_at INTEGER NOT NULL,
        metadata   TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS revisions (
        revision_id        TEXT PRIMARY KEY,
        project_id         TEXT NOT NULL,
        parent_revision_id TEXT,
        note               TEXT,
        created_by         TEXT NOT NULL,
        created_at         INTEGER NOT NULL,
        status             TEXT NOT NULL DEFAULT 'draft'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_revisions_project ON revisions(project_id)",
    """CREATE TABLE IF NOT EXISTS sources (
        source_id    TEXT PRIMARY KEY,
        project_id   TEXT NOT NULL,
        kind         TEXT NOT NULL,
        storage_key  TEXT NOT NULL,
        checksum     TEXT,
        uploaded_by  TEXT NOT NULL,
        uploaded_at  INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sources_project ON sources(project_id)",
    """CREATE TABLE IF NOT EXISTS engineering_objects (
        object_id    TEXT PRIMARY KEY,
        project_id   TEXT NOT NULL,
        revision_id  TEXT NOT NULL,
        tag          TEXT,
        type         TEXT NOT NULL,
        discipline   TEXT NOT NULL,
        parent_id    TEXT,
        properties   TEXT,
        status       TEXT NOT NULL DEFAULT 'discovered',
        confidence   REAL NOT NULL DEFAULT 1.0,
        created_at   INTEGER NOT NULL,
        updated_at   INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_objects_project_revision"
    " ON engineering_objects(project_id, revision_id)",
    "CREATE INDEX IF NOT EXISTS idx_objects_project_type"
    " ON engineering_objects(project_id, type)",
    "CREATE INDEX IF NOT EXISTS idx_objects_parent ON engineering_objects(parent_id)",
    """CREATE TABLE IF NOT EXISTS object_source_refs (
        object_id    TEXT NOT NULL,
        source_id    TEXT NOT NULL,
        locator      TEXT NOT NULL DEFAULT '',
        extracted_at INTEGER NOT NULL,
        PRIMARY KEY (object_id, source_id, locator)
    )""",
    """CREATE TABLE IF NOT EXISTS object_relations (
        from_id       TEXT NOT NULL,
        to_id         TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        project_id    TEXT NOT NULL,
        revision_id   TEXT NOT NULL,
        created_at    INTEGER NOT NULL,
        PRIMARY KEY (from_id, to_id, relation_type, revision_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_relations_project ON object_relations(project_id)",
    """CREATE TABLE IF NOT EXISTS project_members (
        project_id TEXT NOT NULL,
        username   TEXT NOT NULL,
        role       TEXT NOT NULL DEFAULT 'engineer',
        added_at   INTEGER NOT NULL,
        PRIMARY KEY (project_id, username)
    )""",
]


def init_db() -> None:
    """Tạo bảng/index nếu chưa có. Gọi được nhiều lần, không gây hại."""
    with _LOCK, _connect() as conn:
        for stmt in _DDL_STATEMENTS:
            conn.execute(stmt)


def _new_id(prefix: str) -> str:
    """`{prefix}:{uuid4_hex}` — bất biến, không được parse để suy luận gì (mục 7 đặc tả)."""
    import re

    clean = re.sub(r"[^a-z0-9_]+", "_", (prefix or "obj").strip().lower()).strip("_") or "obj"
    return f"{clean}:{uuid.uuid4().hex}"


def _now() -> int:
    return int(time.time())


def _row(row) -> dict | None:
    return dict(row) if row is not None else None


# --- Registry schema properties (quyết định #1) ---

def register_property_schema(type_: str, required_fields: list[str] | tuple[str, ...]) -> None:
    """Đăng ký trường bắt buộc trong `properties` cho một `type` cụ thể. Điểm mở rộng mở —
    KHÔNG hardcode schema domain-specific trong module này (xem quyết định #1 ở đầu file).
    Gọi lại với cùng `type_` sẽ THAY THẾ danh sách cũ, không cộng dồn."""
    key = (type_ or "").strip().lower()
    if not key:
        raise ValueError("type để đăng ký schema không được rỗng.")
    _PROPERTY_SCHEMAS[key] = tuple(required_fields or ())


def get_property_schema(type_: str) -> tuple[str, ...]:
    return _PROPERTY_SCHEMAS.get((type_ or "").strip().lower(), ())


def reset_property_schemas_for_tests() -> None:
    _PROPERTY_SCHEMAS.clear()


# --- Project ---

def create_project(name: str, owner: str, metadata: dict | None = None) -> dict:
    name = (name or "").strip()
    owner = (owner or "").strip()
    if not name:
        raise ValueError("Tên dự án không được rỗng.")
    if not owner:
        raise ValueError("Dự án phải có chủ sở hữu (owner).")

    init_db()
    project_id = _new_id("project")
    created_at = _now()
    with _LOCK, _connect() as conn:
        _exec(
            conn,
            "INSERT INTO projects (project_id, name, owner, status, created_at, metadata)"
            " VALUES (?, ?, ?, 'active', ?, ?)",
            (project_id, name, owner, created_at, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        # Owner là thành viên admin đầu tiên — quyết định #3 (mục 13 đặc tả).
        _exec(conn, _insert_ignore(conn, "project_members", ("project_id", "username", "role", "added_at")),
              (project_id, owner, "admin", created_at))
    logger.info("Đã tạo dự án '%s' (%s), owner=%s", name, project_id, owner)
    return {"project_id": project_id, "name": name, "owner": owner, "status": "active",
            "created_at": created_at, "metadata": metadata or {}}


def get_project(project_id: str) -> dict | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = _exec(
            conn,
            "SELECT project_id, name, owner, status, created_at, metadata FROM projects"
            " WHERE project_id = ?", (project_id,),
        ).fetchone()
    result = _row(row)
    if result is not None:
        result["metadata"] = json.loads(result["metadata"] or "{}")
    return result


def list_projects(owner: str) -> list[dict]:
    init_db()
    with _LOCK, _connect() as conn:
        rows = _exec(
            conn,
            "SELECT project_id, name, owner, status, created_at, metadata FROM projects"
            " WHERE owner = ? ORDER BY created_at DESC", ((owner or "").strip(),),
        ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["metadata"] = json.loads(d["metadata"] or "{}")
        out.append(d)
    return out


# --- Thành viên dự án (quyết định #3) ---

def add_project_member(project_id: str, username: str, role: str = "engineer") -> dict:
    if get_project(project_id) is None:
        raise ValueError(f"Dự án '{project_id}' không tồn tại.")
    username = (username or "").strip()
    if not username:
        raise ValueError("Tên thành viên không được rỗng.")
    role = (role or "").strip().lower()
    if role not in PROJECT_ROLES:
        raise ValueError(f"Vai trò không hợp lệ: '{role}'. Chọn một trong {PROJECT_ROLES}.")

    init_db()
    added_at = _now()
    with _LOCK, _connect() as conn:
        # Thêm mới hoặc đổi vai trò nếu đã là thành viên — không dùng INSERT OR IGNORE ở
        # đây vì mục đích khác nhau: source (mục 6.3) không BAO GIỜ được ghi đè, còn vai
        # trò thành viên thì được phép cập nhật (thăng/hạ quyền là thao tác hợp lệ). Cú
        # pháp "ON CONFLICT ... DO UPDATE ... excluded.<cột>" giống hệt nhau ở cả hai
        # backend (định danh không phân biệt hoa/thường khi không đặt trong dấu ngoặc kép),
        # nên không cần phân nhánh theo dialect như `_insert_ignore`.
        _exec(conn,
              "INSERT INTO project_members (project_id, username, role, added_at)"
              " VALUES (?, ?, ?, ?)"
              " ON CONFLICT (project_id, username) DO UPDATE SET role = excluded.role",
              (project_id, username, role, added_at))
    logger.info("Dự án %s: thành viên %s -> vai trò %s", project_id, username, role)
    return {"project_id": project_id, "username": username, "role": role, "added_at": added_at}


def remove_project_member(project_id: str, username: str) -> None:
    init_db()
    with _LOCK, _connect() as conn:
        _exec(conn, "DELETE FROM project_members WHERE project_id = ? AND username = ?",
              (project_id, (username or "").strip()))


def list_project_members(project_id: str) -> list[dict]:
    init_db()
    with _LOCK, _connect() as conn:
        rows = _exec(
            conn,
            "SELECT project_id, username, role, added_at FROM project_members"
            " WHERE project_id = ? ORDER BY added_at", (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_member_role(project_id: str, username: str) -> str | None:
    """`None` nếu không phải thành viên dự án này."""
    init_db()
    with _LOCK, _connect() as conn:
        row = _exec(
            conn,
            "SELECT role FROM project_members WHERE project_id = ? AND username = ?",
            (project_id, (username or "").strip()),
        ).fetchone()
    return dict(row)["role"] if row is not None else None


# --- Revision ---

def create_revision(project_id: str, created_by: str, note: str = "",
                     parent_revision_id: str | None = None) -> dict:
    if get_project(project_id) is None:
        raise ValueError(f"Dự án '{project_id}' không tồn tại.")
    created_by = (created_by or "").strip()
    if not created_by:
        raise ValueError("Revision phải ghi rõ người tạo (created_by).")
    if parent_revision_id is not None and get_revision(parent_revision_id) is None:
        raise ValueError(f"Revision cha '{parent_revision_id}' không tồn tại.")

    init_db()
    revision_id = _new_id("revision")
    created_at = _now()
    with _LOCK, _connect() as conn:
        _exec(
            conn,
            "INSERT INTO revisions (revision_id, project_id, parent_revision_id, note,"
            " created_by, created_at, status) VALUES (?, ?, ?, ?, ?, ?, 'draft')",
            (revision_id, project_id, parent_revision_id, note, created_by, created_at),
        )
    logger.info("Đã tạo revision %s cho dự án %s", revision_id, project_id)
    return {"revision_id": revision_id, "project_id": project_id,
            "parent_revision_id": parent_revision_id, "note": note,
            "created_by": created_by, "created_at": created_at, "status": "draft"}


def get_revision(revision_id: str) -> dict | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = _exec(
            conn,
            "SELECT revision_id, project_id, parent_revision_id, note, created_by,"
            " created_at, status FROM revisions WHERE revision_id = ?", (revision_id,),
        ).fetchone()
    return _row(row)


def activate_revision(revision_id: str) -> None:
    """Đặt một revision thành `active`; revision `active` trước đó (nếu có) của cùng dự
    án chuyển sang `superseded`. Đúng ràng buộc mục 6.2 của đặc tả: mỗi dự án chỉ có đúng
    một revision `active` tại một thời điểm."""
    revision = get_revision(revision_id)
    if revision is None:
        raise ValueError(f"Revision '{revision_id}' không tồn tại.")

    with _LOCK, _connect() as conn:
        _exec(
            conn,
            "UPDATE revisions SET status = 'superseded'"
            " WHERE project_id = ? AND status = 'active' AND revision_id != ?",
            (revision["project_id"], revision_id),
        )
        _exec(conn, "UPDATE revisions SET status = 'active' WHERE revision_id = ?", (revision_id,))
    logger.info("Revision %s là active cho dự án %s", revision_id, revision["project_id"])


def get_active_revision(project_id: str) -> dict | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = _exec(
            conn,
            "SELECT revision_id, project_id, parent_revision_id, note, created_by,"
            " created_at, status FROM revisions WHERE project_id = ? AND status = 'active'",
            (project_id,),
        ).fetchone()
    return _row(row)


# --- Source ---

def register_source(project_id: str, kind: str, storage_key: str, uploaded_by: str,
                     checksum: str = "") -> dict:
    """Ghi nhận một file gốc. Không có hàm cập nhật/ghi đè — một file sửa lại phải đăng ký
    thành `source_id` mới, đúng nguyên tắc "không được ghi đè source" (`progress.md` mục 8).
    """
    if get_project(project_id) is None:
        raise ValueError(f"Dự án '{project_id}' không tồn tại.")
    kind = (kind or "").strip().lower()
    if kind not in SOURCE_KINDS:
        raise ValueError(f"Loại nguồn không hợp lệ: '{kind}'. Chọn một trong {SOURCE_KINDS}.")
    storage_key = (storage_key or "").strip()
    if not storage_key:
        raise ValueError("Nguồn phải có storage_key (key trong src/storage.py).")
    uploaded_by = (uploaded_by or "").strip()
    if not uploaded_by:
        raise ValueError("Nguồn phải ghi rõ người tải lên (uploaded_by).")

    init_db()
    source_id = _new_id("source")
    uploaded_at = _now()
    with _LOCK, _connect() as conn:
        try:
            _exec(
                conn,
                "INSERT INTO sources (source_id, project_id, kind, storage_key, checksum,"
                " uploaded_by, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (source_id, project_id, kind, storage_key, checksum, uploaded_by, uploaded_at),
            )
        except Exception as e:
            # Về lý thuyết không xảy ra (source_id sinh mới mỗi lần bằng uuid4), nhưng nếu
            # có va chạm thì phải NGĂN, không được lặng lẽ UPDATE — đúng nguyên tắc "không
            # được ghi đè source" (`progress.md` mục 8). Bắt `Exception` rộng vì lỗi ràng
            # buộc của psycopg (`errors.UniqueViolation`) không kế thừa từ
            # `sqlite3.IntegrityError`; an toàn ở đây vì insert này không có hiệu ứng phụ
            # nào khác để lỡ nuốt nhầm lỗi — mọi lỗi không phải va chạm khóa đều bị ném lại.
            if not _is_unique_violation(conn, e):
                raise
            raise ValueError(f"Nguồn '{source_id}' đã tồn tại, không thể ghi đè: {e}") from e
    logger.info("Đã đăng ký nguồn %s (%s) cho dự án %s", source_id, kind, project_id)
    return {"source_id": source_id, "project_id": project_id, "kind": kind,
            "storage_key": storage_key, "checksum": checksum, "uploaded_by": uploaded_by,
            "uploaded_at": uploaded_at}


def get_source(source_id: str) -> dict | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = _exec(
            conn,
            "SELECT source_id, project_id, kind, storage_key, checksum, uploaded_by,"
            " uploaded_at FROM sources WHERE source_id = ?", (source_id,),
        ).fetchone()
    return _row(row)


# --- Object ---

def register_object(project_id: str, revision_id: str, type: str, discipline: str,
                     tag: str = "", parent_id: str | None = None,
                     properties: dict | None = None, confidence: float = 1.0) -> dict:
    if get_project(project_id) is None:
        raise ValueError(f"Dự án '{project_id}' không tồn tại.")
    if get_revision(revision_id) is None:
        raise ValueError(f"Revision '{revision_id}' không tồn tại.")
    type = (type or "").strip()
    if not type:
        raise ValueError("Đối tượng phải có 'type' (không rỗng).")
    discipline = (discipline or "").strip()
    if not discipline:
        raise ValueError("Đối tượng phải có 'discipline' (không rỗng).")
    if parent_id is not None and get_object(parent_id) is None:
        raise ValueError(f"Đối tượng cha '{parent_id}' không tồn tại.")
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence phải trong khoảng 0.0–1.0, nhận {confidence}.")
    properties = properties or {}
    required = get_property_schema(type)
    if required:
        missing = [f for f in required if f not in properties]
        if missing:
            raise ValueError(
                f"Đối tượng type='{type}' thiếu trường bắt buộc trong properties: {missing}"
                f" (đăng ký qua register_property_schema)."
            )
    try:
        properties_json = json.dumps(properties, ensure_ascii=False)
    except TypeError as e:
        raise ValueError(f"properties phải là JSON hợp lệ: {e}") from e

    init_db()
    object_id = _new_id(type)
    now = _now()
    with _LOCK, _connect() as conn:
        _exec(
            conn,
            "INSERT INTO engineering_objects (object_id, project_id, revision_id, tag,"
            " type, discipline, parent_id, properties, status, confidence, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'discovered', ?, ?, ?)",
            (object_id, project_id, revision_id, tag, type, discipline, parent_id,
             properties_json, confidence, now, now),
        )
    logger.info("Đã đăng ký đối tượng %s (type=%s, discipline=%s) cho dự án %s",
                object_id, type, discipline, project_id)
    return {"object_id": object_id, "project_id": project_id, "revision_id": revision_id,
            "tag": tag, "type": type, "discipline": discipline, "parent_id": parent_id,
            "properties": properties, "status": "discovered",
            "confidence": confidence, "created_at": now, "updated_at": now}


def _object_row_to_dict(row) -> dict:
    d = dict(row)
    d["properties"] = json.loads(d["properties"] or "{}")
    return d


def get_object(object_id: str) -> dict | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = _exec(conn, "SELECT * FROM engineering_objects WHERE object_id = ?",
                     (object_id,)).fetchone()
    return _object_row_to_dict(row) if row is not None else None


def list_objects(project_id: str, revision_id: str | None = None, type: str | None = None,
                  discipline: str | None = None) -> list[dict]:
    init_db()
    query = "SELECT * FROM engineering_objects WHERE project_id = ?"
    params: list = [project_id]
    if revision_id is not None:
        query += " AND revision_id = ?"
        params.append(revision_id)
    if type is not None:
        query += " AND type = ?"
        params.append(type)
    if discipline is not None:
        query += " AND discipline = ?"
        params.append(discipline)
    query += " ORDER BY created_at"
    with _LOCK, _connect() as conn:
        rows = _exec(conn, query, tuple(params)).fetchall()
    return [_object_row_to_dict(r) for r in rows]


def update_object_status(object_id: str, new_status: str) -> None:
    """Chuyển trạng thái đối tượng theo `ALLOWED_TRANSITIONS`. Ném `ValueError` nếu bước
    chuyển không hợp lệ — xem bảng vòng đời ở mục 8 của đặc tả."""
    obj = get_object(object_id)
    if obj is None:
        raise ValueError(f"Đối tượng '{object_id}' không tồn tại.")
    current = obj["status"]
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise ValueError(
            f"Không thể chuyển đối tượng '{object_id}' từ trạng thái '{current}' sang"
            f" '{new_status}'. Cho phép: {sorted(allowed) or '(không — trạng thái cuối)'}."
        )
    with _LOCK, _connect() as conn:
        _exec(conn, "UPDATE engineering_objects SET status = ?, updated_at = ? WHERE object_id = ?",
              (new_status, _now(), object_id))
    logger.info("Đối tượng %s: %s -> %s", object_id, current, new_status)


def try_auto_activate(object_id: str) -> bool:
    """Tự động chuyển `validated` -> `active` nếu `confidence` đạt ngưỡng cấu hình
    (quyết định #4, mục 13 đặc tả). Trả `False` (không đổi gì) nếu đối tượng chưa ở
    `validated` hoặc chưa đủ tin cậy — vẫn phải chờ người duyệt tay qua
    `update_object_status`. KHÔNG áp dụng cho các bước chuyển khác."""
    obj = get_object(object_id)
    if obj is None:
        raise ValueError(f"Đối tượng '{object_id}' không tồn tại.")
    if obj["status"] != "validated":
        return False
    try:
        from src.config import settings
        threshold = float(getattr(settings, "project_kernel_auto_activate_confidence", 0.8))
    except Exception:
        threshold = 0.8
    if obj["confidence"] < threshold:
        return False
    update_object_status(object_id, "active")
    return True


# --- Source ref & relation ---

def attach_source_ref(object_id: str, source_id: str, locator: str = "") -> None:
    if get_object(object_id) is None:
        raise ValueError(f"Đối tượng '{object_id}' không tồn tại.")
    if get_source(source_id) is None:
        raise ValueError(f"Nguồn '{source_id}' không tồn tại.")

    init_db()
    with _LOCK, _connect() as conn:
        sql = _insert_ignore(conn, "object_source_refs",
                              ("object_id", "source_id", "locator", "extracted_at"))
        _exec(conn, sql, (object_id, source_id, locator or "", _now()))


def link_objects(from_id: str, to_id: str, relation_type: str, project_id: str,
                  revision_id: str) -> None:
    if relation_type not in RELATION_TYPES:
        raise ValueError(
            f"Loại quan hệ không hợp lệ: '{relation_type}'. Chọn một trong {RELATION_TYPES}."
        )
    if get_object(from_id) is None:
        raise ValueError(f"Đối tượng '{from_id}' không tồn tại.")
    if get_object(to_id) is None:
        raise ValueError(f"Đối tượng '{to_id}' không tồn tại.")

    init_db()
    with _LOCK, _connect() as conn:
        sql = _insert_ignore(conn, "object_relations",
                              ("from_id", "to_id", "relation_type", "project_id",
                               "revision_id", "created_at"))
        _exec(conn, sql, (from_id, to_id, relation_type, project_id, revision_id, _now()))


def get_relations(object_id: str, relation_type: str | None = None) -> list[dict]:
    init_db()
    query = "SELECT * FROM object_relations WHERE (from_id = ? OR to_id = ?)"
    params: list = [object_id, object_id]
    if relation_type is not None:
        query += " AND relation_type = ?"
        params.append(relation_type)
    query += " ORDER BY created_at"
    with _LOCK, _connect() as conn:
        rows = _exec(conn, query, tuple(params)).fetchall()
    return [dict(r) for r in rows]
