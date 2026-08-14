"""OCR — đọc chữ từ ảnh và từ PDF bản scan.

Vì sao có module này: `read_pdf` nay **phát hiện** được PDF không có lớp văn bản, nhưng
phát hiện xong vẫn không đọc được gì. Hồ sơ thầu MEPF ở Việt Nam rất hay ở dạng photo/scan,
nên thiếu OCR là một vùng mù hoàn toàn. Xem `docs/DAC_TA_TOOL_AI.md` mục 3.1.

Hai ràng buộc chi phối thiết kế ở đây, đều xuất phát từ nguyên tắc của dự án:

1. **OCR *là* một mô hình đoán.** Nguyên tắc số 1 nói LLM không được sinh số kỹ thuật; số
   do OCR đọc ra cũng không đủ tư cách đi thẳng vào bảng khối lượng. Vì vậy mọi kết quả
   đều mang cảnh báo cố định, và ký tự đọc không chắc bị đánh dấu `[?]` ngay trong chuỗi
   trả về — chứ không giấu độ tin cậy vào log.
2. **Thiếu engine thì nói rõ cách cài, không sập** (nguyên tắc "graceful fallback"). Mẫu
   ngôn từ lấy theo `ODA_INSTALL_HINT` của `cad_loader.py`.

Engine là **điểm nối tường minh**, cùng khuôn với `standards_backend.register_backend`:
muốn thêm PaddleOCR hay một engine nội bộ thì gọi `register_ocr_engine`, không gán đè hàm
của module này (xem `TECH_DEBT.md` mục 10).

Hợp đồng của một engine:

    fn(image_path: str, lang: str, psm: int) -> list[dict]

mỗi phần tử là một khối chữ: ``{"text": str, "conf": float 0–100, "bbox": (l, t, w, h)}``.
Engine chỉ nhận diện; việc lọc ngưỡng, đánh dấu `[?]`, ghép dòng, cảnh báo là của module
này — để mọi engine cho ra cùng một khuôn kết quả.
"""
from __future__ import annotations

import logging
import os
import threading

from langchain_core.tools import tool

from src.workspace import resolve_safe_path

logger = logging.getLogger(__name__)

#: Dưới ngưỡng này, chữ bị đánh dấu `[?]` để người đọc (LLM rồi tới kỹ sư) biết là chưa chắc.
DEFAULT_MIN_CONFIDENCE = 60.0

#: Trần DPI khi render PDF. Cao hơn hầu như không tăng độ chính xác mà RAM tăng tuyến tính.
MAX_DPI = 600

TESSERACT_INSTALL_HINT = (
    "Chưa có engine OCR nào dùng được. Cách xử lý:\n"
    "  1) Cài gói hệ thống: apt-get install tesseract-ocr tesseract-ocr-vie poppler-utils "
    "(macOS: brew install tesseract tesseract-lang poppler); rồi\n"
    "  2) Cài phụ thuộc Python: uv sync --extra ocr; hoặc\n"
    "  3) Đăng ký engine riêng bằng src.ocr_tools.register_ocr_engine(tên, hàm, ưu tiên)."
)

PDF_RENDER_HINT = (
    "Không render được trang PDF thành ảnh để OCR. Cần một trong hai:\n"
    "  - poppler-utils + pdf2image (apt-get install poppler-utils && uv sync --extra ocr), hoặc\n"
    "  - PyMuPDF (uv add pymupdf)."
)

#: Cảnh báo bắt buộc đứng đầu mọi kết quả OCR. Cố định, không tùy biến theo lời gọi: nó là
#: ranh giới nghiệp vụ, không phải chi tiết trình bày.
OCR_DISCLAIMER = (
    "[OCR — SỐ LIỆU CẦN NGƯỜI XÁC NHẬN] Nội dung dưới đây do máy đọc từ ảnh, KHÔNG phải dữ "
    "liệu gốc. Không được đưa thẳng số đọc được vào bảng khối lượng hay dự toán khi chưa "
    "đối chiếu bản vẽ/hồ sơ gốc. Chữ đánh dấu [?] là chữ máy đọc không chắc."
)

_LOCK = threading.Lock()
_ENGINES: dict[str, tuple[int, object]] = {}


# --- Điểm nối engine ---------------------------------------------------------------


def register_ocr_engine(name: str, fn, priority: int = 0) -> None:
    """Đăng ký một engine OCR. `fn(image_path, lang, psm) -> list[dict]`."""
    with _LOCK:
        _ENGINES[name] = (priority, fn)
    logger.info("OCR engine đã đăng ký: %s (ưu tiên %s)", name, priority)


def unregister_ocr_engine(name: str) -> None:
    with _LOCK:
        _ENGINES.pop(name, None)


def registered_ocr_engines() -> list[str]:
    """Tên các engine, xếp từ ưu tiên cao xuống thấp."""
    with _LOCK:
        items = sorted(_ENGINES.items(), key=lambda kv: kv[1][0], reverse=True)
    return [name for name, _ in items]


def _tesseract_engine(image_path: str, lang: str, psm: int) -> list[dict]:
    """Engine mặc định. Chỉ import `pytesseract` khi thực sự chạy, để máy chưa cài vẫn
    nạp được module (và vẫn thấy tool trong danh sách, kèm hướng dẫn cài)."""
    import pytesseract
    from PIL import Image

    data = pytesseract.image_to_data(
        Image.open(image_path), lang=lang, config=f"--psm {int(psm)}",
        output_type=pytesseract.Output.DICT,
    )
    blocks = []
    for i, word in enumerate(data.get("text", [])):
        if not str(word).strip():
            continue
        try:
            conf = float(data["conf"][i])
        except (KeyError, IndexError, TypeError, ValueError):
            conf = -1.0
        blocks.append({
            "text": str(word),
            "conf": conf,
            "bbox": (data["left"][i], data["top"][i], data["width"][i], data["height"][i]),
            "line": (data.get("block_num", [0] * (i + 1))[i],
                     data.get("par_num", [0] * (i + 1))[i],
                     data.get("line_num", [0] * (i + 1))[i]),
        })
    return blocks


register_ocr_engine("tesseract", _tesseract_engine, priority=0)


def _run_engine(image_path: str, lang: str, psm: int) -> tuple[list[dict], str]:
    """Chạy engine ưu tiên cao nhất, hỏng thì lùi dần. Trả `(blocks, tên engine)`.

    Ném `RuntimeError` kèm hướng dẫn cài khi không engine nào chạy được — người gọi (tool)
    bắt lại và trả về chuỗi, vì hợp đồng của tool là lỗi-là-kết-quả.
    """
    errors = []
    for name in registered_ocr_engines():
        with _LOCK:
            entry = _ENGINES.get(name)
        if not entry:
            continue
        try:
            return entry[1](image_path, lang, psm), name
        except Exception as e:            # engine thiếu hoặc hỏng → thử engine kế tiếp
            logger.warning("OCR engine '%s' không chạy được: %s", name, e)
            errors.append(f"{name}: {e}")
    detail = ("\nChi tiết: " + "; ".join(errors)) if errors else ""
    raise RuntimeError(TESSERACT_INSTALL_HINT + detail)


# --- Định dạng kết quả -------------------------------------------------------------


def _min_confidence() -> float:
    try:
        return float(os.environ.get("OCR_MIN_CONFIDENCE", DEFAULT_MIN_CONFIDENCE))
    except ValueError:
        return DEFAULT_MIN_CONFIDENCE


def _format_blocks(blocks: list[dict]) -> tuple[str, int, int]:
    """`(văn bản đã ghép, số từ, số từ đọc không chắc)`.

    Từ dưới ngưỡng tin cậy được dán `[?]` **ngay cạnh từ đó**, không gom thành một ghi chú
    ở cuối: người đọc cần biết *chữ nào* đáng ngờ, chứ không phải "có mấy chữ đáng ngờ".
    """
    threshold = _min_confidence()
    lines: dict[tuple, list[str]] = {}
    low = 0
    for i, block in enumerate(blocks):
        text = str(block.get("text", "")).strip()
        if not text:
            continue
        conf = float(block.get("conf", -1) or -1)
        if 0 <= conf < threshold:
            text += "[?]"
            low += 1
        lines.setdefault(block.get("line", (0, 0, i)), []).append(text)
    body = "\n".join(" ".join(words) for words in lines.values())
    return body, sum(len(w) for w in lines.values()), low


def _ocr_one_image(image_path: str, lang: str, psm: int) -> tuple[str, str]:
    """`(văn bản đã định dạng kèm thống kê, tên engine)`."""
    blocks, engine = _run_engine(image_path, lang, psm)
    body, total, low = _format_blocks(blocks)
    if not total:
        return ("Không đọc được chữ nào từ ảnh này. Có thể ảnh quá mờ, nghiêng, hoặc thực "
                "sự không chứa chữ.", engine)
    note = f"[Đọc được {total} từ, trong đó {low} từ không chắc (đã đánh dấu [?]).]"
    return f"{body}\n{note}", engine


# --- Render PDF → ảnh --------------------------------------------------------------


def _parse_pages(spec: str, total: int) -> list[int]:
    """Dùng chung bộ phân tích khoảng trang của `read_pdf` để hai tool không lệch cú pháp."""
    from src.tools import _parse_page_range
    return _parse_page_range(spec, total)


def _render_pdf_pages(pdf_path: str, indices: list[int], dpi: int) -> list[tuple[int, str]]:
    """`[(số trang đếm từ 1, đường dẫn ảnh tạm)]`. Ném `RuntimeError` nếu không render được."""
    import tempfile

    out_dir = tempfile.mkdtemp(prefix="ocr_pdf_")
    rendered: list[tuple[int, str]] = []

    try:
        import fitz                                    # PyMuPDF — không cần gói hệ thống
        doc = fitz.open(pdf_path)
        try:
            for i in indices:
                pix = doc.load_page(i).get_pixmap(dpi=dpi)
                path = os.path.join(out_dir, f"page_{i + 1}.png")
                pix.save(path)
                rendered.append((i + 1, path))
        finally:
            doc.close()
        return rendered
    except ImportError:
        pass

    try:
        from pdf2image import convert_from_path
    except ImportError as e:
        raise RuntimeError(PDF_RENDER_HINT) from e

    for i in indices:
        images = convert_from_path(pdf_path, dpi=dpi, first_page=i + 1, last_page=i + 1)
        if not images:
            continue
        path = os.path.join(out_dir, f"page_{i + 1}.png")
        images[0].save(path)
        rendered.append((i + 1, path))
    return rendered


# --- Tool --------------------------------------------------------------------------


@tool
def ocr_image(file_path: str, lang: str = "vie+eng", psm: int = 6) -> str:
    """Đọc chữ từ ảnh (PNG/JPG/TIFF) bằng OCR cục bộ — dùng cho bản vẽ scan, ảnh chụp hồ sơ,
    ảnh render từ bản vẽ CAD. `psm` là chế độ phân tích bố cục của Tesseract (6 = một khối
    chữ; 11 = chữ rải rác, hợp với ghi chú trên bản vẽ).

    Kết quả là số liệu THAM KHẢO cần người xác nhận, không được đưa thẳng vào bảng khối
    lượng hay dự toán.
    """
    logger.info("OCR image: %s (lang=%s, psm=%s)", file_path, lang, psm)
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return f"Lỗi OCR: {e}"
    if not os.path.exists(safe_path):
        return f"Lỗi OCR: ảnh '{file_path}' không tồn tại trong thư mục làm việc."

    try:
        body, engine = _ocr_one_image(safe_path, lang, psm)
    except RuntimeError as e:
        return f"Lỗi OCR: {e}"
    except Exception as e:
        return f"Lỗi OCR: {e}"
    return f"{OCR_DISCLAIMER}\n\nKết quả OCR '{file_path}' (engine: {engine}):\n{body}"


@tool
def ocr_pdf_pages(file_path: str, pages: str = "1-5", dpi: int = 300) -> str:
    """Đọc chữ từ các trang của một PDF bản scan (không có lớp văn bản). `pages` dạng '1-5'
    hoặc '2,7,9'.

    Dùng khi `read_pdf` đã báo file không có lớp văn bản. PDF có sẵn lớp văn bản thì luôn
    ưu tiên `read_pdf` — đọc trực tiếp vừa nhanh vừa chính xác tuyệt đối, còn OCR là đoán.

    Mặc định chỉ 5 trang: OCR tốn thời gian và RAM, ép chọn khoảng trang là cố ý.
    """
    logger.info("OCR PDF: %s (pages=%s, dpi=%s)", file_path, pages, dpi)
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return f"Lỗi OCR PDF: {e}"
    if not os.path.exists(safe_path):
        return f"Lỗi OCR PDF: file '{file_path}' không tồn tại trong thư mục làm việc."

    dpi = max(72, min(int(dpi or 300), MAX_DPI))

    try:
        from pypdf import PdfReader
        total = len(PdfReader(safe_path).pages)
    except Exception as e:
        return f"Lỗi OCR PDF: không đọc được cấu trúc PDF ({e})."

    indices = _parse_pages(pages, total)
    if not indices:
        return (f"Lỗi OCR PDF: khoảng trang '{pages}' không khớp trang nào "
                f"(file có {total} trang).")

    try:
        rendered = _render_pdf_pages(safe_path, indices, dpi)
    except RuntimeError as e:
        return f"Lỗi OCR PDF: {e}"

    if not rendered:
        return f"Lỗi OCR PDF: không render được trang nào trong '{pages}'."

    parts, engine, failed = [], "?", []
    for page_no, image_path in rendered:
        try:
            body, engine = _ocr_one_image(image_path, "vie+eng", 6)
        except Exception as e:
            # Hai loại hỏng khác hẳn nhau, và `_run_engine` gộp chúng vào cùng một
            # RuntimeError vì nó chỉ biết "engine vừa ném": (a) máy không có engine nào —
            # vô ích khi thử tiếp, phải báo hướng dẫn cài; (b) riêng trang này đọc hỏng —
            # bỏ trang đó, các trang còn lại vẫn đọc được. Phân biệt bằng chỗ đã có trang
            # nào đọc xong chưa: đã xong ít nhất một trang nghĩa là engine chạy được.
            if not parts:
                return f"Lỗi OCR PDF: {e}"
            failed.append(page_no)
            logger.warning("OCR trang %d hỏng: %s", page_no, e)
            continue
        parts.append(f"--- Trang {page_no} ---\n{body}")

    if not parts:
        return f"Lỗi OCR PDF: không trang nào đọc được (đã thử {len(rendered)} trang)."

    head = (f"Kết quả OCR '{file_path}' — {len(parts)}/{total} trang, {dpi} DPI "
            f"(engine: {engine}):")
    tail = ""
    if failed:
        tail += f"\n[Cảnh báo: {len(failed)} trang OCR hỏng: {failed}.]"
    if len(indices) < total:
        tail += (f"\n[Mới đọc {len(indices)}/{total} trang. Đọc tiếp bằng tham số "
                 f"pages='<khoảng trang tiếp theo>'.]")
    return f"{OCR_DISCLAIMER}\n\n{head}\n" + "\n\n".join(parts) + tail


@tool
def ocr_title_block(file_path: str, region: str = "auto") -> str:
    """Đọc khung tên bản vẽ từ ảnh (tên dự án, số hiệu bản vẽ, tỷ lệ, ngày, người duyệt).

    `region='auto'` cắt 1/4 dưới-phải của ảnh — vị trí khung tên theo TCVN 7285. Muốn vùng
    khác thì đưa 'trái,trên,phải,dưới' theo tỷ lệ 0–1, VD '0.5,0.6,1,1'.

    **Tỷ lệ đọc được từ khung tên là dữ kiện quan trọng**: nó quyết định mọi kích thước quy
    đổi sau đó. Sai tỷ lệ thì sai toàn bộ khối lượng, nên con số này luôn phải được người
    xác nhận trước khi dùng để tính.
    """
    logger.info("OCR title block: %s (region=%s)", file_path, region)
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return f"Lỗi OCR khung tên: {e}"
    if not os.path.exists(safe_path):
        return f"Lỗi OCR khung tên: ảnh '{file_path}' không tồn tại trong thư mục làm việc."

    try:
        from PIL import Image
    except ImportError:
        return "Lỗi OCR khung tên: thiếu Pillow (uv sync)."

    if region.strip().lower() == "auto":
        box_ratio = (0.5, 0.6, 1.0, 1.0)
    else:
        try:
            parts = [float(x) for x in region.split(",")]
            if len(parts) != 4:
                raise ValueError
            box_ratio = tuple(min(max(p, 0.0), 1.0) for p in parts)
        except ValueError:
            return ("Lỗi OCR khung tên: `region` phải là 'auto' hoặc bốn số "
                    "'trái,trên,phải,dưới' trong khoảng 0–1, VD '0.5,0.6,1,1'.")
        if box_ratio[0] >= box_ratio[2] or box_ratio[1] >= box_ratio[3]:
            return "Lỗi OCR khung tên: vùng cắt rỗng (trái ≥ phải hoặc trên ≥ dưới)."

    import tempfile
    try:
        with Image.open(safe_path) as img:
            w, h = img.size
            box = (int(box_ratio[0] * w), int(box_ratio[1] * h),
                   int(box_ratio[2] * w), int(box_ratio[3] * h))
            crop_path = os.path.join(tempfile.mkdtemp(prefix="ocr_title_"), "title.png")
            img.crop(box).save(crop_path)
    except Exception as e:
        return f"Lỗi OCR khung tên: không cắt được vùng khung tên ({e})."

    try:
        # psm 11 (chữ rải rác) hợp với khung tên hơn psm 6: các ô trong khung tên là những
        # cụm chữ rời, không phải một khối văn bản liền mạch.
        body, engine = _ocr_one_image(crop_path, "vie+eng", 11)
    except RuntimeError as e:
        return f"Lỗi OCR khung tên: {e}"
    except Exception as e:
        return f"Lỗi OCR khung tên: {e}"

    return (f"{OCR_DISCLAIMER}\n\nKhung tên đọc từ '{file_path}' "
            f"(vùng {box_ratio}, engine: {engine}):\n{body}\n"
            f"[Nếu đọc được TỶ LỆ bản vẽ, phải để kỹ sư xác nhận trước khi dùng để quy đổi "
            f"kích thước — sai tỷ lệ là sai toàn bộ khối lượng.]")
