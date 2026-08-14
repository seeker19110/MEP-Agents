"""Hình học CAD dùng chung: chiều dài cung ARC/bulge, cao độ Z, phụ kiện suy từ hình học,
và cảnh báo Block bị insert lệch tỷ lệ.

Trước module này, mọi tool đo chiều dài chỉ cộng khoảng cách thẳng giữa các vertex —
đoạn cong (bulge trong LWPOLYLINE, entity ARC rời) bị đo hụt hoặc bị bỏ hẳn."""
import math

import ezdxf
import pytest

from src.cad_geometry import (
    arc_entity_length, block_scale, bulge_arc_length, collect_segments, detect_fittings,
    entity_length, entity_points_3d, entity_segments, is_scaled, parse_nominal_half_width,
    polyline_segments,
)


# --- bulge -> chiều dài cung thật (không phải dây cung) ---

def test_bulge_zero_is_a_straight_line():
    assert bulge_arc_length(0, 0, 100, 0, 0.0) == 100.0


def test_quarter_circle_bulge_matches_known_formula():
    """bulge = tan(theta/4); cung 1/4 vòng tròn bán kính 100 dài pi*100/2."""
    bulge = math.tan(math.radians(90 / 4))
    chord_length = 100 * math.sqrt(2)  # dây cung của góc 90 độ, bán kính 100
    arc = bulge_arc_length(0, 0, 100, 100, bulge)
    assert arc == pytest.approx(math.pi * 100 / 2, rel=1e-6)
    assert arc > chord_length  # cung luôn dài hơn dây cung — đây chính là phần bị đo hụt trước đây


def test_half_circle_bulge():
    """bulge = 1.0 tương ứng nửa vòng tròn (góc 180 độ)."""
    arc = bulge_arc_length(0, 0, 200, 0, 1.0)
    assert arc == pytest.approx(math.pi * 100, rel=1e-6)  # bán kính 100, nửa chu vi


def test_bulge_arc_scales_with_curvature():
    shallow = bulge_arc_length(0, 0, 100, 0, 0.1)
    deep = bulge_arc_length(0, 0, 100, 0, 0.5)
    assert deep > shallow > 100.0


# --- ARC entity (trước đây bị bỏ qua hoàn toàn) ---

def test_arc_entity_length_quarter_circle():
    doc = ezdxf.new()
    msp = doc.modelspace()
    arc = msp.add_arc(center=(0, 0), radius=50, start_angle=0, end_angle=90)
    assert arc_entity_length(arc) == pytest.approx(math.pi * 50 / 2, rel=1e-6)


def test_arc_entity_length_full_circle_when_angles_equal():
    doc = ezdxf.new()
    msp = doc.modelspace()
    arc = msp.add_arc(center=(0, 0), radius=10, start_angle=45, end_angle=45)
    assert arc_entity_length(arc) == pytest.approx(2 * math.pi * 10, rel=1e-6)


def test_entity_length_includes_bare_arc_entities():
    """Regression: trước đây entity ARC rời (không thuộc polyline) không được cộng vào
    tổng chiều dài — bóc khối lượng bỏ sót hoàn toàn các đoạn vẽ bằng ARC."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    arc = msp.add_arc(center=(0, 0), radius=100, start_angle=0, end_angle=180)
    assert entity_length(arc) == pytest.approx(math.pi * 100, rel=1e-6)


def test_circle_entity_length_is_circumference():
    doc = ezdxf.new()
    msp = doc.modelspace()
    circle = msp.add_circle(center=(0, 0), radius=20)
    assert entity_length(circle) == pytest.approx(2 * math.pi * 20, rel=1e-6)


# --- Polyline với bulge / cao độ Z ---

def test_lwpolyline_with_bulge_uses_arc_length_not_chord():
    doc = ezdxf.new()
    msp = doc.modelspace()
    bulge = math.tan(math.radians(90 / 4))
    # bulge trên một vertex áp dụng cho đoạn TỪ vertex đó TỚI vertex kế tiếp.
    pl = msp.add_lwpolyline([(0, 0, 0, 0, bulge), (100, 100), (200, 0)], format="xyseb")
    segs = polyline_segments(pl)
    assert len(segs) == 2
    assert segs[0]["is_arc"] is True
    assert segs[0]["length"] == pytest.approx(math.pi * 100 / 2, rel=1e-6)


def test_lwpolyline_straight_segment_length():
    doc = ezdxf.new()
    msp = doc.modelspace()
    pl = msp.add_lwpolyline([(0, 0), (30, 40)])
    segs = polyline_segments(pl)
    assert segs[0]["length"] == pytest.approx(50.0)  # tam giác 3-4-5
    assert segs[0]["is_arc"] is False


def test_closed_polyline_adds_the_closing_segment():
    """Polyline đóng bị bỏ sót cạnh cuối (từ vertex cuối về vertex đầu) là đo hụt đúng
    một cạnh của mọi tuyến ống chạy vòng khép kín."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    pl = msp.add_lwpolyline([(0, 0), (100, 0), (100, 100)], close=True)
    segs = polyline_segments(pl)
    assert len(segs) == 3  # 2 cạnh mở + 1 cạnh đóng


def test_line_with_different_z_is_longer_than_its_2d_projection():
    """Tuyến đi xiên giữa hai cao độ bị đo ngắn hơn thật nếu chỉ xét hình chiếu bằng."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    line = msp.add_line((0, 0, 0), (300, 400, 0))
    line_3d = msp.add_line((0, 0, 0), (300, 400, 120))
    flat_length = entity_length(line)
    slanted_length = entity_length(line_3d)
    assert flat_length == pytest.approx(500.0)  # 3-4-5 tam giác x100
    assert slanted_length > flat_length
    assert slanted_length == pytest.approx(math.sqrt(300**2 + 400**2 + 120**2))


# --- Phụ kiện suy từ hình học ---

def test_elbow_detected_at_perpendicular_turn():
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "PIPE"})
    msp.add_line((100, 0), (100, 100), dxfattribs={"layer": "PIPE"})
    segments = collect_segments(list(msp))
    fittings = detect_fittings(segments)
    assert fittings["PIPE"]["co"] == 1


def test_no_elbow_for_nearly_straight_continuation():
    """Hai đoạn gần như thẳng hàng (đổi hướng dưới ngưỡng) không phải là chỗ lắp co."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "PIPE"})
    msp.add_line((100, 0), (200, 1), dxfattribs={"layer": "PIPE"})  # lệch góc rất nhỏ
    segments = collect_segments(list(msp))
    fittings = detect_fittings(segments)
    assert fittings["PIPE"]["co"] == 0


def test_arc_segment_itself_counts_as_an_elbow():
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_arc(center=(0, 0), radius=50, start_angle=0, end_angle=90, dxfattribs={"layer": "PIPE"})
    segments = collect_segments(list(msp))
    fittings = detect_fittings(segments)
    assert fittings["PIPE"]["co"] == 1


def test_tee_detected_when_endpoint_touches_another_segments_body():
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (200, 0), dxfattribs={"layer": "PIPE"})   # tuyến chính
    msp.add_line((100, 0), (100, 80), dxfattribs={"layer": "PIPE"})  # nhánh rẽ giữa tuyến chính
    segments = collect_segments(list(msp))
    fittings = detect_fittings(segments)
    assert fittings["PIPE"]["te"] >= 1


def test_no_tee_when_segments_only_meet_at_shared_endpoint():
    """Hai đoạn nối đầu-đầu là một co, không phải một tê."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "PIPE"})
    msp.add_line((100, 0), (100, 100), dxfattribs={"layer": "PIPE"})
    segments = collect_segments(list(msp))
    fittings = detect_fittings(segments)
    assert fittings["PIPE"]["te"] == 0


def test_couplings_scale_with_total_length_over_stock_length():
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (20000, 0), dxfattribs={"layer": "PIPE"})  # 20m, cây 6m -> ~3 mối nối
    segments = collect_segments(list(msp))
    fittings = detect_fittings(segments, stock_length=6000.0)
    assert fittings["PIPE"]["mang_song"] == 3  # ceil(20000/6000) - 1 tuyến = 4 - 1 = 3


def test_fittings_are_grouped_per_layer_independently():
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "PIPE_A"})
    msp.add_line((100, 0), (100, 100), dxfattribs={"layer": "PIPE_A"})
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "PIPE_B"})
    segments = collect_segments(list(msp))
    fittings = detect_fittings(segments)
    assert fittings["PIPE_A"]["co"] == 1
    assert fittings["PIPE_B"]["co"] == 0


# --- Cảnh báo Block bị insert lệch tỷ lệ ---

def test_default_scale_is_not_flagged():
    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.blocks.new("LIGHT")
    insert = msp.add_blockref("LIGHT", (0, 0))
    assert is_scaled(insert) is False
    assert block_scale(insert) == (1.0, 1.0, 1.0)


def test_non_uniform_scale_is_flagged():
    """Đèn 600x600 chèn ở scale 1.5 có kích thước thực tế 900x900 — phải cảnh báo."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.blocks.new("LIGHT")
    insert = msp.add_blockref("LIGHT", (0, 0), dxfattribs={"xscale": 1.5, "yscale": 1.5})
    assert is_scaled(insert) is True
    xs, ys, _ = block_scale(insert)
    assert xs == pytest.approx(1.5)
    assert ys == pytest.approx(1.5)


def test_only_one_axis_scaled_is_still_flagged():
    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.blocks.new("LIGHT")
    insert = msp.add_blockref("LIGHT", (0, 0), dxfattribs={"xscale": 1.0, "yscale": 2.0})
    assert is_scaled(insert) is True


# --- entity_points_3d: dùng cho clash detection với cung được rời rạc hóa ---

def test_entity_points_3d_arc_endpoints_match_geometry():
    doc = ezdxf.new()
    msp = doc.modelspace()
    arc = msp.add_arc(center=(0, 0), radius=100, start_angle=0, end_angle=90)
    points = entity_points_3d(arc, arc_segments=4)
    assert points[0] == pytest.approx((100, 0, 0))
    assert points[-1] == pytest.approx((0, 100, 0), abs=1e-6)
    assert len(points) == 5


def test_entity_points_3d_preserves_declared_elevation():
    doc = ezdxf.new()
    msp = doc.modelspace()
    line = msp.add_line((0, 0, 50), (100, 0, 50))
    points = entity_points_3d(line)
    assert all(p[2] == pytest.approx(50) for p in points)


# --- Suy bán kính/nửa bề rộng danh nghĩa từ ghi chú kích thước (dùng cho clash theo bề dày) ---

def test_parse_nominal_half_width_from_diameter_notation():
    assert parse_nominal_half_width("Ống uPVC Ø110 (D110)") == pytest.approx(55.0)
    assert parse_nominal_half_width("DN100") == pytest.approx(50.0)


def test_parse_nominal_half_width_from_rectangular_duct_uses_larger_side():
    assert parse_nominal_half_width("Ống gió 600x400") == pytest.approx(300.0)
    assert parse_nominal_half_width("W300xH900") == pytest.approx(450.0)


def test_parse_nominal_half_width_returns_none_when_no_size_found():
    assert parse_nominal_half_width("Ghi chú không có kích thước") is None
    assert parse_nominal_half_width("") is None
    assert parse_nominal_half_width(None) is None


# --- Tê tại ngã ba khi tuyến chính BỊ TÁCH ở chỗ rẽ ---

def test_tee_detected_when_main_run_is_split_at_the_branch():
    """Ngã ba mà cả ba đoạn cùng kết thúc tại điểm rẽ vẫn phải là một TÊ.

    Đây là cách vẽ phổ biến nhất: polyline tuyến chính có một vertex ngay chỗ rẽ, hoặc
    họa viên vẽ từng đoạn một. Cách nhận tê cũ chỉ bắt trường hợp đầu mút nhánh chạm vào
    THÂN tuyến chính, nên ở đây nó đếm 0 tê — mà khúc gãy 90° tại đúng chỗ đó lại bị tính
    thành một CO. Bảng vật tư sai hai lần: thừa một co, thiếu một tê.
    """
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (3000, 0), dxfattribs={"layer": "PIPE"})      # tuyến chính, nửa trái
    msp.add_line((3000, 0), (6000, 0), dxfattribs={"layer": "PIPE"})   # tuyến chính, nửa phải
    msp.add_line((3000, 0), (3000, 4000), dxfattribs={"layer": "PIPE"})  # nhánh rẽ
    fittings = detect_fittings(collect_segments(list(msp)))
    assert fittings["PIPE"]["te"] == 1
    assert fittings["PIPE"]["co"] == 0, "chỗ rẽ nhánh không được tính thành co"


def test_cross_junction_counts_as_one_fitting():
    """Ngã tư (bậc 4) là một phụ kiện, không phải hai."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    for start, end in [((0, 0), (3000, 0)), ((3000, 0), (6000, 0)),
                       ((3000, 0), (3000, 3000)), ((3000, 0), (3000, -3000))]:
        msp.add_line(start, end, dxfattribs={"layer": "PIPE"})
    fittings = detect_fittings(collect_segments(list(msp)))
    assert fittings["PIPE"]["te"] == 1
    assert fittings["PIPE"]["co"] == 0


def test_plain_corner_is_still_an_elbow_not_a_tee():
    """Chốt ngược: bậc 2 đổi hướng vẫn phải là CO, việc sửa tê không được lấn sang."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (3000, 0), dxfattribs={"layer": "PIPE"})
    msp.add_line((3000, 0), (3000, 4000), dxfattribs={"layer": "PIPE"})
    fittings = detect_fittings(collect_segments(list(msp)))
    assert fittings["PIPE"]["co"] == 1
    assert fittings["PIPE"]["te"] == 0
