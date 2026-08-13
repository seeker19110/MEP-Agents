"""Xác thực của API (`src/api.py`) — chạy THẬT qua route, không chỉ gọi hàm.

Lý do phải test qua route: lỗ hổng mà bộ test này ra đời để chặn chính là kiểu "hàm
xác thực đúng nhưng route không dùng nó". `src/api_phase_c_mount.py` từng gán đè
`api.require_api_key` sau khi route đã chốt dependency, nên gọi hàm trực tiếp thì thấy
đúng, còn gửi request thật thì lọt. Mọi test dưới đây đều đi qua `TestClient`.
"""
import types

import pytest
from fastapi.testclient import TestClient

from src import api


@pytest.fixture
def client(monkeypatch):
    fake_task = types.SimpleNamespace(id="fake-task-id-123")
    monkeypatch.setattr(api.parse_cad_to_db_task, "delay", lambda *a, **kw: fake_task)
    return TestClient(api.app)


def _revit_call(client, **kwargs):
    return client.post(
        "/api/v1/revit/analyze",
        json={"project_name": "X", "elements": []},
        **kwargs,
    )


# --- Mặc định: không đặt gì cả thì mở (dev cục bộ) ---

def test_open_when_no_api_key_and_no_jwt(client, monkeypatch):
    monkeypatch.setattr(api, "_API_KEY", "")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setattr(api, "_jwt_enabled", lambda: False)
    assert _revit_call(client).status_code == 200


# --- Chế độ API key ---

def test_api_key_mode_rejects_anonymous(client, monkeypatch):
    monkeypatch.setattr(api, "_API_KEY", "s3cret")
    monkeypatch.setattr(api, "_jwt_enabled", lambda: False)
    assert _revit_call(client).status_code == 401


def test_api_key_mode_accepts_header_and_query(client, monkeypatch):
    monkeypatch.setattr(api, "_API_KEY", "s3cret")
    monkeypatch.setattr(api, "_jwt_enabled", lambda: False)
    assert _revit_call(client, headers={"X-API-Key": "s3cret"}).status_code == 200
    # Query `?api_key=` cũng phải được chấp nhận (trình duyệt tải file / mở WebSocket
    # không đặt được header tùy ý).
    resp = client.post(
        "/api/v1/revit/analyze?api_key=s3cret",
        json={"project_name": "X", "elements": []},
    )
    assert resp.status_code == 200


# --- Chế độ JWT (đây là chỗ từng mở toang) ---

def test_jwt_only_mode_rejects_anonymous(client, monkeypatch):
    """Bật JWT, KHÔNG đặt API key: request nặc danh phải bị chặn.

    Đây chính là lỗ hổng cũ — route giữ bản `require_api_key` chỉ biết API key, mà API
    key lại rỗng, nên mọi endpoint trả 200 cho bất kỳ ai.
    """
    monkeypatch.setattr(api, "_API_KEY", "")
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    assert _revit_call(client).status_code == 401


def test_jwt_only_mode_accepts_valid_bearer(client, monkeypatch):
    monkeypatch.setattr(api, "_API_KEY", "")
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    from src.auth_jwt import create_access_token

    token = create_access_token("boss")
    resp = _revit_call(client, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_jwt_mode_rejects_forged_bearer(client, monkeypatch):
    monkeypatch.setattr(api, "_API_KEY", "")
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    resp = _revit_call(client, headers={"Authorization": "Bearer not.a.token"})
    assert resp.status_code == 401


def test_api_key_still_works_when_jwt_enabled(client, monkeypatch):
    """Hai cách xác thực phải song song được — plugin cũ chỉ biết gửi X-API-Key."""
    monkeypatch.setattr(api, "_API_KEY", "s3cret")
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    assert _revit_call(client, headers={"X-API-Key": "s3cret"}).status_code == 200


def test_auth_login_router_is_mounted(client, monkeypatch):
    """Router `/api/v1/auth` là việc DUY NHẤT `api_phase_c_mount` còn làm — phải còn.

    Kiểm bằng request thật chứ không duyệt `app.routes`: bản FastAPI hiện tại gắn router
    theo kiểu trì hoãn (`_IncludedRouter`), duyệt danh sách route sẽ không thấy đường dẫn.
    """
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    monkeypatch.setenv("JWT_BOOTSTRAP_USER", "boss")
    monkeypatch.setenv("JWT_BOOTSTRAP_PASSWORD", "p@ss")

    ok = client.post("/api/v1/auth/login", json={"username": "boss", "password": "p@ss"})
    assert ok.status_code == 200
    token = ok.json()["access_token"]

    bad = client.post("/api/v1/auth/login", json={"username": "boss", "password": "sai"})
    assert bad.status_code == 401

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["sub"] == "boss"


# --- WebSocket ---

def test_websocket_rejects_anonymous_in_jwt_mode(monkeypatch):
    monkeypatch.setattr(api, "_API_KEY", "")
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    assert api._ws_authorized(api_key="", token="") is False


def test_websocket_accepts_jwt_token_query(monkeypatch):
    monkeypatch.setattr(api, "_API_KEY", "")
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    from src.auth_jwt import create_access_token

    assert api._ws_authorized(token=create_access_token("boss")) is True
