"""Sai lệch từ BẢN VẼ tới BẢNG KHỐI LƯỢNG: quy đổi đơn vị bản vẽ, bung ruột Block và
đếm đủ lưới MINSERT.

Ba nguồn sai lệch còn sót lại sau các đợt trước, đều là sai ÂM THẦM (bảng Excel vẫn ra
đầy đủ dòng, chỉ có con số là sai):

1. Bản vẽ vẽ bằng MÉT bị chia cứng cho 1000 -> khối lượng nhỏ hơn thực tế 1000 lần.
2. Ống/dây vẽ BÊN TRONG Block không được cộng một mét nào.
3. Một entity MINSERT (dàn đèn/dàn đầu phun) chỉ được đếm là 1 thiết bị.
"""
import ezdxf
import pandas as pd
import pytest

from src import cad_units
from src.tools import auto_quantity_takeoff
from src.workspace import resolve_safe_path, set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


def _takeoff(**kwargs):
    params = {"file_path": "bv.dxf", "output_excel_path": "kl.xlsx", "wastage_percent": 0}
    params.update(kwargs)
    result = auto_quantity_takeoff.invoke(params)
    return result, pd.read_excel(resolve_safe_path(params["output_excel_path"]))


def test_meter_drawing_is_converted_with_the_right_factor(workspace):
    """Bản vẽ khai INSUNITS = Met: tuyến dài 6 đơn vị phải ra 6 m, không phải 0.006 m."""
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 6
    doc.layers.add("PIPE_M")
    doc.modelspace().add_line((0, 0), (6, 0), dxfattribs={"layer": "PIPE_M"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    row = df[df["Hạng mục"] == "PIPE_M"].iloc[0]
    assert row["Đơn vị"] == "m"
    assert row["Khối lượng"] == pytest.approx(6.0, rel=1e-6)


def test_millimeter_drawing_still_converts_as_before(workspace):
    """Không phá hành vi cũ: bản vẽ mm vẫn ra đúng số mét."""
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4
    doc.layers.add("PIPE_MM")
    doc.modelspace().add_line((0, 0), (6000, 0), dxfattribs={"layer": "PIPE_MM"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    assert df[df["Hạng mục"] == "PIPE_MM"].iloc[0]["Khối lượng"] == pytest.approx(6.0, rel=1e-6)


def test_drawing_unit_parameter_overrides_wrong_header(workspace):
    """Header sai (chuyện thường sau nhiều lần convert) — kỹ sư khai `drawing_unit` là thắng."""
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4  # khai mm nhưng thực tế vẽ bằng mét
    doc.layers.add("PIPE_OVR")
    doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": "PIPE_OVR"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff(drawing_unit="m")
    assert df[df["Hạng mục"] == "PIPE_OVR"].iloc[0]["Khối lượng"] == pytest.approx(10.0, rel=1e-6)


def test_unitless_drawing_warns_instead_of_silently_assuming(workspace):
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 0
    doc.layers.add("PIPE_U")
    doc.modelspace().add_line((0, 0), (5000, 0), dxfattribs={"layer": "PIPE_U"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    result, _ = _takeoff()
    assert "CẢNH BÁO NGHIÊM TRỌNG" in result
    assert "drawing_unit" in result


def test_pipe_drawn_inside_a_block_is_counted(workspace):
    """Cụm ống đóng gói trong Block: trước đây bóc ra 0 m."""
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4
    doc.layers.add("PIPE_IN_BLOCK")
    block = doc.blocks.new(name="CUM_WC")
    block.add_line((0, 0), (8000, 0), dxfattribs={"layer": "PIPE_IN_BLOCK"})
    doc.modelspace().add_blockref("CUM_WC", (0, 0))
    doc.saveas(resolve_safe_path("bv.dxf"))

    result, df = _takeoff()
    row = df[df["Hạng mục"] == "PIPE_IN_BLOCK"].iloc[0]
    assert row["Khối lượng"] == pytest.approx(8.0, rel=1e-6)
    assert "BÊN TRONG Block" in result


def test_block_geometry_is_scaled_by_the_insert_scale(workspace):
    """Block chèn ở scale 2 thì tuyến bên trong dài gấp đôi trên bản vẽ thật."""
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4
    doc.layers.add("PIPE_SCALED")
    block = doc.blocks.new(name="MODULE_GIO")
    block.add_line((0, 0), (5000, 0), dxfattribs={"layer": "PIPE_SCALED"})
    doc.modelspace().add_blockref("MODULE_GIO", (0, 0),
                                  dxfattribs={"xscale": 2.0, "yscale": 2.0})
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    assert df[df["Hạng mục"] == "PIPE_SCALED"].iloc[0]["Khối lượng"] == pytest.approx(10.0, rel=1e-6)


def test_symbol_linework_inside_a_block_is_not_counted_as_pipe(workspace):
    """Nét vẽ ký hiệu (van, đèn) chỉ dài vài chục mm — không được thổi vào chiều dài ống."""
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4
    doc.layers.add("KY_HIEU_VAN")
    block = doc.blocks.new(name="VAN_CHAN")
    block.add_line((0, 0), (50, 0), dxfattribs={"layer": "KY_HIEU_VAN"})
    block.add_line((50, 0), (50, 50), dxfattribs={"layer": "KY_HIEU_VAN"})
    doc.modelspace().add_blockref("VAN_CHAN", (0, 0))
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    assert not (df["Hạng mục"] == "KY_HIEU_VAN").any()
    assert (df["Hạng mục"] == "VAN_CHAN").any()


def test_nested_equipment_block_is_counted(workspace):
    """Thiết bị lồng trong block khác vẫn phải lên bảng khối lượng."""
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4
    doc.blocks.new(name="DEN_LED")
    cluster = doc.blocks.new(name="CUM_DEN")
    cluster.add_blockref("DEN_LED", (0, 0))
    cluster.add_blockref("DEN_LED", (1200, 0))
    doc.modelspace().add_blockref("CUM_DEN", (0, 0))
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    assert df[df["Hạng mục"] == "DEN_LED"].iloc[0]["Khối lượng"] == 2


def test_minsert_grid_counts_every_copy(workspace):
    """MINSERT 4 hàng x 5 cột là 20 bộ đèn, không phải 1."""
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4
    doc.blocks.new(name="DEN_600")
    doc.modelspace().add_blockref("DEN_600", (0, 0), dxfattribs={
        "row_count": 4, "column_count": 5, "row_spacing": 2000, "column_spacing": 2000,
    })
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    assert df[df["Hạng mục"] == "DEN_600"].iloc[0]["Khối lượng"] == 20


def test_layer_zero_inside_block_inherits_the_insert_layer(workspace):
    """Quy tắc CAD: entity layer '0' trong block hiện theo layer của INSERT — bỏ qua quy
    tắc này là dồn hết tuyến về layer '0' và mất hệ."""
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4
    doc.layers.add("HVAC_DUCT")
    block = doc.blocks.new(name="ONG_GIO_MOD")
    block.add_line((0, 0), (9000, 0), dxfattribs={"layer": "0"})
    doc.modelspace().add_blockref("ONG_GIO_MOD", (0, 0), dxfattribs={"layer": "HVAC_DUCT"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    assert df[df["Hạng mục"] == "HVAC_DUCT"].iloc[0]["Khối lượng"] == pytest.approx(9.0, rel=1e-6)


def test_fitting_stock_length_follows_the_drawing_unit(workspace):
    """Cây ống 6 m: bản vẽ vẽ bằng mét thì ngưỡng phải là 6 đơn vị, không phải 6000."""
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 6
    doc.layers.add("PIPE_STOCK")
    doc.modelspace().add_line((0, 0), (25, 0), dxfattribs={"layer": "PIPE_STOCK"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    couplings = df[df["Hạng mục"] == "Măng sông (nối ống) - PIPE_STOCK"]
    assert not couplings.empty
    # 25 m ống, cây 6 m -> 4 mối nối. Nếu ngưỡng cây ống vẫn là 6000 (mm) thì đoạn 25 đơn
    # vị không vượt nổi một cây và số măng sông ra 0.
    assert couplings.iloc[0]["Khối lượng"] == 4


@pytest.mark.parametrize("insunits,expected_mm", [(1, 25.4), (2, 304.8), (4, 1.0), (5, 10.0), (6, 1000.0)])
def test_insunits_conversion_table(insunits, expected_mm):
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = insunits
    unit = cad_units.detect_drawing_unit(doc)
    assert unit.mm_per_unit == pytest.approx(expected_mm)
    assert unit.confident


def test_unit_guess_from_extent_prefers_a_plausible_building_size():
    assert cad_units.guess_unit_from_extent(50_000).mm_per_unit == 1.0     # 50 m nếu là mm
    assert cad_units.guess_unit_from_extent(45).mm_per_unit == 1000.0      # 45 m nếu là m
    assert cad_units.guess_unit_from_extent(1e-6) is None                  # không đủ căn cứ


def test_drawings_this_project_writes_declare_millimeters(workspace):
    """Vòng lặp khép kín: file do chính dự án ghi ra phải đọc lại đúng.

    `ezdxf.new()` mặc định khai MÉT trong khi mọi tool ở đây vẽ theo mm. Từ khi khối lượng
    được quy đổi THẬT theo header, một bản vẽ do `write_cad` tạo rồi đưa lại vào
    `auto_quantity_takeoff` sẽ ra khối lượng sai 1000 lần nếu header khai sai.
    """
    from src.tools import write_cad

    write_cad.invoke({"file_path": "ban_ve_moi.dxf", "layers": "ONG_CAP_NUOC, M-SAD"})

    path = resolve_safe_path("ban_ve_moi.dxf")
    doc = ezdxf.readfile(path)
    assert doc.header["$INSUNITS"] == 4

    # Vẽ tiếp một tuyến 6000 mm vào chính file đó rồi bóc lại: phải ra đúng 6 m.
    doc.modelspace().add_line((0, 0), (6000, 0), dxfattribs={"layer": "ONG_CAP_NUOC"})
    doc.saveas(path)
    _, df = _takeoff(file_path="ban_ve_moi.dxf")
    assert df[df["Hạng mục"] == "ONG_CAP_NUOC"].iloc[0]["Khối lượng"] == pytest.approx(6.0)


def test_block_library_declares_millimeters():
    """Thư viện block vẽ miệng gió 600x600 mm — header phải nói đúng là mm, nếu không
    chính nó đang tự mô tả 'miệng gió 600x600 MÉT'."""
    import os

    from src.workspace import get_project_root

    library = os.path.join(get_project_root(), "data", "blocks", "mepf_library.dxf")
    assert ezdxf.readfile(library).header["$INSUNITS"] == 4
