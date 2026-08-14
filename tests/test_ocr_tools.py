"""OCR: đường thiếu engine, đường chạy được, và ranh giới nghiệp vụ.

Máy chạy CI không có `tesseract`, nên engine thật không kiểm được ở đây. Thay vì bỏ trống
phần logic, các test dưới đây **đăng ký một engine giả** qua đúng điểm nối công khai
(`register_ocr_engine`) — cũng là cách kiểm rằng điểm nối đó dùng được thật, chứ không chỉ
tồn tại trên giấy. Phần phụ thuộc thật (chất lượng nhận dạng của Tesseract) không phải thứ
bộ test này khẳng định, và `TECH_DEBT.md` ghi rõ điều đó.
"""
import pytest
from PIL import Image

from src import ocr_tools
from src.ocr_tools import (
    OCR_DISCLAIMER,
    ocr_image,
    ocr_pdf_pages,
    ocr_title_block,
    register_ocr_engine,
    registered_ocr_engines,
    unregister_ocr_engine,
)
from src.workspace import set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    return set_workspace_dir(str(tmp_path / "session_ocr"))


@pytest.fixture
def png(workspace, tmp_path):
    path = tmp_path / "session_ocr" / "ban_ve.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), "white").save(path)
    return "ban_ve.png"


@pytest.fixture
def fake_engine():
    """Engine giả trả về một khối chữ chắc và một khối chữ không chắc."""
    def engine(image_path, lang, psm):
        return [
            {"text": "ONG", "conf": 96.0, "bbox": (0, 0, 10, 10), "line": (1, 1, 1)},
            {"text": "GIO", "conf": 95.0, "bbox": (12, 0, 10, 10), "line": (1, 1, 1)},
            {"text": "400x200", "conf": 22.0, "bbox": (24, 0, 30, 10), "line": (1, 1, 1)},
        ]

    register_ocr_engine("test_fake", engine, priority=100)
    yield engine
    unregister_ocr_engine("test_fake")


@pytest.fixture
def broken_engine():
    def engine(image_path, lang, psm):
        raise RuntimeError("engine hỏng")

    register_ocr_engine("test_broken", engine, priority=200)
    yield engine
    unregister_ocr_engine("test_broken")


# --- Thiếu engine: phải hướng dẫn, không được ném ---------------------------------


def test_missing_engine_returns_install_hint(png, monkeypatch):
    """Không engine nào chạy được → trả hướng dẫn cài, KHÔNG ném exception.

    Trên máy chưa cài tesseract, engine mặc định tự hỏng ở bước import — đúng nhánh cần
    kiểm. Xóa hẳn bảng engine để test không phụ thuộc máy có cài hay không.
    """
    monkeypatch.setattr(ocr_tools, "_ENGINES", {})

    result = ocr_image.invoke({"file_path": png})

    assert "Lỗi OCR" in result
    assert "tesseract-ocr" in result          # nói rõ cài gì
    assert "uv sync --extra ocr" in result    # và cài bằng lệnh nào


def test_engine_failure_falls_through_to_next(png, fake_engine, broken_engine):
    """Engine ưu tiên cao hỏng thì lùi xuống engine kế tiếp, không làm hỏng cả lượt."""
    assert registered_ocr_engines()[0] == "test_broken"

    result = ocr_image.invoke({"file_path": png})

    assert "ONG GIO" in result
    assert "test_fake" in result


# --- Ranh giới nghiệp vụ: OCR là số liệu cần xác nhận ------------------------------


def test_every_result_carries_the_disclaimer(png, fake_engine):
    """Kết quả OCR không bao giờ được trông như dữ liệu gốc."""
    result = ocr_image.invoke({"file_path": png})
    assert result.startswith(OCR_DISCLAIMER)
    assert "KHÔNG phải dữ liệu gốc" in result


def test_low_confidence_words_are_marked_inline(png, fake_engine):
    """Chữ đọc không chắc phải đánh dấu ngay tại chỗ, không gom vào ghi chú cuối.

    Người đọc cần biết *chữ nào* đáng ngờ. Ở đây "400x200" (conf 22) là con số đi thẳng vào
    khối lượng nếu không ai để ý — đúng chỗ nguy hiểm nhất.
    """
    result = ocr_image.invoke({"file_path": png})

    assert "400x200[?]" in result
    assert "ONG[?]" not in result             # chữ chắc thì không được dán nhãn
    assert "1 từ không chắc" in result


def test_confidence_threshold_is_configurable(png, fake_engine, monkeypatch):
    monkeypatch.setenv("OCR_MIN_CONFIDENCE", "10")
    result = ocr_image.invoke({"file_path": png})
    assert "400x200[?]" not in result

    monkeypatch.setenv("OCR_MIN_CONFIDENCE", "99")
    result = ocr_image.invoke({"file_path": png})
    assert "ONG[?]" in result


def test_title_block_warns_about_scale(png, fake_engine):
    """Tỷ lệ đọc từ khung tên quyết định mọi kích thước quy đổi sau đó."""
    result = ocr_title_block.invoke({"file_path": png})

    assert "TỶ LỆ" in result
    assert "sai tỷ lệ là sai toàn bộ khối lượng" in result.lower()


# --- Đường dẫn và tham số ---------------------------------------------------------


def test_ocr_image_blocks_path_traversal(workspace):
    result = ocr_image.invoke({"file_path": "../../../../etc/passwd"})
    assert "Lỗi OCR" in result


def test_ocr_pdf_blocks_path_traversal(workspace):
    result = ocr_pdf_pages.invoke({"file_path": "../../../../etc/passwd"})
    assert "Lỗi OCR PDF" in result


def test_title_block_blocks_path_traversal(workspace):
    result = ocr_title_block.invoke({"file_path": "../../../../etc/passwd"})
    assert "Lỗi OCR khung tên" in result


def test_missing_file_is_reported_clearly(workspace):
    result = ocr_image.invoke({"file_path": "khong_co.png"})
    assert "không tồn tại" in result


def test_title_block_rejects_bad_region(png, fake_engine):
    result = ocr_title_block.invoke({"file_path": png, "region": "0.9,0,0.1,1"})
    assert "vùng cắt rỗng" in result

    result = ocr_title_block.invoke({"file_path": png, "region": "linh tinh"})
    assert "phải là 'auto'" in result


def test_title_block_crops_the_requested_region(png, fake_engine):
    result = ocr_title_block.invoke({"file_path": png, "region": "0.5,0.6,1,1"})
    assert "(0.5, 0.6, 1.0, 1.0)" in result


def test_dpi_is_capped(workspace, tmp_path, monkeypatch, fake_engine):
    """DPI quá cao chỉ tốn RAM chứ không chính xác hơn — phải bị chặn trần."""
    seen = {}

    def fake_render(pdf_path, indices, dpi):
        seen["dpi"] = dpi
        img = tmp_path / "p.png"
        Image.new("RGB", (50, 50), "white").save(img)
        return [(i + 1, str(img)) for i in indices]

    monkeypatch.setattr(ocr_tools, "_render_pdf_pages", fake_render)
    pdf = tmp_path / "session_ocr" / "scan.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    _write_blank_pdf(pdf, 3)

    ocr_pdf_pages.invoke({"file_path": "scan.pdf", "pages": "1", "dpi": 5000})

    assert seen["dpi"] == ocr_tools.MAX_DPI


# --- OCR PDF ----------------------------------------------------------------------


def _write_blank_pdf(path, pages):
    """PDF tối thiểu, hợp lệ với pypdf — chỉ cần đúng số trang."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    with open(path, "wb") as f:
        writer.write(f)


@pytest.fixture
def scanned_pdf(workspace, tmp_path, monkeypatch):
    pdf = tmp_path / "session_ocr" / "hoso.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    _write_blank_pdf(pdf, 12)

    img = tmp_path / "page.png"
    Image.new("RGB", (100, 100), "white").save(img)
    monkeypatch.setattr(ocr_tools, "_render_pdf_pages",
                        lambda pdf_path, indices, dpi: [(i + 1, str(img)) for i in indices])
    return "hoso.pdf"


def test_ocr_pdf_reads_requested_pages_only(scanned_pdf, fake_engine):
    result = ocr_pdf_pages.invoke({"file_path": scanned_pdf, "pages": "2,5"})

    assert "--- Trang 2 ---" in result
    assert "--- Trang 5 ---" in result
    assert "--- Trang 1 ---" not in result


def test_ocr_pdf_says_how_much_is_left(scanned_pdf, fake_engine):
    """Đọc 5/12 trang mà không nói ra thì người dùng tưởng đã đọc hết cả hồ sơ."""
    result = ocr_pdf_pages.invoke({"file_path": scanned_pdf, "pages": "1-5"})

    assert "Mới đọc 5/12 trang" in result
    assert "pages=" in result


def test_ocr_pdf_rejects_out_of_range_pages(scanned_pdf, fake_engine):
    result = ocr_pdf_pages.invoke({"file_path": scanned_pdf, "pages": "80-90"})
    assert "không khớp trang nào" in result
    assert "12 trang" in result


def test_ocr_pdf_missing_renderer_gives_install_hint(workspace, tmp_path, monkeypatch,
                                                     fake_engine):
    pdf = tmp_path / "session_ocr" / "hoso.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    _write_blank_pdf(pdf, 2)

    def no_renderer(pdf_path, indices, dpi):
        raise RuntimeError(ocr_tools.PDF_RENDER_HINT)

    monkeypatch.setattr(ocr_tools, "_render_pdf_pages", no_renderer)

    result = ocr_pdf_pages.invoke({"file_path": "hoso.pdf", "pages": "1"})

    assert "Lỗi OCR PDF" in result
    assert "poppler" in result.lower()


def test_ocr_pdf_survives_one_broken_page(scanned_pdf, monkeypatch):
    """Một trang hỏng không được làm hỏng cả hồ sơ — nhưng phải nói ra là hỏng mấy trang."""
    calls = {"n": 0}

    def flaky(image_path, lang, psm):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ValueError("trang hỏng")
        return [{"text": "OK", "conf": 99.0, "bbox": (0, 0, 5, 5), "line": (1, 1, 1)}]

    register_ocr_engine("test_flaky", flaky, priority=100)
    try:
        result = ocr_pdf_pages.invoke({"file_path": scanned_pdf, "pages": "1-3"})
    finally:
        unregister_ocr_engine("test_flaky")

    assert "--- Trang 1 ---" in result
    assert "--- Trang 3 ---" in result
    assert "1 trang OCR hỏng: [2]" in result


# --- Đăng ký tool ------------------------------------------------------------------


def test_ocr_tools_are_bound_to_roles():
    """Tool không nằm trong TOOLS_BY_ROLE thì agent không bao giờ gọi được — đúng lỗi mà
    `detect_cad_symbols_yolo` từng mắc (xem TECH_DEBT.md mục 5)."""
    from src.tools import get_tools_for_role, tools

    names = {t.name for t in tools}
    assert {"ocr_image", "ocr_pdf_pages", "ocr_title_block"} <= names

    for role in ("qs", "cad", "bim"):
        role_names = {t.name for t in get_tools_for_role(role)}
        assert "ocr_title_block" in role_names, role
        assert "ocr_pdf_pages" in role_names, role

    # Hồ sơ scan tới với mọi bộ phận, nên hai tool đọc nằm ở bộ chung.
    for role in ("mechanical", "electrical", "plumbing", "firefighting"):
        role_names = {t.name for t in get_tools_for_role(role)}
        assert "ocr_pdf_pages" in role_names, role


def test_scanned_pdf_message_points_at_the_ocr_tool(workspace, tmp_path):
    """`read_pdf` phát hiện bản scan thì phải chỉ đúng tên tool đọc được nó."""
    from src.tools import read_pdf

    pdf = tmp_path / "session_ocr" / "scan.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    _write_blank_pdf(pdf, 4)

    result = read_pdf.invoke({"file_path": "scan.pdf"})

    assert "ocr_pdf_pages" in result
