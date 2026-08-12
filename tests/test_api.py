"""FastAPI Cloud API endpoints (src/api.py).

`parse_cad_to_db_task.delay(...)` is mocked everywhere — it would otherwise try to
publish to a real Redis broker, which isn't available in the test environment.
"""
import asyncio
import types

import pytest
from fastapi.testclient import TestClient

from src import api


@pytest.fixture
def client(monkeypatch):
    fake_task = types.SimpleNamespace(id="fake-task-id-123")
    monkeypatch.setattr(api.parse_cad_to_db_task, "delay", lambda *a, **kw: fake_task)
    return TestClient(api.app)


def test_root_returns_ok_status(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_takeoff_upload_queues_celery_task_and_returns_task_id(client, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    resp = client.post(
        "/api/v1/takeoff",
        files={"file": ("drawing.dxf", b"fake dxf content", "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == "fake-task-id-123"
    assert "drawing.dxf" in body["message"]


def test_takeoff_upload_sanitizes_path_traversal_filename(client, tmp_path, monkeypatch):
    """Trước khi có `_safe_upload_filename`, `file.filename` (client tự đặt trong multipart
    form) được dùng thẳng trong `os.path.join(UPLOAD_DIR, file.filename)` — filename kiểu
    "../../evil.txt" sẽ ghi file ra NGOÀI UPLOAD_DIR (path traversal / ghi file tùy ý)."""
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    outside_dir = tmp_path.parent / "outside_marker"
    resp = client.post(
        "/api/v1/takeoff",
        files={"file": ("../../evil.dxf", b"malicious content", "application/octet-stream")},
    )
    assert resp.status_code == 200
    # Không có file nào bị ghi ra ngoài UPLOAD_DIR.
    assert not outside_dir.exists()
    # Mọi file thật sự được ghi đều nằm trong UPLOAD_DIR.
    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert written[0].parent == tmp_path
    assert ".." not in written[0].name


def test_takeoff_upload_rejects_non_cad_extension(client, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    resp = client.post(
        "/api/v1/takeoff",
        files={"file": ("payload.sh", b"#!/bin/sh\necho pwned", "application/octet-stream")},
    )
    assert resp.status_code == 200
    written = list(tmp_path.iterdir())
    assert len(written) == 1
    # Đuôi lạ bị ép về .dxf thay vì giữ nguyên .sh có thể thực thi được.
    assert written[0].suffix == ".dxf"


def test_api_key_blocks_request_without_header_when_configured(client, monkeypatch):
    monkeypatch.setattr(api, "_API_KEY", "secret-123")
    resp = client.get("/api/v1/task/some-id")
    assert resp.status_code == 401


def test_api_key_allows_request_with_correct_header(client, monkeypatch):
    monkeypatch.setattr(api, "_API_KEY", "secret-123")
    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: types.SimpleNamespace(state="PENDING", info=None, result=None))
    resp = client.get("/api/v1/task/some-id", headers={"X-API-Key": "secret-123"})
    assert resp.status_code == 200


def test_api_key_allows_request_with_query_param_for_download_links(client, monkeypatch):
    """`window.location.href` (tải file trực tiếp trên Web App) không set được header,
    nên endpoint GET tải file phải chấp nhận cả `?api_key=` trên query string."""
    monkeypatch.setattr(api, "_API_KEY", "secret-123")
    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: types.SimpleNamespace(state="PENDING", info=None, result=None))
    resp = client.get("/api/v1/task/some-id?api_key=secret-123")
    assert resp.status_code == 200


def test_task_status_pending(client, monkeypatch):
    class _Pending:
        state = "PENDING"

    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: _Pending())
    resp = client.get("/api/v1/task/some-id")
    assert resp.status_code == 200
    assert resp.json()["status"] == "Processing"


def test_task_status_success(client, monkeypatch):
    class _Success:
        state = "SUCCESS"
        result = {"excel_path": "boq.xlsx"}

    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: _Success())
    resp = client.get("/api/v1/task/some-id")
    body = resp.json()
    assert body["status"] == "success"
    assert body["result"] == {"excel_path": "boq.xlsx"}


def test_task_status_failure(client, monkeypatch):
    class _Failure:
        state = "FAILURE"
        info = "boom"

    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: _Failure())
    resp = client.get("/api/v1/task/some-id")
    body = resp.json()
    assert body["status"] == "error"
    assert "boom" in body["logs"][0]


def test_task_status_progress_reports_processing_with_custom_logs(client, monkeypatch):
    """Trước khi thêm state PROGRESS, `elif state != 'FAILURE'` sẽ coi state này là
    'success' giả (xem comment ở `_task_status_payload` trong src/api.py)."""
    class _Progress:
        state = "PROGRESS"
        info = {"logs": ["Đang đọc bản vẽ: drawing.dxf"]}

    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: _Progress())
    resp = client.get("/api/v1/task/some-id")
    body = resp.json()
    assert body["status"] == "Processing"
    assert body["logs"] == ["Đang đọc bản vẽ: drawing.dxf"]


class _FakeWebSocket:
    """Double tối giản cho `WebSocket` — chỉ cần đủ để `ws_task_status` gọi được, không
    cần dựng cả stack ASGI/transport thật (TestClient.websocket_connect bị treo trong môi
    trường sandbox này, không liên quan tới logic đang kiểm tra)."""

    def __init__(self):
        self.sent = []

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self):
        pass


class _MutableAsyncResult:
    """`ws_task_status` gọi `AsyncResult(...)` đúng 1 lần rồi giữ nguyên object đó suốt
    vòng lặp — giống hệt Celery thật, nơi `.state`/`.info`/`.result` là property tự tra
    lại backend mỗi lần đọc chứ không phải snapshot. Double ở đây phải MUTATE cùng 1
    object qua các state thay vì thay cả object, nếu không vòng lặp production sẽ không
    bao giờ thấy state mới (đây là lỗi thật suýt lọt qua bản nháp đầu của test này)."""

    def __init__(self):
        self.state = "PENDING"
        self.info = None
        self.result = None


def test_ws_task_status_pushes_updates_then_closes_on_success(monkeypatch):
    fake_result = _MutableAsyncResult()
    states = iter([
        ("PROGRESS", {"logs": ["Đang xử lý..."]}, None),
        ("SUCCESS", None, {"excel_path": "boq.xlsx"}),
    ])

    async def _fake_sleep(_seconds):
        state, info, result = next(states, (fake_result.state, fake_result.info, fake_result.result))
        fake_result.state, fake_result.info, fake_result.result = state, info, result

    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: fake_result)
    monkeypatch.setattr(api, "_WS_POLL_SLEEP", _fake_sleep)

    ws = _FakeWebSocket()
    asyncio.run(api.ws_task_status(ws, "some-id"))

    assert [m["status"] for m in ws.sent] == ["Processing", "Processing", "success"]
    assert ws.sent[-1]["result"] == {"excel_path": "boq.xlsx"}


def test_download_returns_error_when_task_not_successful(client, monkeypatch):
    class _NotDone:
        state = "PENDING"

    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: _NotDone())
    resp = client.get("/api/v1/download/some-id")
    assert resp.json() == {"error": "File not found"}


def test_download_returns_file_when_task_succeeded_and_file_exists(client, monkeypatch, tmp_path):
    excel_file = tmp_path / "boq.xlsx"
    excel_file.write_bytes(b"fake excel bytes")

    class _Success:
        state = "SUCCESS"
        result = {"excel_path": str(excel_file)}

    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: _Success())
    resp = client.get("/api/v1/download/some-id")
    assert resp.status_code == 200
    assert resp.content == b"fake excel bytes"


def test_revit_analyze_counts_ducts_and_pipes(client, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    payload = {
        "project_name": "Tòa nhà A",
        "elements": [
            {"category": "Duct Fitting"},
            {"category": "Duct"},
            {"category": "Pipe"},
            {"category": "Wall"},
        ],
    }
    resp = client.post("/api/v1/revit/analyze", json=payload)
    assert resp.status_code == 200
    message = resp.json()["message"]
    assert "Đã nhận 4 cấu kiện" in message
    assert "Ống gió: 2" in message
    assert "Ống nước: 1" in message


def test_revit_analyze_builds_real_boq_from_length_mm(client, tmp_path, monkeypatch):
    """Trước đây /api/v1/revit/analyze chỉ đếm cấu kiện, không hề dùng `length_mm` mà
    plugin Revit gửi lên -> khác hoàn toàn luồng AutoCAD (có bóc khối lượng thật). Nay
    phải cộng dồn length_mm, quy đổi mm->m, cộng hao hụt, và cho tải file Excel về."""
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    payload = {
        "project_name": "Tòa nhà B",
        "wastage_percent": 10,
        "elements": [
            {"category": "Pipe", "name": "Ống uPVC D110", "length_mm": 4000},
            {"category": "Pipe", "name": "Ống uPVC D110", "length_mm": 2000},
            {"category": "Pipe Fitting", "name": "Co 90", "length_mm": None},
            {"category": "Pipe Fitting", "name": "Co 90"},
        ],
    }
    resp = client.post("/api/v1/revit/analyze", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "boq_filename" in body
    assert "Tải về" in body["message"]

    download_resp = client.get(f"/api/v1/revit/download/{body['boq_filename']}")
    assert download_resp.status_code == 200

    import io
    import pandas as pd
    df = pd.read_excel(io.BytesIO(download_resp.content))
    pipe_row = df[df["Hạng mục"] == "Ống uPVC D110"].iloc[0]
    assert pipe_row["Đơn vị"] == "m"
    # (4000 + 2000) mm = 6 m, cộng 10% hao hụt = 6.6 m
    assert pipe_row["Khối lượng"] == pytest.approx(6.6, rel=1e-6)

    fitting_row = df[df["Hạng mục"] == "Co 90"].iloc[0]
    assert fitting_row["Đơn vị"] == "Cái"
    assert fitting_row["Khối lượng"] == 2


def test_revit_download_rejects_path_traversal(client, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    # FastAPI tự chặn "%2F" (slash mã hóa) ở tầng routing (404) trước khi vào tới
    # handler; nếu request nào lọt qua được thì os.path.basename()/kiểm tra UPLOAD_DIR
    # trong handler vẫn phải chặn — không có đường nào rò rỉ file ngoài UPLOAD_DIR.
    resp = client.get("/api/v1/revit/download/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code == 404 or resp.json() == {"error": "File not found"}


def test_autocad_analyze_reports_missing_file(client):
    resp = client.post(
        "/api/v1/autocad/analyze",
        json={"project_name": "Dự án X", "file_path": "/nonexistent/path.dwg"},
    )
    body = resp.json()
    assert body["status"] == "error"
    assert "Không tìm thấy file" in body["message"]


def test_autocad_analyze_queues_task_when_file_exists(client, tmp_path):
    dwg = tmp_path / "model.dwg"
    dwg.write_bytes(b"fake dwg")

    resp = client.post(
        "/api/v1/autocad/analyze",
        json={"project_name": "Dự án X", "file_path": str(dwg)},
    )
    body = resp.json()
    assert body["status"] == "success"
    assert body["task_id"] == "fake-task-id-123"
