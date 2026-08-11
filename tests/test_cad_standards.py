"""Chuẩn hóa Layer/Block bản vẽ CAD người dùng đẩy vào theo tiêu chuẩn nội bộ MEPF."""
import ezdxf
import pytest

from src import cad_standards
from src.tools import standardize_cad_drawing
from src.workspace import resolve_safe_path, set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    return set_workspace_dir(str(tmp_path / "session_standardize"))


def test_normalize_strips_diacritics_and_punctuation():
    assert cad_standards.normalize("Ống Gió Cấp") == "ONGGIOCAP"
    assert cad_standards.normalize("m-duct-supply") == "MDUCTSUPPLY"


def test_match_layer_recognizes_common_vietnamese_variants():
    assert cad_standards.match_layer("Ong_Gio_Cap") == "M-SAD"
    assert cad_standards.match_layer("O_CAM_DIEN") == "E-POWER"
    assert cad_standards.match_layer("khong-co-nghia-gi-ca") is None


def test_match_layer_recognizes_already_standard_name_regardless_of_case():
    assert cad_standards.match_layer("m-duct-supply") == "M-SAD"


@pytest.mark.parametrize("raw_name, expected_canonical", [
    ("SAD", "M-SAD"),
    ("RAD", "M-RAD"),
    ("FAD", "M-FAD"),
    ("EAD", "M-EAD"),
    ("KEAD", "M-KEAD"),
    ("PAD", "M-PAD"),
    ("SEAD", "M-SEAD"),
    ("M-KEAD", "M-KEAD"),
])
def test_match_layer_recognizes_duct_abbreviations(raw_name, expected_canonical):
    assert cad_standards.match_layer(raw_name) == expected_canonical


def test_match_layer_disambiguates_exhaust_from_kitchen_exhaust():
    """Bug cũ: so khớp 2 chiều khiến 'EAD' (Exhaust) vô tình khớp nhầm 'KEAD' (Kitchen
    Exhaust) vì 'EAD' là chuỗi con của 'KEAD'. Layer/Block khác hệ thống (EAD dùng ống
    tôn thường, KEAD bắt buộc vật liệu chống cháy riêng cho bếp) không được gộp nhầm."""
    assert cad_standards.match_layer("EAD") == "M-EAD"
    assert cad_standards.match_layer("KEAD") == "M-KEAD"
    assert cad_standards.match_layer("ong_gio_thai_bep") == "M-KEAD"
    assert cad_standards.match_layer("ong_gio_thai") == "M-EAD"


@pytest.mark.parametrize("raw_name, expected_canonical", [
    ("ong_dong", "M-PIPE-REF"),
    ("ong_nuoc_ngung", "M-PIPE-COND"),
    ("CHWS", "M-PIPE-CHWS"),
    ("CHWR", "M-PIPE-CHWR"),
    ("ong_cap_nuoc_nong_sinh_hoat", "P-PIPE-HW"),
    ("ong_hoi_nuoc_nong", "P-PIPE-HWR"),
    ("ong_hong_nuoc", "F-PIPE-HYD"),
    ("den_su_co", "E-LIGHT-EMG"),
])
def test_match_layer_recognizes_pipe_and_other_mepf_variants(raw_name, expected_canonical):
    assert cad_standards.match_layer(raw_name) == expected_canonical


def test_match_block_recognizes_common_variants():
    assert cad_standards.match_block("O_Cam_Dien") == "SOCKET"
    assert cad_standards.match_block("mieng_gio_cap") == "DIFFUSER_SUPPLY"
    assert cad_standards.match_block("thiet_bi_la") is None


def _make_messy_dxf(path: str):
    doc = ezdxf.new("R2010")
    doc.layers.add(name="Ong_Gio_Cap")  # sẽ khớp M-SAD
    doc.layers.add(name="THIET_BI_LA")  # không nhận diện được, cần review
    doc.blocks.new(name="O_CAM_DIEN_CU").add_circle((0, 0), radius=50)  # khớp SOCKET
    msp = doc.modelspace()
    msp.add_line((0, 0), (500, 0), dxfattribs={"layer": "Ong_Gio_Cap"})
    msp.add_blockref("O_CAM_DIEN_CU", (0, 0), dxfattribs={"layer": "THIET_BI_LA"})
    doc.saveas(path)


def test_standardize_renames_recognized_layer_and_fixes_color(workspace):
    dxf_path = "messy.dxf"
    _make_messy_dxf(resolve_safe_path(dxf_path))

    result = standardize_cad_drawing.invoke({"file_path": dxf_path})

    assert "THÀNH CÔNG" in result
    assert "Ong_Gio_Cap -> M-SAD" in result

    doc = ezdxf.readfile(resolve_safe_path(dxf_path))
    assert "Ong_Gio_Cap" not in doc.layers
    layer = doc.layers.get("M-SAD")
    assert layer.dxf.color == cad_standards.LAYER_STANDARD["M-SAD"]["color"]
    assert layer.description == cad_standards.LAYER_STANDARD["M-SAD"]["description"]
    # Hình học không bị đụng tới: vẫn còn đúng 1 LINE, chỉ đổi layer.
    lines = list(doc.modelspace().query("LINE"))
    assert len(lines) == 1
    assert lines[0].dxf.layer == "M-SAD"


def test_standardize_lists_unmatched_layer_for_manual_review(workspace):
    dxf_path = "messy.dxf"
    _make_messy_dxf(resolve_safe_path(dxf_path))

    result = standardize_cad_drawing.invoke({"file_path": dxf_path})

    assert "CẦN REVIEW THỦ CÔNG" in result
    assert "THIET_BI_LA" in result


def test_standardize_renames_block_and_adds_attributes(workspace):
    dxf_path = "messy.dxf"
    _make_messy_dxf(resolve_safe_path(dxf_path))

    result = standardize_cad_drawing.invoke({"file_path": dxf_path})

    assert "O_CAM_DIEN_CU -> SOCKET" in result
    assert "SOCKET" in result

    doc = ezdxf.readfile(resolve_safe_path(dxf_path))
    assert "O_CAM_DIEN_CU" not in doc.blocks
    block = doc.blocks.get("SOCKET")
    tags = {a.dxf.tag: a.dxf.text for a in block.attdefs()}
    assert tags["MA_HIEU"] == cad_standards.BLOCK_STANDARD["SOCKET"]["ma_hieu"]
    assert tags["MO_TA"] == cad_standards.BLOCK_STANDARD["SOCKET"]["description"]
    # Geometry vẫn nguyên vẹn: block gốc có 1 CIRCLE.
    circles = [e for e in block if e.dxftype() == "CIRCLE"]
    assert len(circles) == 1
    # Instance INSERT trong modelspace đã trỏ theo tên mới.
    inserts = list(doc.modelspace().query('INSERT[name=="SOCKET"]'))
    assert len(inserts) == 1


def test_standardize_running_twice_is_idempotent(workspace):
    dxf_path = "messy.dxf"
    _make_messy_dxf(resolve_safe_path(dxf_path))

    standardize_cad_drawing.invoke({"file_path": dxf_path})
    result_second_run = standardize_cad_drawing.invoke({"file_path": dxf_path})

    assert "THÀNH CÔNG" in result_second_run
    assert "Đổi tên layer về chuẩn: (không có)" in result_second_run
    assert "Đổi tên Block về chuẩn: (không có)" in result_second_run
    assert "Gắn thuộc tính MA_HIEU/MO_TA cho Block: (không có)" in result_second_run


def test_standardize_can_write_to_separate_output(workspace):
    import os

    dxf_path = "orig.dxf"
    _make_messy_dxf(resolve_safe_path(dxf_path))

    result = standardize_cad_drawing.invoke({"file_path": dxf_path, "output_path": "orig_standardized.dxf"})

    assert "THÀNH CÔNG" in result
    assert os.path.exists(resolve_safe_path("orig_standardized.dxf"))
    original = ezdxf.readfile(resolve_safe_path(dxf_path))
    assert "Ong_Gio_Cap" in original.layers  # file gốc không bị đổi vì có output_path riêng
