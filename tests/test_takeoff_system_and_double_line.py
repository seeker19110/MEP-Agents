"""Đợt rà soát thứ ba: nội dung KHÔNG PHẢI MEPF lẫn vào dự toán, và tuyến vẽ 2 nét song song.

1. Bản vẽ MEPF thật luôn kèm nền kiến trúc (tường, trục định vị, cửa) và lớp trình bày
   (đường kích thước, ghi chú). Tool cộng chiều dài MỌI layer, nên bảng dự toán ra những
   dòng như "A-WALL — 50 m" và thậm chí "Măng sông (nối ống) - DIM — 8 Cái".
2. Ống gió/ống nước cỡ lớn được thể hiện bằng HAI nét song song (hai mép ống); cộng dồn
   hình học ra gấp đôi chiều dài thật.
"""
import ezdxf
import pandas as pd
import pytest

from src import cad_geometry
from src.tools import auto_quantity_takeoff
from src.workspace import resolve_safe_path, set_workspace_dir

# Phải nạp `src.tools` TRƯỚC (dòng trên) rồi mới lấy hằng số từ `src.qs_tools`: hai module
# import vòng lẫn nhau, nạp `qs_tools` trước sẽ vỡ ở nửa chừng khởi tạo. Xem ghi chú cùng
# lý do ở cuối `src/qs_tools.py`.
from src.qs_tools import UNKNOWN_SYSTEM_LABEL  # noqa: E402


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


def _takeoff(**kwargs):
    params = {"file_path": "bv.dxf", "output_excel_path": "kl.xlsx", "wastage_percent": 0}
    params.update(kwargs)
    result = auto_quantity_takeoff.invoke(params)
    return result, pd.read_excel(resolve_safe_path(params["output_excel_path"]))


def _drawing_with_architecture():
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for layer in ("A-WALL", "TRUC-DINH-VI", "DIM", "M-SAD"):
        doc.layers.add(layer)
        msp.add_line((0, 0), (50000, 0), dxfattribs={"layer": layer})
    doc.blocks.new("CUA_DI_800")
    msp.add_blockref("CUA_DI_800", (0, 0))
    doc.saveas(resolve_safe_path("bv.dxf"))


def test_non_mep_layers_are_flagged_in_the_system_column(workspace):
    _drawing_with_architecture()
    result, df = _takeoff()

    duct = df[df["Hạng mục"] == "M-SAD"].iloc[0]
    assert duct["Hệ"] == "HVAC"
    for layer in ("A-WALL", "TRUC-DINH-VI", "DIM"):
        assert df[df["Hạng mục"] == layer].iloc[0]["Hệ"] == UNKNOWN_SYSTEM_LABEL
    assert "CẢNH BÁO NGHIÊM TRỌNG" in result
    assert "NỀN KIẾN TRÚC" in result


def test_non_mep_blocks_are_flagged_too(workspace):
    _drawing_with_architecture()
    _, df = _takeoff()
    assert df[df["Hạng mục"] == "CUA_DI_800"].iloc[0]["Hệ"] == UNKNOWN_SYSTEM_LABEL


def test_fitting_rows_inherit_the_system_of_their_layer(workspace):
    """'Măng sông - DIM' phải mang cùng nhãn CHƯA XÁC ĐỊNH để bị lọc cùng dòng tuyến."""
    _drawing_with_architecture()
    _, df = _takeoff()
    dim_fittings = df[df["Hạng mục"].astype(str).str.contains("DIM", regex=False)]
    assert not dim_fittings.empty
    assert (dim_fittings["Hệ"] == UNKNOWN_SYSTEM_LABEL).all()


def test_mep_only_drops_the_architectural_rows(workspace):
    _drawing_with_architecture()
    _, df = _takeoff(mep_only=True)
    assert (df["Hệ"] == "HVAC").all()
    for layer in ("A-WALL", "TRUC-DINH-VI", "DIM", "CUA_DI_800"):
        assert not (df["Hạng mục"] == layer).any()


def test_mep_only_keeps_everything_off_by_default(workspace):
    """Mặc định KHÔNG lọc: layer MEPF thật đặt tên tự do cũng rơi vào nhóm chưa xác định,
    tự loại sẽ thành bóc thiếu âm thầm — đúng thứ đang cố tránh."""
    _drawing_with_architecture()
    _, df = _takeoff()
    assert (df["Hạng mục"] == "A-WALL").any()


def test_mep_only_explains_itself_when_nothing_survives(workspace):
    doc = ezdxf.new(units=4)
    doc.layers.add("LAYER_TU_DAT_TEN")
    doc.modelspace().add_line((0, 0), (9000, 0), dxfattribs={"layer": "LAYER_TU_DAT_TEN"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    result = auto_quantity_takeoff.invoke({
        "file_path": "bv.dxf", "output_excel_path": "kl.xlsx", "mep_only": True,
    })
    assert "mep_only" in result
    assert "standardize_cad_drawing" in result


def test_double_line_duct_is_reported_as_possibly_doubled(workspace):
    """Ống gió 20 m vẽ bằng 2 nét song song bị cộng thành 40 m."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    doc.layers.add("M-SAD")
    msp.add_line((0, 0), (20000, 0), dxfattribs={"layer": "M-SAD"})
    msp.add_line((0, 600), (20000, 600), dxfattribs={"layer": "M-SAD"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    result, df = _takeoff()
    assert "HAI NÉT SONG SONG" in result
    assert "~20.0 m" in result
    # Cảnh báo chứ KHÔNG tự trừ: con số vẫn là tổng hình học thật.
    assert df[df["Hạng mục"] == "M-SAD"].iloc[0]["Khối lượng"] == pytest.approx(40.0)


def test_far_apart_parallel_routes_are_not_reported(workspace):
    """Hai tuyến cách nhau 5 m là hai tuyến riêng, không phải hai mép của một ống."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    doc.layers.add("M-SAD")
    msp.add_line((0, 0), (20000, 0), dxfattribs={"layer": "M-SAD"})
    msp.add_line((0, 5000), (20000, 5000), dxfattribs={"layer": "M-SAD"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    result, _ = _takeoff()
    assert "HAI NÉT SONG SONG" not in result


def test_barely_overlapping_parallel_segments_are_not_reported():
    """Hai đoạn song song chỉ chồng nhau một khúc ngắn thì không phải hai mép một tuyến."""
    segments = [
        {"layer": "P", "start": (0, 0, 0), "end": (10000, 0, 0), "length": 10000},
        {"layer": "P", "start": (9000, 300, 0), "end": (19000, 300, 0), "length": 10000},
    ]
    assert cad_geometry.detect_double_line_runs(segments) == {}


def test_perpendicular_segments_are_not_reported():
    segments = [
        {"layer": "P", "start": (0, 0, 0), "end": (10000, 0, 0), "length": 10000},
        {"layer": "P", "start": (0, 0, 0), "end": (0, 10000, 0), "length": 10000},
    ]
    assert cad_geometry.detect_double_line_runs(segments) == {}


def test_double_line_detection_reports_the_overlapping_length():
    segments = [
        {"layer": "M-SAD", "start": (0, 0, 0), "end": (10000, 0, 0), "length": 10000},
        {"layer": "M-SAD", "start": (0, 600, 0), "end": (10000, 600, 0), "length": 10000},
    ]
    result = cad_geometry.detect_double_line_runs(segments)
    assert result["M-SAD"] == pytest.approx(10000.0)
