"""Test bộ công cụ offline/AI-yếu: auto_quantity_takeoff, optimize_cad_drawing, và
fallback tra cứu tiêu chuẩn không cần API key (search_standards)."""
import os
import ezdxf
import pandas as pd
import pytest

from src.workspace import set_workspace_dir, resolve_safe_path
from src.tools import auto_quantity_takeoff, optimize_cad_drawing, search_standards, _offline_keyword_search


@pytest.fixture
def workspace(tmp_path):
    return set_workspace_dir(str(tmp_path / "session_offline"))


def _make_sample_dxf(path: str):
    doc = ezdxf.new('R2010')
    doc.layers.add(name="ONG_CAP_NUOC")
    doc.layers.add(name="THIET_BI")
    msp = doc.modelspace()

    # Block định nghĩa + 2 instance
    block = doc.blocks.new(name="SOCKET")
    block.add_circle((0, 0), radius=50)
    msp.add_blockref("SOCKET", (0, 0), dxfattribs={"layer": "THIET_BI"})
    msp.add_blockref("SOCKET", (1000, 0), dxfattribs={"layer": "THIET_BI"})

    # Đường ống dài 500 đơn vị + ghi chú gần đó
    msp.add_line((0, 0), (500, 0), dxfattribs={"layer": "ONG_CAP_NUOC"})
    msp.add_text("Ống uPVC Ø110", dxfattribs={"layer": "ONG_CAP_NUOC"}).set_placement((250, 5))

    doc.saveas(path)


def test_auto_quantity_takeoff_writes_excel_with_blocks_and_pipe_length(workspace):
    dxf_path = "sample.dxf"
    _make_sample_dxf(resolve_safe_path(dxf_path))

    # wastage_percent=0 để so khớp đúng chiều dài hình học thuần; hành vi mặc định có
    # cộng % hao hụt được kiểm tra riêng ở test_wastage_percent_is_added_by_default.
    result = auto_quantity_takeoff.invoke({
        "file_path": dxf_path, "output_excel_path": "boq.xlsx", "wastage_percent": 0,
    })

    assert "THÀNH CÔNG" in result
    out_file = resolve_safe_path("boq.xlsx")
    assert os.path.exists(out_file)

    df = pd.read_excel(out_file)
    assert (df["Hạng mục"] == "SOCKET").any()
    socket_row = df[df["Hạng mục"] == "SOCKET"].iloc[0]
    assert socket_row["Khối lượng"] == 2
    # Ổ cắm là thiết bị đếm rời -> "Cái" (theo cad_standards.BLOCK_STANDARD["SOCKET"]),
    # không phải "Bộ" mặc định cho mọi Block như trước.
    assert socket_row["Đơn vị"] == "Cái"

    # Tuyến ống phải được đặt tên theo ghi chú gần nhất thay vì tên layer thô
    assert (df["Hạng mục"] == "Ống uPVC Ø110 (D110)").any()
    pipe_row = df[df["Hạng mục"] == "Ống uPVC Ø110 (D110)"].iloc[0]
    # Đường vẽ dài 500 đơn vị bản vẽ (mm) -> 0.5 m sau khi quy đổi.
    assert pipe_row["Khối lượng"] == pytest.approx(0.5, rel=1e-3)


def test_wastage_percent_is_added_by_default(workspace):
    """Mặc định phải cộng % hao hụt vật tư vào khối lượng ống/dây — số đo hình học
    thuần luôn thấp hơn khối lượng cần mua thực tế (cắt nối, bù trừ khi thi công)."""
    dxf_path = "sample.dxf"
    _make_sample_dxf(resolve_safe_path(dxf_path))

    no_wastage = auto_quantity_takeoff.invoke({
        "file_path": dxf_path, "output_excel_path": "no_wastage.xlsx", "wastage_percent": 0,
    })
    with_wastage = auto_quantity_takeoff.invoke({
        "file_path": dxf_path, "output_excel_path": "with_wastage.xlsx", "wastage_percent": 10,
    })
    assert "10%" in with_wastage

    df_plain = pd.read_excel(resolve_safe_path("no_wastage.xlsx"))
    df_wasted = pd.read_excel(resolve_safe_path("with_wastage.xlsx"))
    plain_qty = df_plain[df_plain["Hạng mục"] == "Ống uPVC Ø110 (D110)"].iloc[0]["Khối lượng"]
    wasted_qty = df_wasted[df_wasted["Hạng mục"] == "Ống uPVC Ø110 (D110)"].iloc[0]["Khối lượng"]
    assert wasted_qty == pytest.approx(plain_qty * 1.10, rel=1e-3)


def test_auto_quantity_takeoff_handles_missing_file(workspace):
    result = auto_quantity_takeoff.invoke({"file_path": "khong_ton_tai.dxf"})
    assert "Lỗi" in result


def test_auto_quantity_takeoff_blocks_path_traversal(workspace, tmp_path):
    dxf_path = "sample.dxf"
    _make_sample_dxf(resolve_safe_path(dxf_path))
    outside_marker = tmp_path / "leaked.xlsx"

    result = auto_quantity_takeoff.invoke({"file_path": dxf_path, "output_excel_path": "../leaked.xlsx"})
    assert "Lỗi" in result
    assert not outside_marker.exists()


def test_optimize_cad_drawing_removes_zero_length_and_duplicate_blocks(workspace):
    dxf_path = "messy.dxf"
    path = resolve_safe_path(dxf_path)

    doc = ezdxf.new('R2010')
    doc.layers.add(name="RAC_THUA")
    doc.layers.add(name="THIET_BI")
    doc.blocks.new(name="SOCKET").add_circle((0, 0), radius=50)
    msp = doc.modelspace()
    msp.add_line((10, 10), (10, 10), dxfattribs={"layer": "RAC_THUA"})  # length 0
    msp.add_blockref("SOCKET", (0, 0), dxfattribs={"layer": "THIET_BI"})
    msp.add_blockref("SOCKET", (0, 0), dxfattribs={"layer": "THIET_BI"})  # duplicate
    doc.saveas(path)

    result = optimize_cad_drawing.invoke({"file_path": dxf_path})
    assert "THÀNH CÔNG" in result
    assert "Xóa 1 đối tượng có chiều dài bằng 0" in result
    assert "Xóa 1 Block trùng lặp" in result

    cleaned = ezdxf.readfile(path)
    inserts = list(cleaned.modelspace().query('INSERT[name=="SOCKET"]'))
    assert len(inserts) == 1
    lines = list(cleaned.modelspace().query('LINE'))
    assert len(lines) == 0


def test_optimize_cad_drawing_overkill_removes_duplicate_overlapping_lines(workspace):
    """Trace lại đường nét cũ mà quên xóa nét gốc -> LINE trùng hình học hoàn toàn,
    khiến file nặng và mọi bóc khối lượng theo layer đó bị nhân đôi."""
    dxf_path = "overkill.dxf"
    path = resolve_safe_path(dxf_path)

    doc = ezdxf.new('R2010')
    doc.layers.add(name="PIPE")
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "PIPE"})
    msp.add_line((100, 0), (0, 0), dxfattribs={"layer": "PIPE"})  # cùng đoạn, ngược hướng
    msp.add_line((0, 100), (100, 100), dxfattribs={"layer": "PIPE"})  # đoạn khác, giữ lại
    doc.saveas(path)

    result = optimize_cad_drawing.invoke({"file_path": dxf_path})
    assert "THÀNH CÔNG" in result
    assert "Overkill: xóa 1 LINE/LWPOLYLINE" in result

    cleaned = ezdxf.readfile(path)
    lines = list(cleaned.modelspace().query('LINE'))
    assert len(lines) == 2


def test_optimize_cad_drawing_purges_unused_block_definitions(workspace):
    """Block định nghĩa không còn INSERT nào tham chiếu chỉ làm nặng file, không phục vụ
    gì cho bản vẽ — tương đương lệnh PURGE của AutoCAD."""
    dxf_path = "purge.dxf"
    path = resolve_safe_path(dxf_path)

    doc = ezdxf.new('R2010')
    doc.blocks.new(name="SOCKET").add_circle((0, 0), radius=50)
    doc.blocks.new(name="ORPHAN_BLOCK").add_circle((0, 0), radius=10)
    msp = doc.modelspace()
    msp.add_blockref("SOCKET", (0, 0))
    doc.saveas(path)

    result = optimize_cad_drawing.invoke({"file_path": dxf_path})
    assert "THÀNH CÔNG" in result
    assert "1 Block định nghĩa không dùng" in result
    assert "ORPHAN_BLOCK" in result

    cleaned = ezdxf.readfile(path)
    assert "ORPHAN_BLOCK" not in cleaned.blocks
    assert "SOCKET" in cleaned.blocks


def test_optimize_cad_drawing_can_write_to_separate_output(workspace):
    dxf_path = "orig.dxf"
    _make_sample_dxf(resolve_safe_path(dxf_path))

    result = optimize_cad_drawing.invoke({"file_path": dxf_path, "output_path": "orig_optimized.dxf"})
    assert "THÀNH CÔNG" in result
    assert os.path.exists(resolve_safe_path("orig_optimized.dxf"))
    # File gốc vẫn còn nguyên (không bị ghi đè vì đã chỉ định output_path riêng)
    assert os.path.exists(resolve_safe_path(dxf_path))


def test_offline_keyword_search_finds_matching_chunk(tmp_path):
    standards_dir = tmp_path / "standards"
    standards_dir.mkdir()
    (standards_dir / "sample.txt").write_text(
        "Tải lạnh phòng ngủ tính theo hệ số 150 W/m2 theo TCVN 5687.\n\n"
        "Áp suất bơm chữa cháy phải đảm bảo tối thiểu theo TCVN 3890.",
        encoding="utf-8",
    )
    result = _offline_keyword_search("tải lạnh phòng ngủ", standards_dir=str(standards_dir))
    assert "TCVN 5687" in result
    assert "OFFLINE" in result


def test_offline_keyword_search_no_match():
    result = _offline_keyword_search("truy vấn hoàn toàn không liên quan gì", standards_dir="data/standards")
    # Có thể không tìm thấy match hoặc corpus rỗng tùy môi trường CI, chỉ cần không lỗi.
    assert isinstance(result, str)


def test_search_standards_falls_back_to_offline_without_api_key(workspace, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("src.config.settings.openai_api_key", "", raising=False)

    result = search_standards.invoke({"query": "tải lạnh"})
    assert isinstance(result, str)
    # Không được ném exception hay yêu cầu API key; luôn trả về một chuỗi kết quả (có hoặc
    # không tìm thấy khớp) — đây là hành vi offline-first bắt buộc.
