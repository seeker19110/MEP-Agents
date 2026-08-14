"""Workspace riêng từng người dùng trong Worker.

Trước đây Worker ghi chung vào `uploads/` và `data/boq/` cho mọi người: bản vẽ và bảng
khối lượng của khách này nằm cạnh khách kia, và hai người tải lên hai file trùng tên là
ghi đè nhau trong im lặng. Tham số `user_id` vốn có sẵn trong chữ ký task nhưng bị bỏ đi.
"""
import os
import types

import pytest

from src import celery_app as ca
from src.workspace import (
    get_user_workspace,
    get_workspace_dir,
    resolve_safe_path,
    safe_user_dirname,
    set_workspace_dir,
)


@pytest.fixture(autouse=True)
def restore_workspace():
    old = get_workspace_dir()
    yield
    set_workspace_dir(old)


# --- Làm sạch tên thư mục ---

def test_traversal_in_user_id_cannot_escape():
    """`sub` của JWT do người tạo tài khoản đặt — phải coi là dữ liệu không tin cậy."""
    name = safe_user_dirname("../../etc/passwd")
    assert "/" not in name and ".." not in name


def test_similar_names_do_not_collide():
    """Chỉ lọc ký tự thì "a/b" và "a_b" thành cùng một thư mục — hai người dùng chung
    workspace mà không ai biết. Băm ở cuối tách chúng ra."""
    assert safe_user_dirname("a/b") != safe_user_dirname("a_b")


def test_same_user_is_stable():
    assert safe_user_dirname("an") == safe_user_dirname("an")


def test_empty_identity_still_gets_a_directory():
    assert safe_user_dirname("") and safe_user_dirname(None)


def test_user_workspaces_are_separate(tmp_path):
    assert get_user_workspace("an") != get_user_workspace("binh")
    assert os.path.isdir(get_user_workspace("an"))


def test_workspace_confines_file_access():
    """Đặt workspace theo người dùng xong thì `resolve_safe_path` phải chặn đường ra."""
    set_workspace_dir(get_user_workspace("an"))
    with pytest.raises(ValueError, match="ngoài phạm vi"):
        resolve_safe_path("../binh-abc12345/boq/secret.xlsx")


# --- Task chạy trong workspace riêng ---

def _run_task(monkeypatch, dwg_path, user_id, captured):
    """Chạy thân task với `auto_quantity_takeoff` giả, ghi lại đường dẫn nó nhận được."""
    fake_tool = types.SimpleNamespace(
        invoke=lambda payload: captured.update(payload) or "đã bóc xong"
    )
    import src.tools as tools_mod
    monkeypatch.setattr(tools_mod, "auto_quantity_takeoff", fake_tool)
    monkeypatch.setattr(ca, "_publish_event", lambda *a, **kw: None)

    # `.run()` là đường Celery cung cấp để gọi thân task trực tiếp; với `bind=True` nó tự
    # truyền `self`, nên không dựng task giả bằng tay.
    return ca.parse_cad_to_db_task.run(str(dwg_path), user_id=user_id)


def test_task_writes_into_the_user_workspace(tmp_path, monkeypatch):
    dwg = tmp_path / "ban_ve.dxf"
    dwg.write_bytes(b"noi dung")
    captured = {}

    result = _run_task(monkeypatch, dwg, "an", captured)

    ws = get_user_workspace("an")
    assert result["excel_path"].startswith(ws), "BOQ phải nằm trong workspace của 'an'"
    assert captured["file_path"].startswith(ws), "bản vẽ phải được đưa vào workspace trước"
    assert os.path.exists(os.path.join(ws, "ban_ve.dxf"))


def test_two_users_same_filename_do_not_overwrite(tmp_path, monkeypatch):
    """Hai khách cùng đặt tên `ban_ve.dxf` phải ra hai file khác nhau, không đè nhau."""
    dwg_a = tmp_path / "a" / "ban_ve.dxf"
    dwg_a.parent.mkdir()
    dwg_a.write_bytes(b"cua an")
    dwg_b = tmp_path / "b" / "ban_ve.dxf"
    dwg_b.parent.mkdir()
    dwg_b.write_bytes(b"cua binh")

    res_a = _run_task(monkeypatch, dwg_a, "an", {})
    res_b = _run_task(monkeypatch, dwg_b, "binh", {})

    assert res_a["excel_path"] != res_b["excel_path"]
    ws_a, ws_b = get_user_workspace("an"), get_user_workspace("binh")
    assert open(os.path.join(ws_a, "ban_ve.dxf"), "rb").read() == b"cua an"
    assert open(os.path.join(ws_b, "ban_ve.dxf"), "rb").read() == b"cua binh"


def test_missing_source_file_reports_clearly(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError):
        _run_task(monkeypatch, tmp_path / "khong-co.dxf", "an", {})
