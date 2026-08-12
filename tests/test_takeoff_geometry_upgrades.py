"""Tích hợp cung ARC/bulge, phụ kiện, hao hụt, cảnh báo scale, và DWG/XREF vào
`auto_quantity_takeoff` — các lỗ hổng đã nêu trong đợt rà soát bóc khối lượng QS."""
import math
import os

import ezdxf
import pandas as pd
import pytest

from src.tools import auto_quantity_takeoff
from src.workspace import resolve_safe_path, set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


def test_takeoff_counts_arc_length_correctly(workspace):
    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.layers.add("PIPE_ARC")
    msp.add_arc(center=(0, 0), radius=1000, start_angle=0, end_angle=90,
                dxfattribs={"layer": "PIPE_ARC"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    auto_quantity_takeoff.invoke({
        "file_path": "bv.dxf", "output_excel_path": "kl.xlsx", "wastage_percent": 0,
    })
    df = pd.read_excel(resolve_safe_path("kl.xlsx"))
    row = df[df["Hạng mục"] == "PIPE_ARC"].iloc[0]
    # Bán kính 1000 đơn vị bản vẽ (mm) -> chiều dài cung quy đổi ra m.
    assert row["Khối lượng"] == pytest.approx((math.pi * 1000 / 2) / 1000.0, rel=1e-3)


def test_takeoff_reports_fittings_as_separate_rows(workspace):
    """Ống vẽ bằng LINE thuần (không có Block phụ kiện) vẫn phải ra được số phụ kiện."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.layers.add("PIPE_L")
    msp.add_line((0, 0), (5000, 0), dxfattribs={"layer": "PIPE_L"})
    msp.add_line((5000, 0), (5000, 5000), dxfattribs={"layer": "PIPE_L"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    result = auto_quantity_takeoff.invoke({"file_path": "bv.dxf", "output_excel_path": "kl.xlsx"})
    df = pd.read_excel(resolve_safe_path("kl.xlsx"))
    assert (df["Hạng mục"] == "Co (elbow) - PIPE_L").any()
    assert "hình học" in result.lower() or "Co" in result


def test_takeoff_applies_wastage_to_pipe_length_but_not_block_count(workspace):
    """Hao hụt vật tư áp cho khối lượng ống/dây; số lượng thiết bị (Block) không bị nhân
    hao hụt vì thiết bị đếm theo cái, không hao hụt như vật liệu cắt nối."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.layers.add("PIPE_W")
    msp.add_line((0, 0), (1000, 0), dxfattribs={"layer": "PIPE_W"})
    blk = doc.blocks.new("SOCKET")
    blk.add_circle((0, 0), radius=10)
    msp.add_blockref("SOCKET", (10, 10))
    doc.saveas(resolve_safe_path("bv.dxf"))

    auto_quantity_takeoff.invoke({
        "file_path": "bv.dxf", "output_excel_path": "kl.xlsx", "wastage_percent": 8,
    })
    df = pd.read_excel(resolve_safe_path("kl.xlsx"))
    pipe_row = df[df["Hạng mục"] == "PIPE_W"].iloc[0]
    socket_row = df[df["Hạng mục"] == "SOCKET"].iloc[0]
    # 1000 đơn vị bản vẽ (mm) -> 1 m, rồi cộng 8% hao hụt.
    assert pipe_row["Khối lượng"] == pytest.approx(1 * 1.08, rel=1e-3)
    assert socket_row["Khối lượng"] == 1


def test_takeoff_warns_about_scaled_blocks(workspace):
    """Đèn 600x600 chèn ở scale 1.5 vẫn đếm đúng số lượng nhưng phải cảnh báo kích thước
    thực tế khác chuẩn, thay vì âm thầm coi là đúng chuẩn."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    blk = doc.blocks.new("LIGHT_PANEL")
    blk.add_circle((0, 0), radius=10)
    msp.add_blockref("LIGHT_PANEL", (0, 0), dxfattribs={"xscale": 1.5, "yscale": 1.5})
    doc.saveas(resolve_safe_path("bv.dxf"))

    result = auto_quantity_takeoff.invoke({"file_path": "bv.dxf", "output_excel_path": "kl.xlsx"})
    assert "LỆCH TỶ LỆ" in result
    assert "LIGHT_PANEL" in result
    assert "1.5" in result

    df = pd.read_excel(resolve_safe_path("kl.xlsx"))
    assert df[df["Hạng mục"] == "LIGHT_PANEL"].iloc[0]["Khối lượng"] == 1  # số lượng vẫn đúng


def test_takeoff_does_not_warn_when_no_block_is_scaled(workspace):
    doc = ezdxf.new()
    msp = doc.modelspace()
    blk = doc.blocks.new("LIGHT_PANEL")
    blk.add_circle((0, 0), radius=10)
    msp.add_blockref("LIGHT_PANEL", (0, 0))
    doc.saveas(resolve_safe_path("bv.dxf"))

    result = auto_quantity_takeoff.invoke({"file_path": "bv.dxf", "output_excel_path": "kl.xlsx"})
    assert "LỆCH TỶ LỆ" not in result


def test_takeoff_reads_dwg_and_notes_conversion(monkeypatch, workspace):
    dwg_path = workspace / "bv.dwg"
    dwg_path.write_bytes(b"FAKE DWG")

    def fake_convert(path, output_dir=None, timeout=180):
        out = os.path.join(output_dir, "bv.dxf")
        doc = ezdxf.new()
        msp = doc.modelspace()
        doc.layers.add("PIPE_DWG")
        msp.add_line((0, 0), (500, 0), dxfattribs={"layer": "PIPE_DWG"})
        doc.saveas(out)
        return out

    from src import cad_loader
    monkeypatch.setattr(cad_loader, "convert_dwg_to_dxf", fake_convert)

    result = auto_quantity_takeoff.invoke({
        "file_path": "bv.dwg", "output_excel_path": "kl.xlsx", "wastage_percent": 0,
    })
    assert "chuyển .dwg sang .dxf" in result
    df = pd.read_excel(resolve_safe_path("kl.xlsx"))
    assert df[df["Hạng mục"] == "PIPE_DWG"].iloc[0]["Khối lượng"] == pytest.approx(0.5)


def test_takeoff_reports_missing_xref_file(workspace):
    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.layers.add("PIPE_MAIN")
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "PIPE_MAIN"})
    doc.blocks.new("XREF1", dxfattribs={"flags": 4, "xref_path": "khong_ton_tai.dxf"})
    msp.add_blockref("XREF1", (0, 0))
    doc.saveas(resolve_safe_path("bv.dxf"))

    result = auto_quantity_takeoff.invoke({"file_path": "bv.dxf", "output_excel_path": "kl.xlsx"})
    assert "KHÔNG tìm thấy file XREF" in result
    assert "khong_ton_tai.dxf" in result


def test_takeoff_merges_xref_content_into_totals(workspace):
    xref_doc = ezdxf.new()
    xref_msp = xref_doc.modelspace()
    xref_doc.layers.add("PIPE_XREF")
    xref_msp.add_line((0, 0), (300, 0), dxfattribs={"layer": "PIPE_XREF"})
    xref_doc.saveas(resolve_safe_path("phu.dxf"))

    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.blocks.new("XREF1", dxfattribs={"flags": 4, "xref_path": "phu.dxf"})
    msp.add_blockref("XREF1", (0, 0))
    doc.saveas(resolve_safe_path("bv.dxf"))

    result = auto_quantity_takeoff.invoke({
        "file_path": "bv.dxf", "output_excel_path": "kl.xlsx", "wastage_percent": 0,
    })
    assert "Đã gộp nội dung XREF" in result
    df = pd.read_excel(resolve_safe_path("kl.xlsx"))
    assert (df["Hạng mục"] == "PIPE_XREF").any()
    assert df[df["Hạng mục"] == "PIPE_XREF"].iloc[0]["Khối lượng"] == pytest.approx(0.3)
