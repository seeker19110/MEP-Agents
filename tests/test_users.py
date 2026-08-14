"""CSDL người dùng, phân quyền và thu hồi token.

Trước đợt này, "đa người dùng" là MỘT tài khoản bootstrap từ biến môi trường: không tạo
được người thứ hai, không phân quyền, và không có cách nào thu hồi token đã phát.
"""
import types

import pytest
from fastapi.testclient import TestClient

from src import api, rate_limit, task_owner, users


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    """Mỗi test một file CSDL riêng — không test nào thấy dữ liệu của test khác."""
    monkeypatch.setenv("USER_DB_PATH", str(tmp_path / "users.sqlite"))
    monkeypatch.setattr(users, "_PBKDF2_ROUNDS", 1_000)  # 600k vòng làm test chậm vô ích
    rate_limit.reset()
    task_owner._MEM.clear()
    monkeypatch.setattr(task_owner, "_redis", lambda: None)
    users.init_db()
    yield
    rate_limit.reset()
    task_owner._MEM.clear()


@pytest.fixture
def jwt_on(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "jwt_secret", "unit-test-secret")
    return "unit-test-secret"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api.parse_cad_to_db_task, "delay",
                        lambda *a, **kw: types.SimpleNamespace(id="task-1"))
    monkeypatch.setattr(api, "_API_KEY", "")
    return TestClient(api.app)


def _login(client, username, password):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def _headers(client, username, password):
    return {"Authorization": f"Bearer {_login(client, username, password).json()['access_token']}"}


# --- Mật khẩu ---

def test_password_hash_is_salted_and_verifiable():
    """Hai người cùng mật khẩu phải ra hash khác nhau — nếu không, lộ một là lộ cả hai."""
    h1, s1 = users.hash_password("matkhau123")
    h2, s2 = users.hash_password("matkhau123")
    assert s1 != s2 and h1 != h2
    assert users.hash_password("matkhau123", s1)[0] == h1
    assert users.hash_password("sai", s1)[0] != h1


def test_password_is_never_stored_in_plaintext():
    users.create_user("an", "matkhau123")
    import sqlite3
    conn = sqlite3.connect(users.db_path())
    row = conn.execute("SELECT * FROM users WHERE username='an'").fetchone()
    conn.close()
    assert "matkhau123" not in str(row)


def test_short_password_rejected():
    with pytest.raises(ValueError, match="ít nhất 8 ký tự"):
        users.create_user("an", "ngan")


# --- Tài khoản và vai trò ---

def test_create_and_verify_user():
    users.create_user("an", "matkhau123", role="engineer")
    user = users.verify_password("an", "matkhau123")
    assert user["username"] == "an" and user["role"] == "engineer"
    assert users.verify_password("an", "sai") is None


def test_duplicate_username_rejected():
    users.create_user("an", "matkhau123")
    with pytest.raises(ValueError, match="đã tồn tại"):
        users.create_user("an", "matkhaukhac")


def test_disabled_user_cannot_log_in():
    """Người bị khóa trả None y như sai mật khẩu — không tiết lộ tài khoản có tồn tại."""
    users.create_user("an", "matkhau123")
    users.set_disabled("an", True)
    assert users.verify_password("an", "matkhau123") is None


def test_role_hierarchy():
    assert users.role_allows("admin", "engineer") is True
    assert users.role_allows("engineer", "engineer") is True
    assert users.role_allows("viewer", "engineer") is False
    assert users.role_allows("admin", "admin") is True
    assert users.role_allows("engineer", "admin") is False


def test_unknown_role_is_denied():
    """Vai trò lạ (token cũ, dữ liệu hỏng) phải bị coi là không đủ quyền — fail-closed."""
    assert users.role_allows("khong-ton-tai", "viewer") is False
    assert users.role_allows("", "viewer") is False


# --- Thu hồi token ---

def test_revoke_tokens_bumps_version():
    users.create_user("an", "matkhau123")
    before = users.get_user("an")["token_version"]
    assert users.revoke_tokens("an") == before + 1


def test_password_change_revokes_tokens():
    """Đổi mật khẩu vì nghi bị lộ mà phiên của kẻ kia vẫn chạy thì đổi để làm gì."""
    users.create_user("an", "matkhau123")
    before = users.get_user("an")["token_version"]
    users.set_password("an", "matkhaumoi456")
    assert users.get_user("an")["token_version"] == before + 1


def test_role_change_revokes_tokens():
    """Hạ quyền mà không thu hồi token thì token cũ vẫn mang vai trò cũ."""
    users.create_user("an", "matkhau123", role="admin")
    users.create_user("binh", "matkhau123", role="admin")  # để còn admin khác
    before = users.get_user("an")["token_version"]
    users.set_role("an", "viewer")
    assert users.get_user("an")["token_version"] == before + 1


# --- Chốt chặn admin cuối cùng ---

def test_cannot_delete_last_admin():
    users.create_user("sep", "matkhau123", role="admin")
    with pytest.raises(ValueError, match="admin duy nhất"):
        users.delete_user("sep")


def test_cannot_demote_last_admin():
    users.create_user("sep", "matkhau123", role="admin")
    with pytest.raises(ValueError, match="admin duy nhất"):
        users.set_role("sep", "viewer")


def test_cannot_disable_last_admin():
    users.create_user("sep", "matkhau123", role="admin")
    with pytest.raises(ValueError, match="admin duy nhất"):
        users.set_disabled("sep", True)


def test_can_remove_admin_when_another_exists():
    users.create_user("sep", "matkhau123", role="admin")
    users.create_user("pho", "matkhau123", role="admin")
    users.delete_user("sep")
    assert users.get_user("sep") is None


# --- Tài khoản bootstrap ---

def test_bootstrap_works_while_no_admin_exists(monkeypatch, jwt_on):
    from src import auth_jwt

    monkeypatch.setenv("JWT_BOOTSTRAP_USER", "boss")
    monkeypatch.setenv("JWT_BOOTSTRAP_PASSWORD", "bootstrap1")
    user = auth_jwt.authenticate("boss", "bootstrap1")
    assert user is not None and user["role"] == "admin"


def test_bootstrap_still_works_after_creating_a_non_admin(monkeypatch, jwt_on):
    """Cái bẫy đã sửa: điều kiện tắt bootstrap là "có ADMIN", không phải "có người dùng".

    Dùng "có người dùng" thì tạo một viewer đầu tiên là tắt bootstrap ngay, và không còn
    ai đăng nhập được bằng quyền admin — khóa cứng cả hệ thống.
    """
    from src import auth_jwt

    monkeypatch.setenv("JWT_BOOTSTRAP_USER", "boss")
    monkeypatch.setenv("JWT_BOOTSTRAP_PASSWORD", "bootstrap1")
    users.create_user("an", "matkhau123", role="viewer")
    assert auth_jwt.authenticate("boss", "bootstrap1") is not None


def test_bootstrap_disabled_once_admin_exists(monkeypatch, jwt_on):
    """Xong việc thì tắt: biến môi trường sót lại không được thành cửa hậu vĩnh viễn."""
    from src import auth_jwt

    monkeypatch.setenv("JWT_BOOTSTRAP_USER", "boss")
    monkeypatch.setenv("JWT_BOOTSTRAP_PASSWORD", "bootstrap1")
    users.create_user("sep", "matkhau123", role="admin")
    assert auth_jwt.authenticate("boss", "bootstrap1") is None


def test_last_admin_guard_blocks_the_lockout_path(monkeypatch):
    """Không thể tự khóa mình ra khỏi hệ thống qua đường thông thường.

    Chốt chặn admin cuối cùng khiến kịch bản "khóa hết admin" KHÔNG xảy ra được bằng API
    — đó là lớp phòng thủ chính, còn bootstrap cứu hộ chỉ là lưới đỡ phía sau.
    """
    users.create_user("sep", "matkhau123", role="admin")
    users.create_user("pho", "matkhau123", role="admin")
    users.set_disabled("sep", True)          # còn 'pho', cho phép
    with pytest.raises(ValueError, match="admin duy nhất"):
        users.set_disabled("pho", True)      # 'pho' là admin cuối, phải chặn
    assert users.has_admin_user() is True


def test_bootstrap_returns_as_rescue_when_no_admin_left(monkeypatch, jwt_on):
    """Lưới đỡ: nếu bằng cách nào đó không còn admin nào (sửa tay CSDL, dữ liệu hỏng,
    dữ liệu di cư từ bản cũ), bootstrap sống lại làm đường vào cứu hộ."""
    from src import auth_jwt

    monkeypatch.setenv("JWT_BOOTSTRAP_USER", "boss")
    monkeypatch.setenv("JWT_BOOTSTRAP_PASSWORD", "bootstrap1")
    users.create_user("an", "matkhau123", role="engineer")
    assert users.has_admin_user() is False
    assert auth_jwt.authenticate("boss", "bootstrap1") is not None


def test_db_user_logs_in_even_before_any_admin_exists(monkeypatch, jwt_on):
    """Engineer đã tạo phải đăng nhập được ngay, không phải chờ ai đó tạo admin."""
    from src import auth_jwt

    users.create_user("an", "matkhau123", role="engineer")
    assert auth_jwt.authenticate("an", "matkhau123") is not None


def test_broken_db_denies_login_instead_of_opening_bootstrap(monkeypatch, jwt_on):
    """Sự cố CSDL không được biến thành đường vào quyền admin."""
    from src import auth_jwt

    monkeypatch.setenv("JWT_BOOTSTRAP_USER", "boss")
    monkeypatch.setenv("JWT_BOOTSTRAP_PASSWORD", "bootstrap1")

    def _explode():
        raise OSError("đĩa hỏng")

    monkeypatch.setattr(users, "has_admin_user", _explode)
    assert auth_jwt.authenticate("boss", "bootstrap1") is None


# --- Qua API thật ---

def test_login_and_me_through_api(client, jwt_on):
    users.create_user("an", "matkhau123", role="engineer")
    resp = _login(client, "an", "matkhau123")
    assert resp.status_code == 200

    me = client.get("/api/v1/auth/me", headers=_headers(client, "an", "matkhau123"))
    assert me.status_code == 200
    assert me.json()["sub"] == "an"
    assert me.json()["claims"]["role"] == "engineer"


def test_viewer_cannot_create_analysis_work(client, jwt_on, tmp_path, monkeypatch):
    """Mỗi lượt phân tích tốn CPU đọc bản vẽ VÀ tiền gọi LLM thật — viewer không được tạo."""
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    users.create_user("an", "matkhau123", role="viewer")
    resp = client.post(
        "/api/v1/takeoff",
        files={"file": ("a.dxf", b"noi dung", "application/octet-stream")},
        headers=_headers(client, "an", "matkhau123"),
    )
    assert resp.status_code == 403
    assert "engineer" in resp.json()["detail"]


def test_engineer_can_create_analysis_work(client, jwt_on, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    users.create_user("an", "matkhau123", role="engineer")
    resp = client.post(
        "/api/v1/takeoff",
        files={"file": ("a.dxf", b"noi dung", "application/octet-stream")},
        headers=_headers(client, "an", "matkhau123"),
    )
    assert resp.status_code == 200


def test_viewer_can_still_read_own_task(client, jwt_on, monkeypatch):
    """Viewer bị chặn TẠO việc, nhưng vẫn phải xem được kết quả của mình."""
    users.create_user("an", "matkhau123", role="viewer")
    task_owner.set_owner("task-cua-an", "an")
    monkeypatch.setattr(api, "AsyncResult", lambda *a, **kw: types.SimpleNamespace(
        state="PENDING", info=None, result=None))
    resp = client.get("/api/v1/task/task-cua-an", headers=_headers(client, "an", "matkhau123"))
    assert resp.status_code == 200


def test_revoked_token_is_rejected_by_api(client, jwt_on):
    """Đây là chốt chính: chữ ký đúng, chưa hết hạn, nhưng đã bị thu hồi."""
    users.create_user("an", "matkhau123", role="engineer")
    headers = _headers(client, "an", "matkhau123")
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    users.revoke_tokens("an")
    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 401
    assert "thu hồi" in resp.json()["detail"]


def test_disabled_user_token_stops_working(client, jwt_on, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    users.create_user("an", "matkhau123", role="engineer")
    headers = _headers(client, "an", "matkhau123")

    users.set_disabled("an", True)
    resp = client.post(
        "/api/v1/takeoff",
        files={"file": ("a.dxf", b"x", "application/octet-stream")},
        headers=headers,
    )
    assert resp.status_code == 401


def test_change_own_password_revokes_current_session(client, jwt_on):
    users.create_user("an", "matkhau123", role="engineer")
    headers = _headers(client, "an", "matkhau123")

    resp = client.post("/api/v1/auth/change-password", headers=headers,
                       json={"old_password": "matkhau123", "new_password": "matkhaumoi456"})
    assert resp.status_code == 200
    # Token cũ chết ngay, kể cả trên chính thiết bị vừa đổi.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert _login(client, "an", "matkhaumoi456").status_code == 200


def test_change_password_requires_correct_old_password(client, jwt_on):
    users.create_user("an", "matkhau123", role="engineer")
    headers = _headers(client, "an", "matkhau123")
    resp = client.post("/api/v1/auth/change-password", headers=headers,
                       json={"old_password": "sai", "new_password": "matkhaumoi456"})
    assert resp.status_code == 401


# --- Endpoint quản trị ---

def test_admin_can_manage_users(client, jwt_on):
    users.create_user("sep", "matkhau123", role="admin")
    H = _headers(client, "sep", "matkhau123")

    assert client.post("/api/v1/admin/users", headers=H,
                       json={"username": "an", "password": "matkhau123", "role": "engineer"}).status_code == 200
    listed = client.get("/api/v1/admin/users", headers=H).json()["users"]
    assert {u["username"] for u in listed} == {"sep", "an"}

    assert client.patch("/api/v1/admin/users/an", headers=H, json={"role": "viewer"}).status_code == 200
    assert users.get_user("an")["role"] == "viewer"

    assert client.post("/api/v1/admin/users/an/revoke-tokens", headers=H).status_code == 200
    assert client.delete("/api/v1/admin/users/an", headers=H).status_code == 200
    assert users.get_user("an") is None


def test_engineer_cannot_manage_users(client, jwt_on):
    users.create_user("sep", "matkhau123", role="admin")
    users.create_user("an", "matkhau123", role="engineer")
    H = _headers(client, "an", "matkhau123")

    assert client.get("/api/v1/admin/users", headers=H).status_code == 403
    assert client.post("/api/v1/admin/users", headers=H,
                       json={"username": "x", "password": "matkhau123"}).status_code == 403


def test_admin_endpoints_reject_anonymous(client, jwt_on):
    users.create_user("sep", "matkhau123", role="admin")
    assert client.get("/api/v1/admin/users").status_code in (401, 403)


def test_last_admin_guard_surfaces_through_api(client, jwt_on):
    """Lỗi phải thành 400 kèm giải thích, không phải 500."""
    users.create_user("sep", "matkhau123", role="admin")
    H = _headers(client, "sep", "matkhau123")
    resp = client.delete("/api/v1/admin/users/sep", headers=H)
    assert resp.status_code == 404 or resp.status_code == 400
    assert "admin duy nhất" in resp.json()["detail"]
