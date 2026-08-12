"""Regression test cho bug đơn vị mm/m trong `auto_quantity_takeoff` (qs_tools.py):
dòng khối lượng ống/dây từng bị ghi thẳng giá trị mm nhưng gắn nhãn "m" (sai gấp 1000
lần) — xem review tiêu chuẩn bản vẽ/BOQ."""
import ezdxf
import pandas as pd
import pytest

from src.tools import auto_quantity_takeoff
from src.workspace import resolve_safe_path, set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


def test_pipe_length_is_converted_from_mm_to_m(workspace):
    """1 đoạn thẳng dài đúng 6000 đơn vị bản vẽ (mm, khớp DEFAULT_PIPE_STOCK_LENGTH)
    phải ra đúng 6.0 m trong bảng BOQ, KHÔNG PHẢI 6000."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    doc.layers.add("PIPE_UNIT_TEST")
    msp.add_line((0, 0), (6000, 0), dxfattribs={"layer": "PIPE_UNIT_TEST"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    auto_quantity_takeoff.invoke({
        "file_path": "bv.dxf", "output_excel_path": "kl.xlsx", "wastage_percent": 0,
    })
    df = pd.read_excel(resolve_safe_path("kl.xlsx"))
    row = df[df["Hạng mục"] == "PIPE_UNIT_TEST"].iloc[0]
    assert row["Đơn vị"] == "m"
    assert row["Khối lượng"] == pytest.approx(6.0, rel=1e-6)
