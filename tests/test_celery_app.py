"""Celery task xử lý bóc tách khối lượng phân tán (src/celery_app.py).

Chạy task đồng bộ (`.run(...)`, không qua broker Redis thật) để kiểm tra logic nghiệp
vụ bên trong, tách biệt khỏi hạ tầng hàng đợi.
"""
import os

import ezdxf
import pytest

from src.celery_app import parse_cad_to_db_task
from src.workspace import set_workspace_dir


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    set_workspace_dir(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _make_dxf(path):
    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.layers.add("HVAC_DUCT") if "HVAC_DUCT" not in doc.layers else None
    msp.add_lwpolyline([(0, 0), (1000, 0)], dxfattribs={"layer": "HVAC_DUCT"})
    doc.saveas(path)


def test_parse_cad_to_db_task_returns_success_payload(workspace):
    dwg_path = os.path.join(str(workspace), "drawing.dxf")
    _make_dxf(dwg_path)

    result = parse_cad_to_db_task.run(dwg_path, user_id="tester")

    assert result["status"] == "success"
    assert result["file"] == dwg_path
    assert result["excel_path"].endswith(".xlsx")
    assert os.path.exists(result["excel_path"])
    assert "logs" in result
