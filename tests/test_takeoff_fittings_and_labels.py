"""Đợt rà soát thứ tư: suy phụ kiện sai số lượng, gộp thiết bị theo mã hiệu, và chữ MTEXT.

1. Co (elbow): mỗi mắt xấp xỉ của đường cong bị đếm thành một cái co — một spline duy nhất
   ra 1654 cái co (lỗi phát sinh khi thêm đo SPLINE/ELLIPSE ở đợt trước).
2. Măng sông: chỉ đếm cho đoạn dài hơn một cây ống, trong khi tuyến thật luôn được vẽ
   thành polyline nhiều vertex ngắn — tuyến 100 m ra 0 mối nối.
3. Thiết bị cùng chủng loại nhưng khác MÃ HIỆU bị tách thành mỗi cái một dòng.
4. MTEXT mang mã định dạng của CAD làm tên hạng mục ra đầy ký tự điều khiển.
"""
import ezdxf
import pandas as pd
import pytest

from src import cad_geometry
from src.tools import auto_quantity_takeoff
from src.workspace import resolve_safe_path, set_workspace_dir

# Nạp `src.tools` trước rồi mới lấy hằng/hàm từ `src.qs_tools` — hai module import vòng nhau.
from src.qs_tools import aggregate_block_attributes  # noqa: E402


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


def _takeoff(**kwargs):
    params = {"file_path": "bv.dxf", "output_excel_path": "kl.xlsx", "wastage_percent": 0}
    params.update(kwargs)
    result = auto_quantity_takeoff.invoke(params)
    return result, pd.read_excel(resolve_safe_path(params["output_excel_path"]))


def _qty(df, item):
    rows = df[df["Hạng mục"] == item]
    return 0 if rows.empty else rows.iloc[0]["Khối lượng"]


def test_spline_counts_as_a_single_elbow(workspace):
    """Cả đường cong là MỘT chỗ đổi hướng, không phải mỗi mắt xấp xỉ một cái co."""
    doc = ezdxf.new(units=4)
    doc.layers.add("P-SPL")
    doc.modelspace().add_spline([(0, 0), (10000, 5000), (20000, 0)],
                                dxfattribs={"layer": "P-SPL"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    assert _qty(df, "Co (elbow) - P-SPL") == 1


def test_long_route_drawn_with_short_segments_gets_couplings(workspace):
    """Tuyến 100 m vẽ thành 50 đoạn 2 m: ống bán theo cây 6 m nên phải có 16 mối nối."""
    doc = ezdxf.new(units=4)
    doc.layers.add("P-LONG")
    doc.modelspace().add_lwpolyline([(i * 2000, 0) for i in range(51)],
                                    dxfattribs={"layer": "P-LONG"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    assert _qty(df, "P-LONG") == pytest.approx(100.0)
    assert _qty(df, "Măng sông (nối ống) - P-LONG") == 16


def test_scattered_short_pipes_get_no_couplings(workspace):
    """Nhưng 10 mẩu ống 2 m rời rạc thì KHÔNG có mối nối nào — mỗi mẩu ngắn hơn một cây."""
    doc = ezdxf.new(units=4)
    doc.layers.add("P-VUN")
    msp = doc.modelspace()
    for i in range(10):
        msp.add_line((i * 10000, 0), (i * 10000 + 2000, 0), dxfattribs={"layer": "P-VUN"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    assert _qty(df, "P-VUN") == pytest.approx(20.0)
    assert _qty(df, "Măng sông (nối ống) - P-VUN") == 0


def test_connected_run_lengths_groups_by_continuity():
    segments = [
        {"layer": "P", "start": (0, 0, 0), "end": (1000, 0, 0), "length": 1000},
        {"layer": "P", "start": (1000, 0, 0), "end": (2000, 0, 0), "length": 1000},
        {"layer": "P", "start": (50000, 0, 0), "end": (50500, 0, 0), "length": 500},
    ]
    assert sorted(cad_geometry._connected_run_lengths(segments, 1.0)) == [500.0, 2000.0]


def _lights(doc, powers):
    block = doc.blocks.new("DEN_LED_600")
    block.add_attdef("TAG", (0, 0))
    block.add_attdef("CONGSUAT", (0, 100))
    msp = doc.modelspace()
    for i, power in enumerate(powers):
        ref = msp.add_blockref("DEN_LED_600", (i * 3000, 0))
        ref.add_auto_attribs({"TAG": "L-%02d" % i, "CONGSUAT": power})


def test_devices_with_unique_tags_are_merged_into_one_row(workspace):
    doc = ezdxf.new(units=4)
    _lights(doc, ["36W"] * 5)
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    rows = df[df["Hạng mục"] == "DEN_LED_600"]
    assert len(rows) == 1
    assert rows.iloc[0]["Khối lượng"] == 5
    # Mã hiệu không bị vứt đi — vẫn tra được trong ghi chú.
    assert "L-00" in str(rows.iloc[0]["Ghi chú"])


def test_different_specifications_stay_on_separate_rows(workspace):
    """Gộp theo mã hiệu thì được, gộp mất luôn thông số kỹ thuật thì KHÔNG: 36W và 18W là
    hai chủng loại khác nhau, đơn giá khác nhau."""
    doc = ezdxf.new(units=4)
    _lights(doc, ["36W", "36W", "36W", "18W", "18W"])
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    rows = df[df["Hạng mục"] == "DEN_LED_600"]
    assert len(rows) == 2
    assert sorted(rows["Khối lượng"].tolist()) == [2, 3]


def test_aggregate_keeps_single_instance_attributes():
    """Block chỉ chèn một lần: không đủ căn cứ nói thuộc tính nào là mã định danh."""
    counts = {("BOM_PCCC", '{"MODEL": "NFPA-20"}'): 1}
    aggregated, notes = aggregate_block_attributes(counts)
    assert aggregated == {("BOM_PCCC", '{"MODEL": "NFPA-20"}'): 1}
    assert notes == {}


def test_mtext_formatting_codes_are_stripped(workspace):
    """Tên hạng mục phải là chữ người đọc được, không phải mã định dạng của CAD — tên rác
    còn làm `calc_boq_cost` không khớp nổi từ khóa đơn giá."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    doc.layers.add("P-CN")
    msp.add_line((0, 0), (10000, 0), dxfattribs={"layer": "P-CN"})
    mtext = msp.add_mtext(r"{\fArial|b1;Ống uPVC \pxqc;Ø110}", dxfattribs={"layer": "GHI-CHU"})
    mtext.set_location((5000, 200))
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    names = df["Hạng mục"].astype(str).tolist()
    assert any(name.startswith("Ống uPVC Ø110") for name in names)
    assert not any("\\f" in name or "{" in name for name in names)


def test_text_escape_codes_are_decoded(workspace):
    """TEXT dùng mã thoát riêng: `%%c` chính là ký hiệu đường kính Ø."""
    doc = ezdxf.new(units=4)
    text = doc.modelspace().add_text("Ong thep %%c114")
    assert cad_geometry.plain_entity_text(text) == "Ong thep Ø114"
