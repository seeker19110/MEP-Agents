"""Nạp bản vẽ: hỗ trợ DWG và gộp nội dung XREF.

Hai khoảng trống khiến hệ thống bóc thiếu hoặc từ chối file của khách:

1. **DWG.** `ezdxf` chỉ đọc được DXF, trong khi `.dwg` mới là định dạng gốc phổ biến
   nhất của AutoCAD. Trước đây khách gửi `.dwg` là phải tự convert. Module này tự gọi
   **ODA File Converter** (miễn phí) nếu máy có cài, và nếu chưa cài thì nói rõ cách cài
   thay vì báo một lỗi khó hiểu.

2. **XREF (external reference).** Hồ sơ lớn thường tách nền kiến trúc và từng hệ ra file
   riêng rồi ghép bằng XREF. Đọc `modelspace()` của file chính sẽ **không thấy một
   entity nào** nằm trong xref — bóc khối lượng ra kết quả thiếu trầm trọng mà không có
   dấu hiệu cảnh báo nào. Ở đây xref được nạp từ file đi kèm, áp ma trận biến đổi của
   khối tham chiếu, và gộp vào danh sách entity trả về.
"""
import logging
import math
import os
import shutil
import subprocess
import tempfile

import ezdxf

from src import cad_geometry
from src.workspace import resolve_safe_path

logger = logging.getLogger(__name__)

# Tên/đường dẫn ODA File Converter. Cho phép ghi đè bằng biến môi trường vì mỗi hệ điều
# hành cài ở một chỗ khác nhau.
ODA_CONVERTER_CANDIDATES = (
    "ODAFileConverter",
    "ODAFileConverter.exe",
    "/usr/bin/ODAFileConverter",
    "/opt/ODAFileConverter/ODAFileConverter",
    "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
)

ODA_INSTALL_HINT = (
    "Chưa tìm thấy ODA File Converter để chuyển .dwg sang .dxf. Cách xử lý:\n"
    "  1) Cài ODA File Converter (miễn phí) tại https://www.opendesign.com/guestfiles/oda_file_converter "
    "rồi đặt đường dẫn vào biến môi trường ODA_CONVERTER_PATH; hoặc\n"
    "  2) Mở bản vẽ bằng AutoCAD/BricsCAD và tự lưu thành .dxf rồi tải lên lại."
)


def find_oda_converter() -> str:
    """Đường dẫn ODA File Converter nếu có trên máy, ngược lại chuỗi rỗng."""
    configured = os.getenv("ODA_CONVERTER_PATH", "").strip()
    if configured and os.path.exists(configured):
        return configured
    for candidate in ODA_CONVERTER_CANDIDATES:
        found = shutil.which(candidate) if os.path.basename(candidate) == candidate else (
            candidate if os.path.exists(candidate) else None
        )
        if found:
            return found
    return ""


def convert_dwg_to_dxf(dwg_path: str, output_dir: str = None, timeout: int = 180) -> str:
    """Chuyển một file .dwg sang .dxf bằng ODA File Converter. Trả về đường dẫn .dxf.

    Ném `RuntimeError` kèm hướng dẫn cài đặt nếu máy chưa có converter — thà nói rõ còn
    hơn để người dùng nhận một lỗi parse khó hiểu từ ezdxf.
    """
    converter = find_oda_converter()
    if not converter:
        raise RuntimeError(ODA_INSTALL_HINT)

    src_dir = os.path.dirname(os.path.abspath(dwg_path))
    out_dir = output_dir or tempfile.mkdtemp(prefix="dwg2dxf_")
    os.makedirs(out_dir, exist_ok=True)

    # Cú pháp: ODAFileConverter <thư mục vào> <thư mục ra> <phiên bản> <định dạng>
    #          <đệ quy> <audit> <bộ lọc tên file>
    cmd = [converter, src_dir, out_dir, "ACAD2018", "DXF", "0", "1",
           os.path.basename(dwg_path)]
    logger.info("Converting DWG -> DXF: %s", dwg_path)
    try:
        subprocess.run(cmd, check=False, timeout=timeout,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ODA File Converter chạy quá {timeout}s và bị dừng.") from exc

    expected = os.path.join(out_dir, os.path.splitext(os.path.basename(dwg_path))[0] + ".dxf")
    if not os.path.exists(expected):
        raise RuntimeError(
            f"ODA File Converter chạy xong nhưng không tạo ra '{os.path.basename(expected)}'. "
            f"File .dwg có thể bị lỗi hoặc thuộc phiên bản converter không hỗ trợ."
        )
    return expected


def load_drawing(file_path: str):
    """Nạp bản vẽ .dxf hoặc .dwg. Trả về `(doc, notes)` với `notes` là ghi chú cho người dùng.

    `.dwg` được tự chuyển sang `.dxf` (đặt cạnh file gốc trong workspace để tái sử dụng
    cho các lần gọi tool sau, khỏi convert lại).
    """
    safe_path = resolve_safe_path(file_path)
    notes = []

    if safe_path.lower().endswith(".dwg"):
        converted = os.path.splitext(safe_path)[0] + ".dxf"
        if os.path.exists(converted) and os.path.getmtime(converted) >= os.path.getmtime(safe_path):
            notes.append(f"Dùng lại bản .dxf đã chuyển đổi trước đó: {os.path.basename(converted)}")
        else:
            produced = convert_dwg_to_dxf(safe_path, output_dir=os.path.dirname(safe_path))
            if os.path.abspath(produced) != os.path.abspath(converted):
                shutil.move(produced, converted)
            notes.append(f"Đã tự chuyển .dwg sang .dxf: {os.path.basename(converted)}")
        safe_path = converted

    return ezdxf.readfile(safe_path), notes


def list_xrefs(doc):
    """Danh sách XREF khai báo trong bản vẽ: [(tên khối, đường dẫn file)]."""
    xrefs = []
    for block in doc.blocks:
        if cad_geometry.is_xref_block(block):
            path = getattr(block.block.dxf, "xref_path", "") or ""
            if path:
                xrefs.append((block.name, path))
    return xrefs


def _transform_point(point, insert, xscale, yscale, rotation_deg):
    """Đưa một điểm từ hệ tọa độ của xref về hệ tọa độ bản vẽ chính."""
    x, y = point[0] * xscale, point[1] * yscale
    if rotation_deg:
        rad = math.radians(rotation_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        x, y = x * cos_a - y * sin_a, x * sin_a + y * cos_a
    z = (point[2] if len(point) > 2 else 0.0)
    return (x + insert[0], y + insert[1], z + (insert[2] if len(insert) > 2 else 0.0))


def resolve_xref_segments(doc, base_dir: str, collect_segments_fn):
    """Đo chiều dài các tuyến nằm TRONG xref, quy về tọa độ bản vẽ chính.

    Trả về `(segments, notes)`. Xref không tìm thấy file đi kèm sẽ được nêu tên trong
    `notes` — người dùng phải biết bản vẽ còn thiếu phần nào, thay vì nhận một con số
    khối lượng thiếu mà tưởng là đủ.
    """
    segments, notes = [], []
    xref_defs = {name: path for name, path in list_xrefs(doc)}
    if not xref_defs:
        return segments, notes

    msp = doc.modelspace()
    inserts = [e for e in msp if e.dxftype() == "INSERT" and e.dxf.name in xref_defs]
    if not inserts:
        notes.append(f"Bản vẽ khai báo {len(xref_defs)} XREF nhưng không chèn ở modelspace.")
        return segments, notes

    for insert in inserts:
        name = insert.dxf.name
        raw_path = xref_defs[name]
        candidates = [raw_path, os.path.join(base_dir, os.path.basename(raw_path))]
        found = next((p for p in candidates if p and os.path.exists(p)), "")
        if not found:
            notes.append(
                f"KHÔNG tìm thấy file XREF '{os.path.basename(raw_path)}' (khối '{name}') — "
                f"toàn bộ nội dung trong xref này KHÔNG được tính vào khối lượng. "
                f"Hãy tải file xref lên cùng thư mục rồi chạy lại."
            )
            continue

        try:
            xdoc = ezdxf.readfile(found)
        except Exception as exc:
            notes.append(f"Không đọc được XREF '{os.path.basename(found)}': {exc}")
            continue

        base = (insert.dxf.insert.x, insert.dxf.insert.y, getattr(insert.dxf.insert, "z", 0.0) or 0.0)
        xscale = float(getattr(insert.dxf, "xscale", 1.0) or 1.0)
        yscale = float(getattr(insert.dxf, "yscale", 1.0) or 1.0)
        rotation = float(getattr(insert.dxf, "rotation", 0.0) or 0.0)
        scale_factor = math.sqrt(abs(xscale * yscale)) or 1.0

        for seg in collect_segments_fn(xdoc.modelspace()):
            item = dict(seg)
            item["start"] = _transform_point(seg["start"], base, xscale, yscale, rotation)
            item["end"] = _transform_point(seg["end"], base, xscale, yscale, rotation)
            item["length"] = seg["length"] * scale_factor
            item["from_xref"] = name
            segments.append(item)

        notes.append(f"Đã gộp nội dung XREF '{os.path.basename(found)}' (khối '{name}') vào kết quả.")

    return segments, notes
