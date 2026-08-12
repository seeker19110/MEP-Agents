"""Đợt rà soát thứ hai các nguồn sai lệch bản vẽ -> khối lượng.

Bốn lỗi còn sót, đều không có dấu hiệu nào trên bảng Excel:

1. Tuyến vẽ bằng SPLINE/ELLIPSE đo ra đúng 0 m (bóc THIẾU trọn vẹn).
2. Lưới 3D (polyface/polygon mesh) bị cộng cạnh lưới vào chiều dài ống (bóc THỪA).
3. Đối tượng vẽ trong UCS lật (extrusion khác mặc định) bị đọc tọa độ OCS như WCS —
   chiều dài đúng nhưng tuyến nằm sai chỗ, kéo theo gán nhầm ghi chú kích thước.
4. Block động bị AutoCAD lưu thành block ẩn danh `*U…` — hạng mục dự toán mang tên vô
   nghĩa và một chủng loại thiết bị bị xé thành nhiều dòng.
"""
import math

import ezdxf
import pandas as pd
import pytest

from src import cad_geometry
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


def test_spline_route_is_measured(workspace):
    """Ống uốn cong vẽ bằng SPLINE: trước đây ra 0 m."""
    doc = ezdxf.new(units=4)
    doc.layers.add("PIPE_SPLINE")
    doc.modelspace().add_spline([(0, 0), (4000, 0), (8000, 0)],
                                dxfattribs={"layer": "PIPE_SPLINE"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    assert df[df["Hạng mục"] == "PIPE_SPLINE"].iloc[0]["Khối lượng"] == pytest.approx(8.0, rel=1e-3)


def test_ellipse_is_measured(workspace):
    doc = ezdxf.new(units=4)
    doc.layers.add("PIPE_ELLIPSE")
    doc.modelspace().add_ellipse((0, 0), major_axis=(1000, 0), ratio=1.0,
                                 dxfattribs={"layer": "PIPE_ELLIPSE"})
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    circumference_m = 2 * math.pi * 1000 / 1000.0
    assert df[df["Hạng mục"] == "PIPE_ELLIPSE"].iloc[0]["Khối lượng"] == pytest.approx(
        circumference_m, rel=1e-3)


def test_curved_spline_is_longer_than_its_chord(workspace):
    """Xấp xỉ phải bám đường cong: tuyến cong luôn dài hơn đoạn thẳng nối hai đầu."""
    doc = ezdxf.new(units=4)
    curve = doc.modelspace().add_spline([(0, 0), (5000, 5000), (10000, 0)])
    chord = 10000.0
    assert cad_geometry.entity_length(curve) > chord * 1.1


def test_polyface_mesh_is_not_counted_as_pipe(workspace):
    """Bề mặt 3D không phải tuyến ống — cộng cạnh lưới vào là bóc thừa."""
    doc = ezdxf.new(units=4)
    doc.layers.add("MO_HINH_3D")
    mesh = doc.modelspace().add_polyface(dxfattribs={"layer": "MO_HINH_3D"})
    mesh.append_face([(0, 0, 0), (5000, 0, 0), (5000, 5000, 0), (0, 5000, 0)])
    doc.saveas(resolve_safe_path("bv.dxf"))

    # Loại xong thì bản vẽ không còn gì đo được -> tool báo rõ, không xuất file rỗng.
    result = auto_quantity_takeoff.invoke({
        "file_path": "bv.dxf", "output_excel_path": "kl.xlsx", "wastage_percent": 0,
    })
    assert "Không tìm thấy Block hoặc tuyến" in result


def test_ocs_coordinates_are_converted_to_wcs():
    """Extrusion (0,0,-1) lật dấu trục X: tọa độ lưu 1000 nhưng vị trí thật là -1000."""
    doc = ezdxf.new(units=4)
    line = doc.modelspace().add_lwpolyline([(0, 0), (1000, 0)],
                                           dxfattribs={"extrusion": (0, 0, -1)})
    segment = cad_geometry.entity_segments(line)[0]
    assert segment["end"][0] == pytest.approx(-1000.0)
    # Phép biến đổi là trực giao nên chiều dài không đổi.
    assert segment["length"] == pytest.approx(1000.0)


def test_ocs_entity_is_matched_against_the_right_label(workspace):
    """Hệ quả thật của lỗi OCS: ghi chú kích thước bị gán cho tuyến sai.

    Hai tuyến nằm hai phía trục Y. Tuyến OCS có vị trí THẬT ở bên trái (x âm), ghi chú
    'Ống uPVC Ø110' cũng đặt bên trái — nếu tọa độ OCS bị đọc như WCS thì tuyến này bị coi
    là nằm bên phải và ghi chú sẽ rơi nhầm sang tuyến kia.
    """
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    doc.layers.add("ONG_TRAI")
    doc.layers.add("ONG_PHAI")
    # Lưu tọa độ dương nhưng extrusion lật -> vị trí thật nằm ở x âm.
    msp.add_lwpolyline([(1000, 0), (5000, 0)],
                       dxfattribs={"layer": "ONG_TRAI", "extrusion": (0, 0, -1)})
    msp.add_lwpolyline([(1000, 0), (5000, 0)], dxfattribs={"layer": "ONG_PHAI"})
    msp.add_text("Ống uPVC Ø110", dxfattribs={"layer": "GHI_CHU"}).set_placement((-3000, 100))
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    # Tên hạng mục được chuẩn hóa thêm phần kích thước, nên so khớp theo tiền tố.
    labelled = df[df["Hạng mục"].astype(str).str.startswith("Ống uPVC Ø110")]
    assert not labelled.empty
    assert "ONG_TRAI" in str(labelled.iloc[0]["Ghi chú"])


def _register_dynamic_block(doc, real_name: str, anonymous_name: str):
    """Dựng lại cách AutoCAD lưu một biến thể block động: block ẩn danh `*U…` kèm XDATA
    `AcDbBlockRepBTag` trỏ handle về block_record của định nghĩa gốc."""
    doc.appids.add("AcDbBlockRepBTag")
    real_block = doc.blocks.new(real_name)
    doc.blocks.new(anonymous_name)
    return real_block.block_record.dxf.handle


def test_dynamic_block_reports_its_real_name(workspace):
    doc = ezdxf.new(units=4)
    handle = _register_dynamic_block(doc, "VAN_CHAN_DN100", "*U12")
    insert = doc.modelspace().add_blockref("*U12", (0, 0))
    insert.set_xdata("AcDbBlockRepBTag", [(1005, handle)])
    doc.saveas(resolve_safe_path("bv.dxf"))

    result, df = _takeoff()
    assert (df["Hạng mục"] == "VAN_CHAN_DN100").any()
    assert not df["Hạng mục"].astype(str).str.startswith("*U").any()
    assert "ẨN DANH" not in result


def test_dynamic_block_variants_merge_into_one_row(workspace):
    """Hai biến thể của cùng một block động phải gộp về một dòng, không xé làm hai."""
    doc = ezdxf.new(units=4)
    handle = _register_dynamic_block(doc, "DAU_PHUN", "*U20")
    doc.blocks.new("*U21")
    msp = doc.modelspace()
    for name in ("*U20", "*U21"):
        insert = msp.add_blockref(name, (0, 0))
        insert.set_xdata("AcDbBlockRepBTag", [(1005, handle)])
    doc.saveas(resolve_safe_path("bv.dxf"))

    _, df = _takeoff()
    rows = df[df["Hạng mục"] == "DAU_PHUN"]
    assert len(rows) == 1
    assert rows.iloc[0]["Khối lượng"] == 2


def test_unresolvable_anonymous_block_is_flagged(workspace):
    """Không tra được tên gốc thì phải NÓI RÕ, thay vì im lặng in ra '*U99'."""
    doc = ezdxf.new(units=4)
    doc.blocks.new("*U99")
    doc.modelspace().add_blockref("*U99", (0, 0))
    doc.saveas(resolve_safe_path("bv.dxf"))

    result, _ = _takeoff()
    assert "ẨN DANH" in result
    assert "*U99" in result
