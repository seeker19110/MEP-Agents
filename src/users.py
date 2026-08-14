"""Cơ sở dữ liệu người dùng: tài khoản, vai trò, thu hồi token.

Trước module này, "đa người dùng" của hệ thống là **một** tài khoản bootstrap đọc từ biến
môi trường (`JWT_BOOTSTRAP_USER`/`JWT_BOOTSTRAP_PASSWORD`). Không tạo được người dùng thứ
hai, không phân quyền, và **không có cách nào thu hồi một token đã phát** — đổi mật khẩu
cũng không đuổi được phiên đang chạy, token vẫn hợp lệ tới lúc hết hạn.

## Ba quyết định thiết kế, và lý do

**1. SQLite qua `sqlite3` của thư viện chuẩn.** Dự án đã dùng SQLite cho checkpoint
LangGraph, nên không thêm phụ thuộc nào. Postgres vẫn để ngỏ (`DATABASE_URL` đã có trong
`config.py`) nhưng CỐ Ý chưa hiện thực: viết schema Postgres mà không có instance thật để
chạy thử là đoán mò — đúng lý do đã ghi ở `TECH_DEBT.md` mục 1. Toàn bộ truy vấn ở đây đi
qua một lớp mỏng, thêm backend Postgres về sau không phải viết lại phần gọi.

**2. Hash mật khẩu bằng PBKDF2-HMAC-SHA256 (`hashlib.pbkdf2_hmac`).** bcrypt/argon2 tốt
hơn về lý thuyết, nhưng cả hai là phụ thuộc mới, mà PBKDF2 với 600.000 vòng lặp là mức
OWASP khuyến nghị cho SHA-256 và nằm sẵn trong thư viện chuẩn. Muối riêng từng người dùng,
so sánh bằng `hmac.compare_digest`.

**3. Thu hồi token bằng `token_version`, không phải danh sách đen.** Mỗi người dùng có một
số phiên bản; JWT mang theo `ver`. Thu hồi = tăng số đó, mọi token cũ lập tức vô hiệu.
Danh sách đen thì phải lưu từng token, dọn rác theo hạn, và vẫn sót nếu bỏ lỡ một cái —
một con số nguyên làm đúng việc đó mà không có trạng thái phải dọn.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import threading
import time

logger = logging.getLogger(__name__)

#: Vai trò, từ ít quyền tới nhiều quyền. Thứ tự trong tuple LÀ thứ tự quyền — `role_allows`
#: dựa vào nó, nên đừng sắp xếp lại mà không đọc hàm đó.
ROLES = ("viewer", "engineer", "admin")

#: viewer: chỉ xem kết quả của chính mình.
#: engineer: thêm quyền tạo việc (upload bản vẽ, chạy phân tích) — tốn CPU và tiền LLM.
#: admin: thêm quyền quản lý người dùng.
DEFAULT_ROLE = "engineer"

_PBKDF2_ROUNDS = 600_000
_LOCK = threading.Lock()


def db_path() -> str:
    """Đường dẫn file CSDL. Đọc mỗi lần gọi để test đổi được bằng biến môi trường."""
    from src.workspace import get_project_root

    configured = os.environ.get("USER_DB_PATH", "").strip()
    if configured:
        return configured
    return os.path.join(get_project_root(), "data", "users.sqlite")


def _connect() -> sqlite3.Connection:
    path = db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Tạo bảng nếu chưa có. Gọi được nhiều lần, không gây hại."""
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username      TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                salt          TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'engineer',
                token_version INTEGER NOT NULL DEFAULT 1,
                disabled      INTEGER NOT NULL DEFAULT 0,
                created_at    INTEGER NOT NULL
            )
            """
        )


# --- Mật khẩu ---

def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Trả `(hash_hex, salt_hex)`. Muối riêng từng người dùng, sinh ngẫu nhiên nếu không truyền."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ROUNDS
    )
    return digest.hex(), salt


def _password_matches(password: str, expected_hash: str, salt: str) -> bool:
    actual, _ = hash_password(password, salt)
    return hmac.compare_digest(actual, expected_hash)


# --- Quản lý người dùng ---

def create_user(username: str, password: str, role: str = DEFAULT_ROLE) -> dict:
    """Tạo người dùng mới. Ném `ValueError` nếu trùng tên hoặc dữ liệu không hợp lệ."""
    username = (username or "").strip()
    if not username:
        raise ValueError("Tên đăng nhập không được rỗng.")
    if not password or len(password) < 8:
        raise ValueError("Mật khẩu phải dài ít nhất 8 ký tự.")
    if role not in ROLES:
        raise ValueError(f"Vai trò không hợp lệ: {role}. Chọn một trong {ROLES}.")

    init_db()
    pw_hash, salt = hash_password(password)
    with _LOCK, _connect() as conn:
        existing = conn.execute(
            "SELECT username FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            raise ValueError(f"Người dùng '{username}' đã tồn tại.")
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, role, token_version, disabled, created_at)"
            " VALUES (?, ?, ?, ?, 1, 0, ?)",
            (username, pw_hash, salt, role, int(time.time())),
        )
    logger.info("Đã tạo người dùng '%s' (vai trò %s)", username, role)
    return {"username": username, "role": role, "disabled": False}


def get_user(username: str) -> dict | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT username, role, token_version, disabled, created_at FROM users WHERE username = ?",
            ((username or "").strip(),),
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    init_db()
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT username, role, token_version, disabled, created_at FROM users ORDER BY username"
        ).fetchall()
    return [dict(r) for r in rows]


def has_any_user() -> bool:
    """Có người dùng nào trong CSDL chưa."""
    init_db()
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    return row is not None


def has_admin_user() -> bool:
    """Có admin nào còn hoạt động trong CSDL chưa. **Đây** là điều kiện tắt tài khoản bootstrap.

    Lúc đầu tôi dùng `has_any_user()`, và đó là một cái bẫy: tài khoản bootstrap tạo một
    người dùng `viewer` đầu tiên là CSDL "đã có người dùng", bootstrap tắt ngay, và không
    còn ai đăng nhập được bằng quyền admin nữa — khóa cứng cả hệ thống.

    Điều kiện đúng bám theo mục đích của tài khoản bootstrap: nó tồn tại để **có đường tạo
    admin thật đầu tiên**. Xong việc đó thì tắt, chưa xong thì còn. Kéo theo một hành vi
    khôi phục hợp lý: lỡ khóa/xóa hết admin thì bootstrap sống lại làm đường vào cứu hộ.
    """
    init_db()
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE role = 'admin' AND disabled = 0 LIMIT 1"
        ).fetchone()
    return row is not None


def _active_admin_count(conn) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND disabled = 0"
    ).fetchone()
    return int(row["n"])


def verify_password(username: str, password: str) -> dict | None:
    """Kiểm tra đăng nhập. Trả thông tin người dùng, hoặc None nếu sai/bị khóa.

    Người bị khóa (`disabled`) trả về None y như sai mật khẩu — không nói cho người gọi
    biết tài khoản có tồn tại hay không.
    """
    init_db()
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT username, password_hash, salt, role, token_version, disabled FROM users WHERE username = ?",
            ((username or "").strip(),),
        ).fetchone()
    if row is None or row["disabled"]:
        return None
    if not _password_matches(password or "", row["password_hash"], row["salt"]):
        return None
    return {
        "username": row["username"],
        "role": row["role"],
        "token_version": row["token_version"],
    }


def set_password(username: str, password: str, *, revoke_tokens: bool = True) -> None:
    """Đổi mật khẩu. **Mặc định thu hồi luôn mọi token đang có.**

    Đổi mật khẩu mà không thu hồi token là một cái bẫy quen thuộc: người dùng đổi mật khẩu
    vì nghi bị lộ, nhưng phiên của kẻ kia vẫn chạy tiếp tới lúc token hết hạn.
    """
    if not password or len(password) < 8:
        raise ValueError("Mật khẩu phải dài ít nhất 8 ký tự.")
    init_db()
    pw_hash, salt = hash_password(password)
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ?, salt = ?"
            + (", token_version = token_version + 1" if revoke_tokens else "")
            + " WHERE username = ?",
            (pw_hash, salt, (username or "").strip()),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Không có người dùng '{username}'.")


def set_role(username: str, role: str) -> None:
    if role not in ROLES:
        raise ValueError(f"Vai trò không hợp lệ: {role}. Chọn một trong {ROLES}.")
    init_db()
    with _LOCK, _connect() as conn:
        _guard_last_admin(conn, username, "hạ quyền", still_admin=(role == "admin"))
        cur = conn.execute(
            "UPDATE users SET role = ?, token_version = token_version + 1 WHERE username = ?",
            (role, (username or "").strip()),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Không có người dùng '{username}'.")
    # Hạ quyền cũng phải thu hồi token: nếu không, token cũ vẫn mang vai trò cũ và người
    # vừa bị hạ quyền tiếp tục làm được đúng những việc vừa bị cấm.
    logger.info("Đã đổi vai trò của '%s' thành %s (token cũ bị thu hồi)", username, role)


def set_disabled(username: str, disabled: bool) -> None:
    """Khóa/mở khóa tài khoản. Khóa thì thu hồi luôn token đang có."""
    init_db()
    with _LOCK, _connect() as conn:
        if disabled:
            _guard_last_admin(conn, username, "khóa", still_admin=False)
        cur = conn.execute(
            "UPDATE users SET disabled = ?"
            + (", token_version = token_version + 1" if disabled else "")
            + " WHERE username = ?",
            (1 if disabled else 0, (username or "").strip()),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Không có người dùng '{username}'.")


def revoke_tokens(username: str) -> int:
    """Vô hiệu mọi token đã phát cho người này. Trả về `token_version` mới."""
    init_db()
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "UPDATE users SET token_version = token_version + 1 WHERE username = ?",
            ((username or "").strip(),),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Không có người dùng '{username}'.")
        row = conn.execute(
            "SELECT token_version FROM users WHERE username = ?", ((username or "").strip(),)
        ).fetchone()
    logger.info("Đã thu hồi token của '%s' (phiên bản mới: %s)", username, row["token_version"])
    return int(row["token_version"])


def delete_user(username: str) -> None:
    init_db()
    with _LOCK, _connect() as conn:
        _guard_last_admin(conn, username, "xóa", still_admin=False)
        cur = conn.execute("DELETE FROM users WHERE username = ?", ((username or "").strip(),))
        if cur.rowcount == 0:
            raise ValueError(f"Không có người dùng '{username}'.")


def _guard_last_admin(conn, username: str, action: str, *, still_admin: bool) -> None:
    """Chặn thao tác làm mất admin cuối cùng đang hoạt động.

    Không có chốt này thì một cú nhấp nhầm (tự hạ quyền chính mình, khóa nhầm đồng
    nghiệp cuối cùng) là mất quyền quản trị. Hệ thống vẫn khôi phục được — tài khoản
    bootstrap sống lại khi không còn admin — nhưng đường đó cần sửa biến môi trường và
    khởi động lại dịch vụ. Chặn ngay tại chỗ rẻ hơn nhiều.
    """
    if still_admin:
        return
    username = (username or "").strip()
    row = conn.execute(
        "SELECT role, disabled FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None or row["role"] != "admin" or row["disabled"]:
        return  # không phải admin đang hoạt động thì thao tác không đụng tới số admin
    if _active_admin_count(conn) <= 1:
        raise ValueError(
            f"Không thể {action} '{username}': đây là admin duy nhất còn hoạt động. "
            f"Hãy tạo hoặc cấp quyền admin cho một người khác trước."
        )


# --- Phân quyền ---

def role_allows(role: str, required: str) -> bool:
    """Vai trò `role` có đủ quyền cho mức `required` không.

    Quyền xếp bậc theo thứ tự trong `ROLES`: admin làm được mọi việc của engineer, engineer
    làm được mọi việc của viewer. Vai trò lạ (token cũ, dữ liệu hỏng) coi như **không đủ
    quyền** — fail-closed.
    """
    try:
        return ROLES.index(role) >= ROLES.index(required)
    except ValueError:
        return False
