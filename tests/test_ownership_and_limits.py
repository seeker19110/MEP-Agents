"""Quyền sở hữu tài nguyên, hạn mức upload và giới hạn tần suất.

Xác thực trả lời "anh là ai". Bộ test này canh câu còn lại — "cái này có phải của anh
không" — cùng hai chốt chặn tài nguyên đi kèm.
"""
import types

import pytest
from fastapi.testclient import TestClient

from src import api, rate_limit, task_owner


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    rate_limit.reset()
    task_owner._MEM.clear()
    # Ép dùng bản bộ nhớ: môi trường test không có Redis, và test không được phụ thuộc
    # vào việc có hay không có nó.
    monkeypatch.setattr(task_owner, "_redis", lambda: None)
    yield
    rate_limit.reset()
    task_owner._MEM.clear()


@pytest.fixture
def client(monkeypatch):
    counter = {"n": 0}

    def fake_delay(*a, **kw):
        counter["n"] += 1
        return types.SimpleNamespace(id=f"task-{counter['n']}")

    monkeypatch.setattr(api.parse_cad_to_db_task, "delay", fake_delay)
    return TestClient(api.app)


@pytest.fixture
def jwt_on(monkeypatch):
    """Bật JWT một cách KHÔNG phụ thuộc thứ tự import.

    `src.config.settings` chụp lại biến môi trường đúng MỘT lần, lúc `src.config` được
    import lần đầu. Test nào `monkeypatch.setenv("JWT_SECRET", ...)` trước thời điểm đó
    sẽ khiến `settings.jwt_secret` dính giá trị test **suốt cả phiên pytest** — các test
    sau tưởng JWT đang tắt nhưng thực ra đang bật, và hỏng theo kiểu rất khó lần ra.
    Đặt thẳng thuộc tính thì `monkeypatch` hoàn nguyên được, không phụ thuộc thứ tự.
    """
    from src.config import settings

    monkeypatch.setattr(settings, "jwt_secret", "unit-test-secret")
    return "unit-test-secret"


def _jwt_headers(user: str) -> dict:
    from src.auth_jwt import create_access_token
    return {"Authorization": f"Bearer {create_access_token(user)}"}


# --- Quyền sở hữu ---

def test_task_owner_recorded_on_upload(client, tmp_path, monkeypatch, jwt_on):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_API_KEY", "")

    resp = client.post(
        "/api/v1/takeoff",
        files={"file": ("a.dxf", b"noi dung", "application/octet-stream")},
        headers=_jwt_headers("an"),
    )
    assert resp.status_code == 200
    assert task_owner.get_owner(resp.json()["task_id"]) == "an"


def test_other_user_cannot_read_or_download_task(client, tmp_path, monkeypatch, jwt_on):
    """Đây là lỗ hổng chính mục này bịt: trước đây ai xác thực được cũng tải được BOQ
    của bất kỳ task_id nào."""
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_API_KEY", "")

    created = client.post(
        "/api/v1/takeoff",
        files={"file": ("a.dxf", b"noi dung", "application/octet-stream")},
        headers=_jwt_headers("an"),
    )
    task_id = created.json()["task_id"]

    for path in (f"/api/v1/task/{task_id}", f"/api/v1/download/{task_id}"):
        resp = client.get(path, headers=_jwt_headers("binh"))
        assert resp.status_code == 403, f"{path} cho người khác xem được"


def test_owner_can_read_own_task(client, tmp_path, monkeypatch, jwt_on):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_API_KEY", "")

    created = client.post(
        "/api/v1/takeoff",
        files={"file": ("a.dxf", b"noi dung", "application/octet-stream")},
        headers=_jwt_headers("an"),
    )
    task_id = created.json()["task_id"]

    monkeypatch.setattr(api, "AsyncResult", lambda *a, **kw: types.SimpleNamespace(
        state="PENDING", info=None, result=None))
    resp = client.get(f"/api/v1/task/{task_id}", headers=_jwt_headers("an"))
    assert resp.status_code == 200


def test_unknown_task_is_denied_when_auth_on():
    """Fail-closed: mất bản ghi chủ sở hữu thì từ chối, không mở lại lỗ hổng."""
    assert task_owner.is_owner("khong-co-that", "an") is False


def test_ownership_not_enforced_when_auth_off():
    """Không bật xác thực thì mọi người là cùng một chủ thể — chặn nhau là vô nghĩa."""
    assert task_owner.is_owner("bat-ky", task_owner.ANONYMOUS) is True


def test_shared_api_key_is_a_single_principal():
    """Khóa chung theo định nghĩa là MỘT danh tính dùng chung, nên kiểm tra chủ sở hữu
    không thêm được an toàn nào — chỉ thêm một đường hỏng khi mất bản ghi.

    Đi kèm là giới hạn phải nói rõ: ai cầm `MEP_AGENTS_API_KEY` đọc được task của mọi
    người. Muốn tách người dùng thật thì dùng JWT và không phát khóa chung ra ngoài.
    """
    task_owner.set_owner("task-cua-an", "an")
    assert task_owner.is_owner("task-cua-an", task_owner.SHARED_KEY_IDENTITY) is True
    assert task_owner.is_owner("task-cua-an", "binh") is False


def test_websocket_rejects_other_users_task(monkeypatch, jwt_on):
    monkeypatch.setattr(api, "_API_KEY", "")
    from src.auth_jwt import create_access_token

    task_owner.set_owner("task-cua-an", "an")
    assert api._ws_identity(token=create_access_token("binh")) == "binh"
    assert task_owner.is_owner("task-cua-an", "binh") is False
    assert task_owner.is_owner("task-cua-an", "an") is True


# --- Hạn mức upload ---

def test_upload_rejects_file_over_limit(client, tmp_path, monkeypatch):
    """`await file.read()` cũ nạp toàn bộ file vào RAM rồi mới ghi — file 5 GB là một lần
    hết RAM. Nay đọc theo khối và dừng ngay khi vượt hạn mức."""
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_API_KEY", "")
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 1024)

    resp = client.post(
        "/api/v1/takeoff",
        files={"file": ("to.dxf", b"x" * 5000, "application/octet-stream")},
    )
    assert resp.status_code == 413
    assert "hạn mức" in resp.json()["detail"]


def test_oversized_upload_leaves_no_partial_file(client, tmp_path, monkeypatch):
    """File dở dang vừa tốn đĩa vừa có thể bị đọc nhầm thành bản vẽ hỏng ở lượt sau."""
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_API_KEY", "")
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 1024)

    client.post(
        "/api/v1/takeoff",
        files={"file": ("to.dxf", b"x" * 5000, "application/octet-stream")},
    )
    assert list(tmp_path.iterdir()) == []


def test_upload_within_limit_still_works(client, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_API_KEY", "")
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 1024 * 1024)

    resp = client.post(
        "/api/v1/takeoff",
        files={"file": ("ok.dxf", b"y" * 2048, "application/octet-stream")},
    )
    assert resp.status_code == 200
    assert (tmp_path / "ok.dxf").read_bytes() == b"y" * 2048


# --- Giới hạn tần suất ---

def test_rate_limit_blocks_after_quota(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "3")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    rate_limit.reset()

    for _ in range(3):
        allowed, _ = rate_limit.check("an", scope="write")
        assert allowed
    allowed, retry_after = rate_limit.check("an", scope="write")
    assert allowed is False and retry_after > 0


def test_rate_limit_is_per_identity(monkeypatch):
    """Người dùng này gọi nhiều không được làm người khác bị chặn."""
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    rate_limit.reset()

    rate_limit.check("an", scope="write")
    rate_limit.check("an", scope="write")
    assert rate_limit.check("an", scope="write")[0] is False
    assert rate_limit.check("binh", scope="write")[0] is True


def test_rate_limit_can_be_disabled(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "0")
    rate_limit.reset()
    for _ in range(50):
        assert rate_limit.check("an", scope="write")[0] is True


def test_api_returns_429_when_over_quota(client, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_API_KEY", "")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    rate_limit.reset()

    def upload():
        return client.post(
            "/api/v1/takeoff",
            files={"file": ("a.dxf", b"noi dung", "application/octet-stream")},
        )

    assert upload().status_code == 200
    assert upload().status_code == 200
    blocked = upload()
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")


def test_read_endpoints_are_not_rate_limited(client, tmp_path, monkeypatch):
    """Chỉ endpoint tạo việc nặng bị giới hạn. Chặn cả đường đọc trạng thái sẽ làm hỏng
    chính vòng theo dõi tiến độ của Web App."""
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_API_KEY", "")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    rate_limit.reset()
    monkeypatch.setattr(api, "AsyncResult", lambda *a, **kw: types.SimpleNamespace(
        state="PENDING", info=None, result=None))

    for _ in range(5):
        resp = client.get("/api/v1/task/bat-ky")
        assert resp.status_code == 200
