"""Canh ba chỗ `read_pdf` / `read_excel` từng bỏ sót dữ liệu mà không nói.

Mỗi test dưới đây khẳng định cảnh báo nằm trong **chuỗi trả về** của tool, không phải
trong log — vì chuỗi trả về mới là thứ agent đọc và chuyển tiếp cho người dùng. Ba lỗi
gốc (xem `docs/DAC_TA_TOOL_AI.md` mục 2.1–2.3):

1. PDF bản scan → trả chuỗi rỗng nhưng vẫn báo đủ số trang.
2. `read_pdf` cắt ở 5000 ký tự, luôn dán "..." kể cả khi không cắt.
3. `read_excel` chỉ đọc sheet đầu tiên, không nói là file còn sheet khác.
"""
import pandas as pd
import pytest

from src.tools import read_excel, read_pdf
from src.workspace import set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    return set_workspace_dir(str(tmp_path / "session_read"))


def _write_pdf(path, pages_text):
    """Dựng PDF thô với `pages_text` là nội dung từng trang (None = trang không có chữ).

    Viết thẳng cấu trúc PDF thay vì dùng `PdfWriter.add_blank_page` + content stream: một
    trang chỉ rút được chữ khi content stream tham chiếu tới một font **có khai báo trong
    /Resources**. Thiếu khai báo đó thì `extract_text()` trả về rỗng và bài test "trang có
    chữ" sẽ vô tình kiểm tra đúng nhánh bản scan — tức là luôn xanh mà không kiểm gì.
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)          # số hiệu object, đếm từ 1

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    # /Pages đứng ngay sau font (1) và 2 object mỗi trang (content + page).
    pages_id = len(pages_text) * 2 + 2      # biết trước để trang trỏ ngược về /Parent

    for text in pages_text:
        stream = (f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode()
                  if text else b"")
        content = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        page_ids.append(add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (pages_id, font, content)
        ))

    kids = b" ".join(b"%d 0 R" % pid for pid in page_ids)
    tree = add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids)))
    assert tree == pages_id, "số hiệu object của /Pages phải khớp giá trị /Parent đã ghi"
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % tree)

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (num, body)

    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets[1:]:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, catalog, xref_at))

    path.write_bytes(bytes(out))


# --- 1. PDF bản scan -------------------------------------------------------------


def test_scanned_pdf_reports_no_text_layer(workspace, tmp_path):
    """Toàn trang trống = bản scan. Không được trả về chuỗi rỗng trông hợp lệ."""
    path = tmp_path / "session_read" / "scan.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_pdf(path, [None] * 6)

    result = read_pdf.invoke({"file_path": "scan.pdf"})

    assert "KHÔNG có lớp văn bản" in result
    assert "OCR" in result
    # Lỗi gốc: chỉ báo số trang rồi thôi, người đọc tưởng file rỗng.
    assert "Đừng kết luận file này không có nội dung" in result


def test_partially_scanned_pdf_warns_about_empty_pages(workspace, tmp_path):
    """Vài trang không có chữ giữa một file có chữ → vẫn phải nói ra."""
    path = tmp_path / "session_read" / "hon_hop.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_pdf(path, ["ONG GIO 400x200 DAI 24 M", "BANG THONG KE VAT TU", None])

    result = read_pdf.invoke({"file_path": "hon_hop.pdf"})

    assert "ONG GIO 400x200" in result
    assert "1/3 trang không rút được chữ" in result


# --- 2. Cắt ngắn phải khai báo, và chỉ khi cắt thật -------------------------------


def test_short_pdf_has_no_truncation_notice(workspace, tmp_path):
    """Không cắt thì không được có dấu hiệu cắt — lỗi gốc luôn dán '...'."""
    path = tmp_path / "session_read" / "ngan.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_pdf(path, ["TONG HOP KHOI LUONG PHAN DIEN TANG 3"])

    result = read_pdf.invoke({"file_path": "ngan.pdf"})

    assert "TONG HOP KHOI LUONG" in result
    assert "Đã cắt" not in result
    assert not result.rstrip().endswith("...")


def test_truncated_pdf_declares_how_much_was_dropped(workspace, tmp_path):
    path = tmp_path / "session_read" / "dai.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_pdf(path, ["ONG NUOC DN100 " * 40 for _ in range(6)])

    result = read_pdf.invoke({"file_path": "dai.pdf", "max_chars": 200})

    assert "Đã cắt" in result
    assert "ký tự" in result          # nói rõ mất bao nhiêu
    assert "pages=" in result         # và nói cách đọc tiếp


def test_pdf_page_range_is_honoured(workspace, tmp_path):
    path = tmp_path / "session_read" / "chon_trang.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_pdf(path, ["TRANG MOT", "TRANG HAI", "TRANG BA"])

    result = read_pdf.invoke({"file_path": "chon_trang.pdf", "pages": "2"})

    assert "TRANG HAI" in result
    assert "TRANG MOT" not in result
    assert "--- Trang 2 ---" in result


def test_page_with_little_text_is_not_called_a_scan(workspace, tmp_path):
    """Rút được chữ thì phải trả chữ, dù ít.

    Bản nháp đầu dùng ngưỡng 20 ký tự/trang để đoán bản scan; một trang chỉ có "TRANG HAI"
    liền bị thay bằng câu báo scan — tức là tool tự giấu mất nội dung đọc được, đúng cái
    lỗi mà cả nhánh này sinh ra để vá.
    """
    path = tmp_path / "session_read" / "it_chu.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_pdf(path, ["DN100"])

    result = read_pdf.invoke({"file_path": "it_chu.pdf"})

    assert "DN100" in result
    assert "KHÔNG có lớp văn bản" not in result


def test_pdf_blocks_path_traversal(workspace):
    result = read_pdf.invoke({"file_path": "../../../../etc/passwd"})
    assert "Lỗi đọc PDF" in result


# --- 3. Excel nhiều sheet --------------------------------------------------------


def _write_multisheet(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"Hang muc": ["Tong cong"], "Thanh tien": [1_000]}).to_excel(
            writer, sheet_name="TONG HOP", index=False)
        pd.DataFrame({"Hang muc": ["Cap CV 3x50"], "KL": [120]}).to_excel(
            writer, sheet_name="DIEN", index=False)
        pd.DataFrame({"Hang muc": ["Ong PPR DN32"], "KL": [85]}).to_excel(
            writer, sheet_name="NUOC", index=False)


def test_read_excel_names_the_sheets_it_did_not_read(workspace, tmp_path):
    """Lỗi gốc: đọc sheet đầu rồi trả về như thể đó là toàn bộ file."""
    path = tmp_path / "session_read" / "boq.xlsx"
    _write_multisheet(path)

    result = read_excel.invoke({"file_path": "boq.xlsx"})

    assert "TONG HOP" in result and "Tong cong" in result
    assert "CHƯA đọc" in result
    assert "DIEN" in result and "NUOC" in result       # nêu đích danh, không nói chung chung


def test_read_excel_can_target_a_named_sheet(workspace, tmp_path):
    path = tmp_path / "session_read" / "boq.xlsx"
    _write_multisheet(path)

    result = read_excel.invoke({"file_path": "boq.xlsx", "sheet": "NUOC"})

    assert "Ong PPR DN32" in result
    assert "Cap CV 3x50" not in result


def test_read_excel_unknown_sheet_lists_the_real_ones(workspace, tmp_path):
    path = tmp_path / "session_read" / "boq.xlsx"
    _write_multisheet(path)

    result = read_excel.invoke({"file_path": "boq.xlsx", "sheet": "PCCC"})

    assert "Lỗi đọc Excel" in result
    assert "TONG HOP" in result and "DIEN" in result


def test_single_sheet_file_has_no_leftover_notice(workspace, tmp_path):
    path = tmp_path / "session_read" / "mot_sheet.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"a": [1]}).to_excel(path, index=False)

    result = read_excel.invoke({"file_path": "mot_sheet.xlsx"})

    assert "CHƯA đọc" not in result


def test_read_excel_paginates_large_sheet(workspace, tmp_path):
    """Bảng lớn phải cắt CÓ khai báo và CÓ đường đọc tiếp, thay vì nhồi hết vào ngữ cảnh."""
    path = tmp_path / "session_read" / "lon.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"stt": range(500), "ten": [f"hang muc {i}" for i in range(500)]}).to_excel(
        path, index=False)

    first = read_excel.invoke({"file_path": "lon.xlsx", "max_rows": 10})
    assert "hang muc 0" in first
    assert "hang muc 400" not in first
    assert "Đã cắt: hiển thị dòng 1–10/500" in first
    assert "offset=10" in first

    second = read_excel.invoke({"file_path": "lon.xlsx", "max_rows": 10, "offset": 10})
    assert "hang muc 12" in second
    assert "hang muc 0 " not in second
