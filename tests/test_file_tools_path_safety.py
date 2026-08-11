import os
import pytest

from src.workspace import set_workspace_dir
from src.tools import write_excel, read_excel, list_directory


@pytest.fixture
def workspace(tmp_path):
    return set_workspace_dir(str(tmp_path / "session_xyz"))


def test_write_excel_stays_inside_workspace(workspace):
    result = write_excel.invoke({
        "file_path": "bao_cao.xlsx",
        "json_data": '[{"STT": 1, "Vat_tu": "Ong", "KL": 10}]',
    })
    assert "Đã ghi đè/tạo thành công" in result
    assert os.path.exists(os.path.join(workspace, "bao_cao.xlsx"))


def test_write_excel_blocks_path_traversal(workspace, tmp_path):
    outside_marker = tmp_path / "leaked.xlsx"
    result = write_excel.invoke({
        "file_path": "../leaked.xlsx",
        "json_data": '[{"a": 1}]',
    })
    assert "Lỗi ghi Excel" in result
    assert not outside_marker.exists()


def test_read_excel_blocks_path_traversal(workspace):
    result = read_excel.invoke({"file_path": "../../../../etc/passwd"})
    assert "Lỗi đọc Excel" in result


def test_write_then_read_roundtrip(workspace):
    write_excel.invoke({
        "file_path": "roundtrip.xlsx",
        "json_data": '[{"STT": 1, "Vat_tu": "Ong D110", "KL": 25}]',
    })
    result = read_excel.invoke({"file_path": "roundtrip.xlsx"})
    assert "Ong D110" in result


def test_list_directory_reflects_workspace(workspace):
    write_excel.invoke({"file_path": "a.xlsx", "json_data": "[]"})
    result = list_directory.invoke({"path": "."})
    assert "a.xlsx" in result


def test_list_directory_blocks_traversal(workspace):
    result = list_directory.invoke({"path": "../../"})
    assert "Lỗi đọc thư mục" in result
