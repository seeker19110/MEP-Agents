"""Project Kernel — canonical project state cho Engineering OS.

Đặc tả đầy đủ: [`docs/DAC_TA_PROJECT_KERNEL.md`](../docs/DAC_TA_PROJECT_KERNEL.md). Đây là
bước 1 ("schema + module trơn") trong kế hoạch triển khai ở đặc tả đó (mục 11): module
đứng **độc lập**, không có tool nào gọi vào, không có route API — đúng bài học "ghép sai
khi chạy chung" từ PR #32 (`progress.md` mục 3.4–3.5). Nối vào hệ thống là việc của lượt
sau.

## Ba quyết định thiết kế, và lý do

**1. SQLite riêng file, qua `sqlite3` thư viện chuẩn** — cùng lựa chọn và cùng lý do đã ghi
ở `src/users.py`: dự án đã dùng SQLite cho checkpoint và CSDL người dùng, không thêm phụ
thuộc. Tách file riêng (`project_kernel.sqlite`, không dùng chung `users.sqlite`) để hai
schema không khóa lẫn nhau khi ghi đồng thời, và xóa thử CSDL dự án lúc phát triển không
đụng tài khoản người dùng thật. `DATABASE_URL` (Postgres) trong `config.py` vẫn để ngỏ,
cố ý chưa hiện thực — xem `TECH_DEBT.md` mục 1.

**2. `object_id` (và `project_id`/`revision_id`/`source_id`) là ID nội bộ bất biến, tách
khỏi `tag` (nhãn nghiệp vụ có thể đổi).** Sinh bằng `uuid.uuid4().hex`, không bao giờ tái
sử dụng, không được parse để suy luận gì ngoài mục đích đọc log bằng mắt. Đây là điểm dễ
làm sai nhất theo đặc tả — xem mục 7 của đặc tả để biết lý do tách.

**3. Chuyển trạng thái đối tượng được canh ở một chỗ duy nhất** (`update_object_status`),
không để tầng gọi tự `UPDATE status`. `ALLOWED_TRANSITIONS` bên dưới là nguồn duy nhất cho
luật này — thêm trạng thái mới phải sửa đúng một chỗ.
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


def db_path() -> str:
    """Đường dẫn file CSDL. Đọc mỗi lần gọi để test đổi được bằng biến môi trường."""
    from src.workspace import get_project_root

    configured = os.environ.get("PROJECT_KERNEL_DB_PATH", "").strip()
    if configured:
        return configured
    return os.path.join(get_project_root(), "data", "project_kernel.sqlite")


def _connect() -> sqlite3.Connection:
    path = db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Tạo bảng/index nếu chưa có. Gọi được nhiều lần, không gây hại."""
    with _LOCK, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                owner      TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'active',
                created_at INTEGER NOT NULL,
                metadata   TEXT
            );

            CREATE TABLE IF NOT EXISTS revisions (
                revision_id        TEXT PRIMARY KEY,
                project_id         TEXT NOT NULL,
                parent_revision_id TEXT,
                note               TEXT,
                created_by         TEXT NOT NULL,
                created_at         INTEGER NOT NULL,
                status             TEXT NOT NULL DEFAULT 'draft'
            );
            CREATE INDEX IF NOT EXISTS idx_revisions_project ON revisions(project_id);

            CREATE TABLE IF NOT EXISTS sources (
                source_id    TEXT PRIMARY KEY,
                project_id   TEXT NOT NULL,
                kind         TEXT NOT NULL,
                storage_key  TEXT NOT NULL,
                checksum     TEXT,
                uploaded_by  TEXT NOT NULL,
                uploaded_at  INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sources_project ON sources(project_id);

            CREATE TABLE IF NOT EXISTS engineering_objects (
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
            );
            CREATE INDEX IF NOT EXISTS idx_objects_project_revision
                ON engineering_objects(project_id, revision_id);
            CREATE INDEX IF NOT EXISTS idx_objects_project_type
                ON engineering_objects(project_id, type);
            CREATE INDEX IF NOT EXISTS idx_objects_parent
                ON engineering_objects(parent_id);

            CREATE TABLE IF NOT EXISTS object_source_refs (
                object_id    TEXT NOT NULL,
                source_id    TEXT NOT NULL,
                locator      TEXT NOT NULL DEFAULT '',
                extracted_at INTEGER NOT NULL,
                PRIMARY KEY (object_id, source_id, locator)
            );

            CREATE TABLE IF NOT EXISTS object_relations (
                from_id      TEXT NOT NULL,
                to_id        TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                project_id   TEXT NOT NULL,
                revision_id  TEXT NOT NULL,
                created_at   INTEGER NOT NULL,
                PRIMARY KEY (from_id, to_id, relation_type, revision_id)
            );
            CREATE INDEX IF NOT EXISTS idx_relations_project ON object_relations(project_id);
            """
        )


def _new_id(prefix: str) -> str:
    """`{prefix}:{uuid4_hex}` — bất biến, không được parse để suy luận gì (mục 7 đặc tả)."""
    import re

    clean = re.sub(r"[^a-z0-9_]+", "_", (prefix or "obj").strip().lower()).strip("_") or "obj"
    return f"{clean}:{uuid.uuid4().hex}"


def _now() -> int:
    return int(time.time())


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


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
        conn.execute(
            "INSERT INTO projects (project_id, name, owner, status, created_at, metadata)"
            " VALUES (?, ?, ?, 'active', ?, ?)",
            (project_id, name, owner, created_at, json.dumps(metadata or {}, ensure_ascii=False)),
        )
    logger.info("Đã tạo dự án '%s' (%s), owner=%s", name, project_id, owner)
    return {"project_id": project_id, "name": name, "owner": owner, "status": "active",
            "created_at": created_at, "metadata": metadata or {}}


def get_project(project_id: str) -> dict | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = conn.execute(
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
        rows = conn.execute(
            "SELECT project_id, name, owner, status, created_at, metadata FROM projects"
            " WHERE owner = ? ORDER BY created_at DESC", ((owner or "").strip(),),
        ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["metadata"] = json.loads(d["metadata"] or "{}")
        out.append(d)
    return out


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
        conn.execute(
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
        row = conn.execute(
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
        conn.execute(
            "UPDATE revisions SET status = 'superseded'"
            " WHERE project_id = ? AND status = 'active' AND revision_id != ?",
            (revision["project_id"], revision_id),
        )
        conn.execute(
            "UPDATE revisions SET status = 'active' WHERE revision_id = ?", (revision_id,),
        )
    logger.info("Revision %s là active cho dự án %s", revision_id, revision["project_id"])


def get_active_revision(project_id: str) -> dict | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = conn.execute(
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
            conn.execute(
                "INSERT INTO sources (source_id, project_id, kind, storage_key, checksum,"
                " uploaded_by, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (source_id, project_id, kind, storage_key, checksum, uploaded_by, uploaded_at),
            )
        except sqlite3.IntegrityError as e:
            # Về lý thuyết không xảy ra (source_id sinh mới mỗi lần bằng uuid4), nhưng nếu
            # có va chạm thì phải NGĂN, không được lặng lẽ UPDATE — đúng nguyên tắc "không
            # được ghi đè source" (`progress.md` mục 8).
            raise ValueError(f"Nguồn '{source_id}' đã tồn tại, không thể ghi đè: {e}") from e
    logger.info("Đã đăng ký nguồn %s (%s) cho dự án %s", source_id, kind, project_id)
    return {"source_id": source_id, "project_id": project_id, "kind": kind,
            "storage_key": storage_key, "checksum": checksum, "uploaded_by": uploaded_by,
            "uploaded_at": uploaded_at}


def get_source(source_id: str) -> dict | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = conn.execute(
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
    try:
        properties_json = json.dumps(properties or {}, ensure_ascii=False)
    except TypeError as e:
        raise ValueError(f"properties phải là JSON hợp lệ: {e}") from e

    init_db()
    object_id = _new_id(type)
    now = _now()
    with _LOCK, _connect() as conn:
        conn.execute(
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
            "properties": properties or {}, "status": "discovered",
            "confidence": confidence, "created_at": now, "updated_at": now}


def _object_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["properties"] = json.loads(d["properties"] or "{}")
    return d


def get_object(object_id: str) -> dict | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT * FROM engineering_objects WHERE object_id = ?", (object_id,),
        ).fetchone()
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
        rows = conn.execute(query, params).fetchall()
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
        conn.execute(
            "UPDATE engineering_objects SET status = ?, updated_at = ? WHERE object_id = ?",
            (new_status, _now(), object_id),
        )
    logger.info("Đối tượng %s: %s -> %s", object_id, current, new_status)


# --- Source ref & relation ---

def attach_source_ref(object_id: str, source_id: str, locator: str = "") -> None:
    if get_object(object_id) is None:
        raise ValueError(f"Đối tượng '{object_id}' không tồn tại.")
    if get_source(source_id) is None:
        raise ValueError(f"Nguồn '{source_id}' không tồn tại.")

    init_db()
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO object_source_refs (object_id, source_id, locator,"
            " extracted_at) VALUES (?, ?, ?, ?)",
            (object_id, source_id, locator or "", _now()),
        )


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
        conn.execute(
            "INSERT OR IGNORE INTO object_relations (from_id, to_id, relation_type,"
            " project_id, revision_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (from_id, to_id, relation_type, project_id, revision_id, _now()),
        )


def get_relations(object_id: str, relation_type: str | None = None) -> list[dict]:
    init_db()
    query = "SELECT * FROM object_relations WHERE (from_id = ? OR to_id = ?)"
    params: list = [object_id, object_id]
    if relation_type is not None:
        query += " AND relation_type = ?"
        params.append(relation_type)
    query += " ORDER BY created_at"
    with _LOCK, _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]
