"""Đọc mô hình BIM định dạng IFC (src/bim_tools.read_ifc_model).

Không dựng file IFC thật bằng ifcopenshell.api (tốn công, không cần thiết) — model trả
về từ `ifcopenshell.open` được giả lập để kiểm tra luồng trích xuất & xuất Excel.
"""
import os

import pandas as pd
import pytest

from src.bim_tools import read_ifc_model
from src.workspace import set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


def test_reports_missing_file(workspace):
    result = read_ifc_model.invoke({"file_path": "khong_ton_tai.ifc"})
    assert "Không tìm thấy file" in result


class _FakeEntity:
    def __init__(self, guid, name, type_name, props=None):
        self.GlobalId = guid
        self.Name = name
        self._type = type_name
        self.IsDefinedBy = []

    def is_a(self):
        return self._type


class _FakeModel:
    def __init__(self, entities):
        self._entities = entities

    def by_type(self, type_name):
        if type_name == "IfcBuildingElement":
            return [e for e in self._entities if e._type != "IfcDistributionElement"]
        if type_name == "IfcDistributionElement":
            return [e for e in self._entities if e._type == "IfcDistributionElement"]
        return []


def test_extracts_elements_and_writes_excel(workspace, monkeypatch):
    import ifcopenshell

    ifc_path = os.path.join(str(workspace), "model.ifc")
    with open(ifc_path, "w") as f:
        f.write("fake ifc content")

    entities = [
        _FakeEntity("GUID-1", "Duct-01", "IfcDistributionElement"),
        _FakeEntity("GUID-2", "Wall-01", "IfcBuildingElement"),
    ]
    monkeypatch.setattr(ifcopenshell, "open", lambda path: _FakeModel(entities))

    result = read_ifc_model.invoke({"file_path": "model.ifc"})
    assert "Tổng số đối tượng tìm thấy: 2" in result

    out_path = os.path.join(str(workspace), "ifc_report.xlsx")
    assert os.path.exists(out_path)
    df = pd.read_excel(out_path)
    assert set(df["GUID"]) == {"GUID-1", "GUID-2"}


def test_reports_when_no_relevant_entities_found(workspace, monkeypatch):
    import ifcopenshell

    ifc_path = os.path.join(str(workspace), "empty.ifc")
    with open(ifc_path, "w") as f:
        f.write("fake ifc content")

    monkeypatch.setattr(ifcopenshell, "open", lambda path: _FakeModel([]))
    result = read_ifc_model.invoke({"file_path": "empty.ifc"})
    assert "Không tìm thấy thiết bị" in result


def test_generic_error_is_reported_gracefully(workspace, monkeypatch):
    import ifcopenshell

    ifc_path = os.path.join(str(workspace), "bad.ifc")
    with open(ifc_path, "w") as f:
        f.write("fake ifc content")

    def _boom(path):
        raise RuntimeError("corrupt file")

    monkeypatch.setattr(ifcopenshell, "open", _boom)
    result = read_ifc_model.invoke({"file_path": "bad.ifc"})
    assert "Lỗi đọc file IFC" in result
