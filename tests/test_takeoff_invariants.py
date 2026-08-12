"""Test BẤT BIẾN cho `auto_quantity_takeoff` — lưới an toàn cho mọi thay đổi sau này.

Các test khác trong repo kiểm tra từng CA CỤ THỂ đã biết (bản vẽ mét, ống trong block,
spline...). Chúng chỉ bắt được lỗi mà người viết đã nghĩ ra. File này kiểm tra các TÍNH
CHẤT phải luôn đúng bất kể bản vẽ trông thế nào, nên bắt được cả lỗi chưa ai nghĩ tới:

1. **Bất biến đơn vị** — cùng một công trình vẽ bằng mm hay bằng m phải ra cùng số mét.
2. **Bất biến phép dời hình** — xoay/tịnh tiến/lật cả bản vẽ không làm đổi chiều dài đo.
3. **Tương đương lồng/phẳng** — hình học gói trong Block phải cho cùng kết quả với chính
   nó vẽ trực tiếp.
4. **Cộng tính** — hai khu tách rời bóc chung phải bằng tổng bóc riêng.
5. **Lũy đẳng** — chạy hai lần cho kết quả y hệt.

Xem `docs/AUDIT_BOC_KHOI_LUONG.md` và `docs/PROMPT_RA_SOAT_SAI_LECH.md`.
"""
import math

import ezdxf
import pandas as pd
import pytest
from ezdxf.math import Matrix44

from src.tools import auto_quantity_takeoff
from src.workspace import resolve_safe_path, set_workspace_dir

# Sai số cho phép khi so hai kết quả: đường cong tự do được xấp xỉ bằng gấp khúc với độ
# mịn suy từ kích thước bao của chính nó, nên phép dời hình có thể làm lệch vài phần vạn.
_REL = 1e-3


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


def _draw_reference(msp, doc, offset=(0.0, 0.0)):
    """Một 'công trình' thu nhỏ nhưng đủ mặt các kiểu hình học mà tool phải đo.

    Toạ độ theo mm. Cố ý trộn đủ LINE, polyline có cung (bulge), ARC, CIRCLE, SPLINE,
    ELLIPSE và một Block thiết bị — nếu một bất biến vỡ, ta biết nó vỡ trên hình học
    thật chứ không phải trên một ca nhân tạo.
    """
    dx, dy = offset
    for layer in ("ONG_CAP_NUOC", "M-SAD"):
        if layer not in doc.layers:
            doc.layers.add(layer)

    msp.add_lwpolyline([(dx, dy), (dx + 20000, dy), (dx + 20000, dy + 15000)],
                       dxfattribs={"layer": "ONG_CAP_NUOC"})
    msp.add_lwpolyline([(dx, dy + 3000, 0, 0, 0.5), (dx + 8000, dy + 3000, 0, 0, 0)],
                       format="xyseb", dxfattribs={"layer": "ONG_CAP_NUOC"})
    msp.add_arc(center=(dx, dy + 9000), radius=4000, start_angle=0, end_angle=90,
                dxfattribs={"layer": "M-SAD"})
    msp.add_circle(center=(dx + 30000, dy), radius=2500, dxfattribs={"layer": "M-SAD"})
    msp.add_spline([(dx, dy - 6000), (dx + 9000, dy - 2000), (dx + 18000, dy - 6000)],
                   dxfattribs={"layer": "M-SAD"})
    msp.add_ellipse((dx + 30000, dy - 9000), major_axis=(3000, 0), ratio=0.6,
                    dxfattribs={"layer": "ONG_CAP_NUOC"})

    if "DEN_LED" not in doc.blocks:
        doc.blocks.new("DEN_LED").add_circle((0, 0), radius=150)
    msp.add_blockref("DEN_LED", (dx + 2000, dy + 12000))


def _takeoff(name="bv.dxf", **kwargs):
    params = {"file_path": name, "output_excel_path": name.replace(".dxf", ".xlsx"),
              "wastage_percent": 0}
    params.update(kwargs)
    auto_quantity_takeoff.invoke(params)
    return pd.read_excel(resolve_safe_path(params["output_excel_path"]))


def _totals(df):
    """(tổng chiều dài mét, tổng số phụ kiện/thiết bị) — dạng so sánh gọn của một bảng."""
    lengths = df[df["Đơn vị"] == "m"]["Khối lượng"].sum()
    pieces = df[df["Đơn vị"] != "m"]["Khối lượng"].sum()
    return float(lengths), int(pieces)


def _build(path, build_fn, units=4):
    doc = ezdxf.new(units=units)
    build_fn(doc.modelspace(), doc)
    doc.saveas(resolve_safe_path(path))
    return doc


# --- 1. Bất biến đơn vị ------------------------------------------------------------

def test_same_building_measures_the_same_in_millimeters_and_meters(workspace):
    """Cùng một công trình: vẽ bằng mm, hoặc vẽ bằng m với toạ độ chia 1000 — cùng ra một
    số mét. Đây là bất biến bắt được lớp lỗi 'chia cứng cho 1000'."""
    _build("mm.dxf", _draw_reference, units=4)

    doc_m = ezdxf.new(units=6)
    _draw_reference(doc_m.modelspace(), doc_m)
    for entity in doc_m.modelspace():
        entity.transform(Matrix44.scale(0.001, 0.001, 0.001))
    doc_m.saveas(resolve_safe_path("m.dxf"))

    len_mm, pieces_mm = _totals(_takeoff("mm.dxf"))
    len_m, pieces_m = _totals(_takeoff("m.dxf"))

    assert len_m == pytest.approx(len_mm, rel=_REL)
    # Ngưỡng cây ống/dung sai cũng phải đổi theo đơn vị, nếu không số phụ kiện sẽ lệch.
    assert pieces_m == pieces_mm


# --- 2. Bất biến phép dời hình -----------------------------------------------------

@pytest.mark.parametrize("name,matrix", [
    ("tinh_tien", Matrix44.translate(123456, -78901, 0)),
    ("xoay_37_do", Matrix44.z_rotate(math.radians(37))),
    ("xoay_90_do", Matrix44.z_rotate(math.radians(90))),
    ("lat_truc_x", Matrix44.scale(-1, 1, 1)),
])
def test_rigid_motion_does_not_change_measured_quantities(workspace, name, matrix):
    """Xoay, tịnh tiến hay lật cả bản vẽ là đổi cách đặt hệ trục, không đổi công trình —
    chiều dài và số phụ kiện phải y nguyên. Bất biến này bắt lớp lỗi đọc sai hệ toạ độ."""
    _build("goc.dxf", _draw_reference)

    doc = ezdxf.new(units=4)
    _draw_reference(doc.modelspace(), doc)
    for entity in doc.modelspace():
        entity.transform(matrix)
    doc.saveas(resolve_safe_path(f"{name}.dxf"))

    assert _totals(_takeoff(f"{name}.dxf")) == pytest.approx(_totals(_takeoff("goc.dxf")),
                                                             rel=_REL)


# --- 3. Tương đương lồng / phẳng ---------------------------------------------------

def test_geometry_inside_a_block_equals_the_same_geometry_drawn_directly(workspace):
    """Gói hình học vào Block rồi chèn ở gốc toạ độ không làm thay đổi công trình."""
    _build("phang.dxf", _draw_reference)

    doc = ezdxf.new(units=4)
    doc.layers.add("ONG_CAP_NUOC")
    doc.layers.add("M-SAD")
    block = doc.blocks.new("CUM_KY_THUAT")
    _draw_reference(block, doc)
    doc.modelspace().add_blockref("CUM_KY_THUAT", (0, 0))
    doc.saveas(resolve_safe_path("long.dxf"))

    length_flat, _ = _totals(_takeoff("phang.dxf"))
    length_nested, _ = _totals(_takeoff("long.dxf"))
    assert length_nested == pytest.approx(length_flat, rel=_REL)


def test_scaled_block_multiplies_length_by_the_scale(workspace):
    """Chèn cùng cụm đó ở tỷ lệ 3 thì chiều dài phải gấp đúng 3 lần."""
    doc = ezdxf.new(units=4)
    doc.layers.add("ONG_CAP_NUOC")
    doc.layers.add("M-SAD")
    block = doc.blocks.new("CUM_KY_THUAT")
    _draw_reference(block, doc)
    msp = doc.modelspace()
    msp.add_blockref("CUM_KY_THUAT", (0, 0))
    doc.saveas(resolve_safe_path("mot_lan.dxf"))

    doc2 = ezdxf.new(units=4)
    doc2.layers.add("ONG_CAP_NUOC")
    doc2.layers.add("M-SAD")
    block2 = doc2.blocks.new("CUM_KY_THUAT")
    _draw_reference(block2, doc2)
    doc2.modelspace().add_blockref("CUM_KY_THUAT", (0, 0),
                                   dxfattribs={"xscale": 3.0, "yscale": 3.0})
    doc2.saveas(resolve_safe_path("gap_ba.dxf"))

    base, _ = _totals(_takeoff("mot_lan.dxf"))
    scaled, _ = _totals(_takeoff("gap_ba.dxf"))
    assert scaled == pytest.approx(base * 3, rel=_REL)


# --- 4. Cộng tính ------------------------------------------------------------------

def test_two_separate_zones_add_up(workspace):
    """Hai khu tách rời hẳn nhau: bóc chung một lần phải bằng tổng bóc riêng từng khu.

    Bất biến này bảo vệ phần suy phụ kiện: măng sông tính theo TUYẾN LIÊN TỤC nên hai khu
    rời nhau không được phép ảnh hưởng lẫn nhau.
    """
    _build("khu_a.dxf", lambda msp, doc: _draw_reference(msp, doc, offset=(0, 0)))
    _build("khu_b.dxf", lambda msp, doc: _draw_reference(msp, doc, offset=(500000, 0)))

    def both(msp, doc):
        _draw_reference(msp, doc, offset=(0, 0))
        _draw_reference(msp, doc, offset=(500000, 0))

    _build("ca_hai.dxf", both)

    len_a, pieces_a = _totals(_takeoff("khu_a.dxf"))
    len_b, pieces_b = _totals(_takeoff("khu_b.dxf"))
    len_both, pieces_both = _totals(_takeoff("ca_hai.dxf"))

    assert len_both == pytest.approx(len_a + len_b, rel=_REL)
    assert pieces_both == pieces_a + pieces_b


# --- 5. Lũy đẳng -------------------------------------------------------------------

def test_running_the_takeoff_twice_gives_the_same_table(workspace):
    """Cùng đầu vào, chạy hai lần phải ra bảng y hệt — không phụ thuộc thứ tự duyệt,
    thứ tự tiến trình con, hay trạng thái còn sót từ lần chạy trước."""
    _build("bv.dxf", _draw_reference)

    first = _takeoff("bv.dxf", output_excel_path="lan1.xlsx")
    second = _takeoff("bv.dxf", output_excel_path="lan2.xlsx")

    pd.testing.assert_frame_equal(first, second)


# --- 6. Khép kín: file do chính dự án ghi ra ---------------------------------------

def test_wastage_scales_pipe_quantities_linearly(workspace):
    """Hao hụt là phép nhân thuần: 10% phải đúng bằng 0% nhân 1.1, không đụng vào số
    lượng thiết bị/phụ kiện (chúng đếm theo cái, không hao hụt)."""
    _build("bv.dxf", _draw_reference)

    base_len, base_pieces = _totals(_takeoff("bv.dxf", output_excel_path="w0.xlsx",
                                             wastage_percent=0))
    more_len, more_pieces = _totals(_takeoff("bv.dxf", output_excel_path="w10.xlsx",
                                             wastage_percent=10))

    assert more_len == pytest.approx(base_len * 1.1, rel=5e-3)
    assert more_pieces == base_pieces
