"""Nhánh DỰ PHÒNG phải cho cùng kết quả với nhánh chính.

Đo coverage cho thấy hai nhánh dự phòng chưa bao giờ chạy trong test: phần suy phụ kiện
khi máy thiếu `rtree`, và phần gán nhãn khi máy thiếu `numpy`. Đây là tình huống nguy
hiểm điển hình — **hai cài đặt cho cùng một việc, chỉ một cái được kiểm chứng**. Máy cài
thiếu thư viện sẽ âm thầm chạy nhánh còn lại và không ai biết nó có ra cùng con số không.

Kiểm tra thật thì nhánh gán nhãn LỆCH THẬT: nhánh `numpy` coi tuyến không tra được hệ là
"hệ khác" nên bỏ ghi chú, nhánh dự phòng thì không. Cùng một bản vẽ ra hai bảng khối
lượng khác nhau tuỳ máy có cài `numpy` hay không.
"""
import random
import sys

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


@pytest.fixture
def without_numpy(monkeypatch):
    """Ép `auto_quantity_takeoff` đi vào nhánh không có numpy.

    Đặt `sys.modules['numpy'] = None` làm mọi lệnh `import numpy` MỚI ném ImportError,
    trong khi các module đã giữ sẵn tham chiếu (pandas) vẫn chạy bình thường.
    """
    monkeypatch.setitem(sys.modules, "numpy", None)


@pytest.fixture
def without_rtree(monkeypatch):
    monkeypatch.setitem(sys.modules, "rtree", None)


def _label_drawing(rival_layer: str, rival_y: float):
    """Ghi chú cách tuyến cấp nước 300 đơn vị và cách tuyến 'đối thủ' 330 — tức nằm ngay
    trong ngưỡng mơ hồ 1.3 lần, đúng chỗ hai nhánh từng cho kết quả khác nhau."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    doc.layers.add("ONG_CAP_NUOC")
    doc.layers.add(rival_layer)
    msp.add_line((0, 0), (20000, 0), dxfattribs={"layer": "ONG_CAP_NUOC"})
    msp.add_line((0, rival_y), (20000, rival_y), dxfattribs={"layer": rival_layer})
    msp.add_text("Ống uPVC Ø110").set_placement((10000, 300))
    doc.saveas(resolve_safe_path("bv.dxf"))


def _has_label(df):
    return any(str(name).startswith("Ống uPVC") for name in df["Hạng mục"])


def _run():
    auto_quantity_takeoff.invoke({"file_path": "bv.dxf", "output_excel_path": "kl.xlsx",
                                  "wastage_percent": 0})
    return pd.read_excel(resolve_safe_path("kl.xlsx"))


def test_unclassified_route_does_not_make_a_label_ambiguous(workspace):
    """Tuyến KHÔNG tra được hệ là hệ CHƯA BIẾT, không phải "hệ khác".

    Coi nó là đối thủ sẽ khiến ghi chú bị bỏ tràn lan trên hồ sơ thật — bản vẽ nào cũng
    đầy nét nền kiến trúc không tra được hệ chạy sát tuyến MEPF.
    """
    _label_drawing("LAYER_LA_HOAC", 630)
    assert _has_label(_run())


def test_a_genuinely_different_system_still_makes_a_label_ambiguous(workspace):
    """Nhưng ống gió HVAC chạy song song sát ống nước thì ghi chú vẫn phải bị coi là mơ hồ
    — đây mới là trường hợp cảnh báo sinh ra để bắt."""
    _label_drawing("M-SAD", 630)
    assert not _has_label(_run())


def test_label_matching_agrees_with_and_without_numpy(workspace, without_numpy):
    """Cùng bản vẽ, cùng kết quả, bất kể máy có numpy hay không."""
    _label_drawing("LAYER_LA_HOAC", 630)
    assert _has_label(_run())


def test_ambiguity_warning_agrees_with_and_without_numpy(workspace, without_numpy):
    _label_drawing("M-SAD", 630)
    assert not _has_label(_run())


def _random_route(seed):
    """Một tuyến gấp khúc ngẫu nhiên, có cả đoạn thẳng lẫn đoạn cung."""
    random.seed(seed)
    segments, x, y = [], 0.0, 0.0
    for _ in range(random.randint(3, 12)):
        nx = x + random.choice([-1, 0, 1]) * random.randint(0, 9) * 1000
        ny = y + random.choice([-1, 0, 1]) * random.randint(0, 9) * 1000
        if (nx, ny) != (x, y):
            segments.append({
                "layer": "P", "start": (x, y, 0.0), "end": (nx, ny, 0.0),
                "length": ((nx - x) ** 2 + (ny - y) ** 2) ** 0.5,
                "is_arc": random.random() < 0.15,
            })
        x, y = nx, ny
    return segments


@pytest.mark.parametrize("seed", range(25))
def test_fitting_inference_agrees_with_and_without_rtree(seed, monkeypatch):
    """Suy phụ kiện có hai cài đặt: chỉ mục không gian (rtree) và vòng lặp O(N²) dự phòng.
    Chúng phải cho cùng số co/tê/măng sông trên cùng hình học."""
    import importlib

    segments = _random_route(seed)
    if not segments:
        pytest.skip("hình học rỗng")

    with_index = cad_geometry.detect_fittings(segments)

    monkeypatch.setitem(sys.modules, "rtree", None)
    reloaded = importlib.reload(cad_geometry)
    try:
        without_index = reloaded.detect_fittings(segments)
    finally:
        monkeypatch.undo()
        importlib.reload(cad_geometry)

    assert without_index == with_index


# --- Các nhánh còn trống sau khi đo coverage ---------------------------------------

def test_pipe_two_block_levels_deep_is_counted_and_placed_correctly(workspace):
    """Tuyến nằm trong block LỒNG TRONG block khác: phải được cộng, và phải chịu đủ phép
    dời/tỷ lệ của cả hai tầng."""
    doc = ezdxf.new(units=4)
    doc.layers.add("ONG_CAP_NUOC")
    inner = doc.blocks.new("CUM_TRONG")
    inner.add_line((0, 0), (10000, 0), dxfattribs={"layer": "ONG_CAP_NUOC"})
    outer = doc.blocks.new("CUM_NGOAI")
    outer.add_blockref("CUM_TRONG", (1000, 0), dxfattribs={"xscale": 2.0, "yscale": 2.0})
    doc.modelspace().add_blockref("CUM_NGOAI", (5000, 5000))
    doc.saveas(resolve_safe_path("bv.dxf"))

    df = _run()
    # 10 m x tỷ lệ 2 của tầng trong = 20 m.
    assert df[df["Hạng mục"] == "ONG_CAP_NUOC"].iloc[0]["Khối lượng"] == pytest.approx(20.0)


def test_block_referring_to_itself_does_not_hang(workspace):
    """Block tự tham chiếu vòng (A chứa B, B chứa A) có thật trong file hỏng — `max_depth`
    phải chặn, không được đệ quy vô hạn."""
    doc = ezdxf.new(units=4)
    doc.layers.add("ONG_CAP_NUOC")
    block_a = doc.blocks.new("A")
    block_b = doc.blocks.new("B")
    block_a.add_line((0, 0), (10000, 0), dxfattribs={"layer": "ONG_CAP_NUOC"})
    block_a.add_blockref("B", (0, 0))
    block_b.add_blockref("A", (0, 0))
    doc.modelspace().add_blockref("A", (0, 0))
    doc.saveas(resolve_safe_path("bv.dxf"))

    df = _run()   # phải trả về, không treo
    assert (df["Hạng mục"] == "ONG_CAP_NUOC").any()


def test_xref_block_is_not_exploded_by_the_block_walker(workspace):
    """XREF đã có đường xử lý riêng (`cad_loader.resolve_xref_segments`); bung nó thêm lần
    nữa ở đây là tính đôi."""
    doc = ezdxf.new(units=4)
    doc.layers.add("ONG_CAP_NUOC")
    block = doc.blocks.new("NEN_KIEN_TRUC")
    block.add_line((0, 0), (50000, 0), dxfattribs={"layer": "ONG_CAP_NUOC"})
    block.block.dxf.flags = block.block.dxf.flags | 4      # đánh dấu là XREF
    insert = doc.modelspace().add_blockref("NEN_KIEN_TRUC", (0, 0))

    segments, _ = cad_geometry.explode_insert(insert, doc)
    assert segments == []


def test_degenerate_curve_measures_zero_without_crashing():
    """Hình suy biến (trục lớn bằng 0, thiếu điểm điều khiển) phải trả 0, không ném lỗi.

    ezdxf chặn không cho tạo ellipse như vậy, nhưng file thật từ nguồn khác thì có — nên
    nhánh phòng vệ này được kiểm bằng một đối tượng giả.
    """
    class _EllipseSuyBien:
        dxf = type("dxf", (), {"major_axis": (0.0, 0.0, 0.0)})()

        def dxftype(self):
            return "ELLIPSE"

    class _SplineTrong:
        control_points = []
        fit_points = []

        def dxftype(self):
            return "SPLINE"

    assert cad_geometry._curve_span(_EllipseSuyBien()) == 0.0
    assert cad_geometry._curve_span(_SplineTrong()) == 0.0
    assert cad_geometry._flattened_points(_EllipseSuyBien()) == []


def test_block_name_lookup_survives_unrelated_xdata(workspace):
    """Block ẩn danh mang XDATA không phải mã 1005 vẫn phải được nhận là ẩn danh, không
    ném lỗi."""
    doc = ezdxf.new(units=4)
    doc.appids.add("AcDbBlockRepBTag")
    doc.blocks.new("*U77")
    insert = doc.modelspace().add_blockref("*U77", (0, 0))
    insert.set_xdata("AcDbBlockRepBTag", [(1000, "ghi chu la hoac")])

    name, is_anonymous = cad_geometry.effective_block_name(insert, doc)
    assert (name, is_anonymous) == ("*U77", True)
