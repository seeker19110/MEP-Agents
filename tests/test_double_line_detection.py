"""Cảnh báo "tuyến vẽ 2 nét song song bị tính đôi" (`cad_geometry.detect_double_line_runs`).

Ống gió và ống nước cỡ lớn hầu như luôn được vẽ bằng HAI nét song song (hai mép ống).
Cộng dồn chiều dài hình học sẽ ra **gấp đôi** tuyến thật, nên cảnh báo này là thứ duy nhất
cho kỹ sư biết con số trong bảng dự toán cần xem lại.

Bộ test này ra đời sau khi phát hiện cảnh báo **im lặng không nổ** với hai loại bản vẽ hay
gặp nhất — xem `docs/RA_SOAT_LO_HONG.md` mục 12.
"""
import math

import pytest

from src.cad_geometry import detect_double_line_runs


def _parallel_pair(angle_a, angle_b, separation=300.0, length=5000.0, layer="DUCT"):
    """Hai đoạn thẳng gần song song, cách nhau `separation` theo phương vuông góc."""
    normal = (-math.sin(math.radians(angle_a)), math.cos(math.radians(angle_a)))

    def line(angle, offset):
        rad = math.radians(angle)
        ux, uy = math.cos(rad), math.sin(rad)
        x0, y0 = normal[0] * offset, normal[1] * offset
        return {"layer": layer, "start": (x0, y0, 0),
                "end": (x0 + ux * length, y0 + uy * length, 0), "length": length}

    return [line(angle_a, 0.0), line(angle_b, separation)]


def _detected(*args, **kwargs) -> bool:
    return bool(detect_double_line_runs(_parallel_pair(*args, **kwargs)))


# --- Trường hợp cơ bản, vốn đã chạy đúng ---

@pytest.mark.parametrize("angle", [0.0, 45.0, 90.0, 135.0, 179.0])
def test_detects_exactly_parallel_pair(angle):
    assert _detected(angle, angle) is True


# --- Bẫy 1: lệch góc nhỏ rơi vào hai "ô góc" khác nhau ---

@pytest.mark.parametrize("a, b", [(0.0, 1.2), (0.0, 1.9), (1.0, 1.5), (44.5, 45.6)])
def test_detects_pair_with_small_angle_difference(a, b):
    """Hai nét vẽ tay lệch nhau dưới 2° vẫn là hai mép của một ống.

    Bản đầu gom đoạn theo ô `round(angle / 2°)` rồi chỉ so trong cùng một ô, nên một cặp
    nằm hai bên ranh giới ô (1,9° và 2,1°) không bao giờ được đem so — cảnh báo im lặng
    không nổ, để lại bảng khối lượng gấp đôi thực tế.
    """
    assert _detected(a, b) is True


# --- Bẫy 2: mốc 0/180 ---

@pytest.mark.parametrize("a, b", [(0.5, 179.5), (0.2, 179.9), (1.0, 179.0)])
def test_detects_pair_across_the_zero_boundary(a, b):
    """0,2° và 179,9° chỉ lệch nhau 0,3°, không phải 179,7°.

    Đây là loại tuyến phổ biến nhất trong bản vẽ MEPF (gần ngang), và cũng là chỗ bản đầu
    bỏ sót chắc chắn nhất: số hiệu ô của chúng là 0 và 90 — xa nhau nhất có thể.
    """
    assert _detected(a, b) is True


def test_offset_is_measured_in_a_canonical_direction():
    """Hai nét vẽ NGƯỢC CHIỀU nhau phải cho cùng một hệ quy chiếu khoảng lệch.

    Vector ngược chiều cho `offset` trái dấu; không chuẩn hóa hướng thì dù có so đúng cặp,
    khoảng lệch vẫn tính sai và cặp bị loại vì "quá xa nhau".
    """
    segments = [
        {"layer": "DUCT", "start": (0, 0, 0), "end": (5000, 0, 0), "length": 5000},
        # cùng tuyến, cách 300, nhưng vẽ từ phải sang trái
        {"layer": "DUCT", "start": (5000, 300, 0), "end": (0, 300, 0), "length": 5000},
    ]
    assert bool(detect_double_line_runs(segments)) is True


# --- Không được bắt nhầm ---

@pytest.mark.parametrize("a, b", [(0.0, 5.0), (0.0, 10.0), (0.0, 90.0)])
def test_ignores_pairs_that_are_not_parallel(a, b):
    assert _detected(a, b) is False


def test_ignores_pair_further_apart_than_any_real_duct():
    """Cách nhau 5 m thì gần như chắc chắn là hai tuyến riêng biệt, không phải hai mép."""
    assert _detected(0.0, 0.0, separation=5000.0) is False


def test_ignores_pairs_on_different_layers():
    """Hai hệ khác nhau chạy song song (cấp và hồi đi cùng trục) là chuyện bình thường."""
    segments = _parallel_pair(0.0, 0.0)
    segments[1]["layer"] = "PIPE-KHAC"
    assert bool(detect_double_line_runs(segments)) is False


def test_ignores_pairs_that_barely_overlap():
    """Hai tuyến chỉ chạm nhau một khúc ngắn thì không phải hai mép của cùng một ống."""
    segments = [
        {"layer": "DUCT", "start": (0, 0, 0), "end": (5000, 0, 0), "length": 5000},
        {"layer": "DUCT", "start": (4800, 300, 0), "end": (9800, 300, 0), "length": 5000},
    ]
    assert bool(detect_double_line_runs(segments)) is False


def test_reports_the_overlapping_length_per_layer():
    doubled = detect_double_line_runs(_parallel_pair(0.0, 0.0, length=4000.0))
    assert doubled["DUCT"] == pytest.approx(4000.0)


def test_each_segment_pairs_at_most_once():
    """Ba nét song song không được tính thành ba cặp — một nét chỉ là mép của một ống."""
    segments = [
        {"layer": "DUCT", "start": (0, y, 0), "end": (5000, y, 0), "length": 5000}
        for y in (0, 300, 600)
    ]
    assert detect_double_line_runs(segments)["DUCT"] == pytest.approx(5000.0)
