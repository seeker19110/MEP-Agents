"""Các chốt chặn phát hiện trong đợt rà soát viết lại đặc tả.

Mỗi test ở đây gắn với một mục trong `docs/RA_SOAT_LO_HONG.md`.
"""
import types

import pytest
from fastapi.testclient import TestClient

from src import api


# --- Mục 3: Celery không được nhận pickle ---

def test_celery_does_not_accept_pickle():
    """Nhận pickle = unpickle dữ liệu từ broker = chạy code tùy ý trong Worker.

    Redis trong `docker-compose.yml` không đặt mật khẩu, nên ai vào được mạng nội bộ
    của Compose là đẩy được message vào hàng đợi.
    """
    from src.celery_app import app as celery_app

    accept = list(celery_app.conf.accept_content or [])
    assert "pickle" not in accept
    assert "json" in accept
    assert celery_app.conf.task_serializer == "json"


# --- Mục 4: endpoint AutoCAD không được thành công cụ dò file ---

@pytest.fixture
def client(monkeypatch):
    fake_task = types.SimpleNamespace(id="fake-task-id-123")
    monkeypatch.setattr(api.parse_cad_to_db_task, "delay", lambda *a, **kw: fake_task)
    return TestClient(api.app)


def test_autocad_analyze_rejects_non_cad_path(client):
    """`/etc/passwd` phải bị chặn vì ĐUÔI FILE, trước cả khi kiểm tra tồn tại — nếu
    không, thông báo "không tìm thấy file" chính là câu trả lời có/không cho mọi đường
    dẫn khách hàng đoán."""
    resp = client.post(
        "/api/v1/autocad/analyze",
        json={"project_name": "X", "file_path": "/etc/passwd"},
    )
    body = resp.json()
    assert body["status"] == "error"
    assert ".dwg/.dxf" in body["message"]


def test_autocad_analyze_strict_mode_confines_to_workspace(client, tmp_path, monkeypatch):
    """Bật `MEP_AGENTS_STRICT_PATHS` thì file ngoài workspace bị từ chối."""
    monkeypatch.setenv("MEP_AGENTS_STRICT_PATHS", "true")
    outside = tmp_path / "ngoai_workspace.dxf"
    outside.write_bytes(b"fake")

    resp = client.post(
        "/api/v1/autocad/analyze",
        json={"project_name": "X", "file_path": str(outside)},
    )
    body = resp.json()
    assert body["status"] == "error"
    assert "ngoài phạm vi làm việc" in body["message"]


def test_autocad_analyze_strict_mode_allows_inside_workspace(client, tmp_path, monkeypatch):
    monkeypatch.setenv("MEP_AGENTS_STRICT_PATHS", "true")
    from src.workspace import set_workspace_dir, get_workspace_dir

    old = get_workspace_dir()
    try:
        set_workspace_dir(str(tmp_path))
        inside = tmp_path / "ban_ve.dxf"
        inside.write_bytes(b"fake")
        resp = client.post(
            "/api/v1/autocad/analyze",
            json={"project_name": "X", "file_path": str(inside)},
        )
        assert resp.json()["status"] == "success"
    finally:
        set_workspace_dir(old)


def test_autocad_analyze_default_mode_keeps_absolute_paths(client, tmp_path, monkeypatch):
    """Mặc định TẮT chế độ nghiêm ngặt — kịch bản plugin chạy cùng máy vẫn phải chạy."""
    monkeypatch.delenv("MEP_AGENTS_STRICT_PATHS", raising=False)
    dwg = tmp_path / "model.dwg"
    dwg.write_bytes(b"fake dwg")
    resp = client.post(
        "/api/v1/autocad/analyze",
        json={"project_name": "X", "file_path": str(dwg)},
    )
    assert resp.json()["status"] == "success"


# --- Mục 5: QS Auditor chỉ được đọc, không được sửa ---

def test_qs_auditor_role_has_scoped_readonly_toolset():
    """Kiểm toán viên mà cầm `edit_cad`/`execute_python_code` thì là tự sửa bài mình chấm.

    Trước đây vai trò này không có trong `TOOLS_BY_ROLE` nên rơi vào nhánh mặc định và
    nhận TOÀN BỘ tool.
    """
    from src.tools import get_tools_for_role, tools

    for alias in ("qs_auditor", "QSAuditor", "qsauditor"):
        role_tools = get_tools_for_role(alias)
        names = {t.name for t in role_tools}
        assert len(role_tools) < len(tools), f"{alias} vẫn nhận toàn bộ tool"
        forbidden = {"edit_cad", "write_cad", "execute_python_code", "auto_quantity_takeoff"}
        assert not (names & forbidden), f"{alias} cầm tool ghi/sửa: {names & forbidden}"
        # Vẫn phải đủ đồ nghề để kiểm toán thật.
        assert {"qs_audit_checklist", "compare_boq", "lookup_unit_price"} <= names


def test_known_roles_all_have_explicit_toolsets():
    """Mọi vai trò có node trong graph phải được khai báo tường minh.

    Rơi vào nhánh mặc định là im lặng nhận 90 tool — không lỗi, không cảnh báo, chỉ đắt
    và sai quyền. Đúng loại thiếu sót mà dự án này gọi là "bỏ sót âm thầm".
    """
    from src.tools import get_tools_for_role, tools

    for role in ("mechanical", "electrical", "plumbing", "firefighting",
                 "qs", "qs_auditor", "cad", "bim"):
        assert len(get_tools_for_role(role)) < len(tools), f"{role} chưa có bộ tool riêng"
