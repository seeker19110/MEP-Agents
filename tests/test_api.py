"""FastAPI Cloud API endpoints (src/api.py).

`parse_cad_to_db_task.delay(...)` is mocked everywhere — it would otherwise try to
publish to a real Redis broker, which isn't available in the test environment.
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
