"""Theo dõi phiên bản (revision) bản vẽ CAD giữa các lần chỉnh sửa.

Các tool sửa bản vẽ (`edit_cad`, `optimize_cad_drawing`, `ai_block_recovery`) ghi đè
file **tại chỗ**: một lần AI sửa sai là bản gốc mất luôn, người dùng không có đường lùi
và cũng không có cách nào biết AI đã đổi đúng những gì. Module này bù cả hai:

- `snapshot_cad`: chụp lại bản vẽ vào kho revision trước khi sửa (tự động gọi bởi các
  tool sửa bản vẽ, hoặc gọi tay).
- `list_cad_revisions` / `diff_cad_revisions`: xem lịch sử và so sánh hai phiên bản
  (số Block theo tên, chiều dài theo Layer, danh sách Layer) để biết chính xác lần sửa
  vừa rồi đã thêm/bớt cái gì.
- `restore_cad_revision`: quay lại một phiên bản trước.

Toàn bộ so sánh là thống kê hình học xác định, không cần LLM.
"""
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime

import ezdxf
from langchain_core.tools import tool

from src import cad_geometry
from src.config import settings
from src.workspace import get_workspace_dir, resolve_safe_path

logger = logging.getLogger(__name__)

REVISION_DIR = ".revisions"


def _revision_dir(file_name: str) -> str:
    """Thư mục chứa revision của một bản vẽ, nằm trong workspace của phiên hiện tại."""
    base = os.path.join(get_workspace_dir(), REVISION_DIR, os.path.basename(file_name))
    os.makedirs(base, exist_ok=True)
    return base


def _next_sequence(folder: str) -> int:
    """Số thứ tự tăng dần, không bao giờ lặp lại, cho một thư mục revision.

    Lưu trong một file riêng (`.seq`) thay vì suy từ các file `.dxf` đang có trên đĩa: nếu
    dựa vào đĩa, `_prune_revisions` xóa bớt revision cũ ngay sau mỗi lần chụp sẽ "giải
    phóng" một số thứ tự đã dùng, khiến lần chụp kế tiếp cấp lại đúng số đó — hai revision
    khác nhau trùng tên dù không cùng tồn tại một lúc.
    """
    seq_path = os.path.join(folder, ".seq")
    current = 0
    try:
        with open(seq_path, encoding="utf-8") as f:
            current = int(f.read().strip() or 0)
    except (OSError, ValueError):
        current = 0
    current += 1
    with open(seq_path, "w", encoding="utf-8") as f:
        f.write(str(current))
    return current


def _unique_revision_name(folder: str) -> str:
    """Tên revision không bao giờ trùng, kể cả khi hai lần chụp cách nhau dưới 1 mili-giây.

    Dấu thời gian đơn thuần là KHÔNG đủ: hai snapshot liên tiếp (ví dụ `edit_cad` gọi ngay
    sau `snapshot_cad`) có thể rơi vào cùng một mili-giây, khiến bản sau ghi đè bản trước
    trong khi lịch sử vẫn ghi hai dòng — người dùng thấy một phiên bản không còn khôi phục
    đúng nội dung nữa. Số thứ tự từ `_next_sequence` đảm bảo duy nhất kể cả sau khi revision
    cũ đã bị dọn (xem `_next_sequence`).
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    seq = _next_sequence(folder)
    return f"rev_{stamp}_{seq}.dxf"


def _prune_revisions(file_path: str, keep: int = None) -> int:
    """Xóa bớt revision cũ, chỉ giữ `keep` bản gần nhất. Trả về số bản đã xóa.

    Mỗi revision là một bản sao .dxf ĐẦY ĐỦ, nên một phiên sửa bản vẽ nhiều lần sẽ phình
    dung lượng workspace nếu giữ hết. `keep <= 0` nghĩa là giữ toàn bộ (tắt dọn dẹp).
    """
    limit = settings.max_cad_revisions if keep is None else keep
    if limit <= 0:
        return 0

    entries = _read_history(file_path)
    if len(entries) <= limit:
        return 0

    folder = _revision_dir(file_path)
    obsolete, kept = entries[:-limit], entries[-limit:]
    for entry in obsolete:
        path = os.path.join(folder, entry.get("revision", ""))
        try:
            os.remove(path)
        except OSError:
            # File đã bị xóa tay hoặc chưa từng ghi được — vẫn phải bỏ khỏi lịch sử để
            # `list_cad_revisions` không hiển thị phiên bản không còn khôi phục được.
            logger.debug("Không xóa được revision %s (có thể đã mất).", path)

    # Ghi lại lịch sử chỉ còn các bản còn tồn tại.
    with open(os.path.join(folder, "history.jsonl"), "w", encoding="utf-8") as f:
        for entry in kept:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info("Đã dọn %s revision cũ của %s (giữ lại %s bản).", len(obsolete), file_path, limit)
    return len(obsolete)


def create_snapshot(file_path: str, note: str = "") -> str:
    """Chụp bản vẽ thành một revision mới. Trả về tên revision đã tạo ('' nếu file chưa tồn tại).

    Được các tool sửa bản vẽ gọi TRƯỚC khi ghi đè, nên bản gốc luôn còn đường lùi. Sau mỗi
    lần chụp, các revision quá cũ được dọn theo `settings.max_cad_revisions`.
    """
    safe_path = resolve_safe_path(file_path)
    if not os.path.exists(safe_path):
        return ""
    folder = _revision_dir(file_path)
    rev_name = _unique_revision_name(folder)
    shutil.copy2(safe_path, os.path.join(folder, rev_name))
    meta = {"revision": rev_name, "thoi_gian": datetime.now().isoformat(timespec="seconds"), "ghi_chu": note}
    with open(os.path.join(folder, "history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    logger.info("Created CAD revision %s for %s", rev_name, file_path)
    _prune_revisions(file_path)
    return rev_name


def _read_history(file_path: str):
    folder = _revision_dir(file_path)
    path = os.path.join(folder, "history.jsonl")
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def summarize_drawing(dxf_path: str) -> dict:
    """Thống kê nội dung bản vẽ: số Block theo tên, chiều dài THẬT theo Layer (kể cả cung
    cong và chênh cao độ), danh sách Layer."""
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    blocks, lengths = {}, {}
    entity_count = 0

    for entity in msp:
        entity_count += 1
        if entity.dxftype() == "INSERT":
            blocks[entity.dxf.name] = blocks.get(entity.dxf.name, 0) + 1
            continue
        length = cad_geometry.entity_length(entity)
        if length > 0:
            layer = entity.dxf.layer
            lengths[layer] = lengths.get(layer, 0.0) + length

    return {
        "blocks": blocks,
        "lengths": {k: round(v, 2) for k, v in lengths.items()},
        "layers": sorted(layer.dxf.name for layer in doc.layers),
        "entity_count": entity_count,
    }


@tool
def snapshot_cad(file_path: str, note: str = "") -> str:
    """Lưu một phiên bản (revision) của bản vẽ CAD trước khi chỉnh sửa, để có đường lùi.

    Nên gọi trước mọi thao tác sửa lớn. `note` là ghi chú mô tả lần sửa sắp thực hiện.
    """
    logger.info("Snapshot CAD: %s", file_path)
    try:
        rev = create_snapshot(file_path, note)
        if not rev:
            return f"Không tìm thấy file '{file_path}' để lưu phiên bản."
        total = len(_read_history(file_path))
        limit_note = (f" Hệ thống chỉ giữ {settings.max_cad_revisions} phiên bản gần nhất "
                      f"cho mỗi bản vẽ; các bản cũ hơn đã được dọn để tiết kiệm dung lượng."
                      if settings.max_cad_revisions > 0 else "")
        return (f"Đã lưu phiên bản '{rev}' của bản vẽ '{file_path}'"
                + (f" (ghi chú: {note})" if note else "")
                + f". Tổng số phiên bản hiện có: {total}.{limit_note}")
    except Exception as e:
        return f"Lỗi lưu phiên bản bản vẽ: {e}"


@tool
def list_cad_revisions(file_path: str) -> str:
    """Liệt kê lịch sử các phiên bản đã lưu của một bản vẽ CAD."""
    logger.info("List CAD revisions: %s", file_path)
    try:
        entries = _read_history(file_path)
        if not entries:
            return (f"Bản vẽ '{file_path}' chưa có phiên bản nào được lưu. "
                    f"Dùng `snapshot_cad` trước khi sửa để tạo điểm lùi.")
        lines = [f"LỊCH SỬ PHIÊN BẢN của '{file_path}' ({len(entries)} phiên bản):"]
        for i, entry in enumerate(entries, start=1):
            note = f" — {entry['ghi_chu']}" if entry.get("ghi_chu") else ""
            lines.append(f"  {i}. {entry['revision']} (lưu lúc {entry['thoi_gian']}){note}")
        if settings.max_cad_revisions > 0:
            lines.append(f"(Chỉ giữ {settings.max_cad_revisions} phiên bản gần nhất; bản cũ hơn đã bị dọn.)")
        lines.append("Dùng `diff_cad_revisions` để so sánh, `restore_cad_revision` để quay lại.")
        return "\n".join(lines)
    except Exception as e:
        return f"Lỗi đọc lịch sử phiên bản: {e}"


@tool
def diff_cad_revisions(file_path: str, revision_a: str = "", revision_b: str = "") -> str:
    """So sánh hai phiên bản bản vẽ để biết lần sửa vừa rồi đã thay đổi CHÍNH XÁC những gì.

    Bỏ trống `revision_a` thì lấy phiên bản gần nhất; bỏ trống `revision_b` thì so với
    FILE HIỆN TẠI trên đĩa. So sánh số lượng Block theo tên, tổng chiều dài theo Layer và
    danh sách Layer.
    """
    logger.info("Diff CAD revisions: %s (%s vs %s)", file_path, revision_a, revision_b)
    try:
        entries = _read_history(file_path)
        folder = _revision_dir(file_path)

        if not revision_a:
            if not entries:
                return (f"Bản vẽ '{file_path}' chưa có phiên bản nào để so sánh. "
                        f"Dùng `snapshot_cad` trước khi sửa.")
            revision_a = entries[-1]["revision"]

        path_a = os.path.join(folder, revision_a)
        if not os.path.exists(path_a):
            return f"Không tìm thấy phiên bản '{revision_a}'. Dùng `list_cad_revisions` để xem danh sách."

        if revision_b:
            path_b = os.path.join(folder, revision_b)
            label_b = revision_b
            if not os.path.exists(path_b):
                return f"Không tìm thấy phiên bản '{revision_b}'."
        else:
            path_b = resolve_safe_path(file_path)
            label_b = "file hiện tại"
            if not os.path.exists(path_b):
                return f"Không tìm thấy file hiện tại '{file_path}'."

        a, b = summarize_drawing(path_a), summarize_drawing(path_b)

        report = [f"SO SÁNH BẢN VẼ '{file_path}': {revision_a} -> {label_b}",
                  f"- Tổng số đối tượng: {a['entity_count']} -> {b['entity_count']} "
                  f"({b['entity_count'] - a['entity_count']:+d})", ""]

        block_names = sorted(set(a["blocks"]) | set(b["blocks"]))
        block_changes = [(n, a["blocks"].get(n, 0), b["blocks"].get(n, 0)) for n in block_names
                         if a["blocks"].get(n, 0) != b["blocks"].get(n, 0)]
        if block_changes:
            report.append("THAY ĐỔI SỐ LƯỢNG BLOCK:")
            for name, old, new in block_changes:
                report.append(f"  - {name}: {old} -> {new} ({new - old:+d})")
        else:
            report.append("SỐ LƯỢNG BLOCK: không thay đổi.")

        layer_names = sorted(set(a["lengths"]) | set(b["lengths"]))
        length_changes = [(n, a["lengths"].get(n, 0.0), b["lengths"].get(n, 0.0)) for n in layer_names
                          if abs(a["lengths"].get(n, 0.0) - b["lengths"].get(n, 0.0)) > 0.01]
        report.append("")
        if length_changes:
            report.append("THAY ĐỔI CHIỀU DÀI THEO LAYER:")
            for name, old, new in length_changes:
                report.append(f"  - {name}: {old:.2f} -> {new:.2f} ({new - old:+.2f})")
        else:
            report.append("CHIỀU DÀI THEO LAYER: không thay đổi.")

        added_layers = sorted(set(b["layers"]) - set(a["layers"]))
        removed_layers = sorted(set(a["layers"]) - set(b["layers"]))
        report.append("")
        if added_layers:
            report.append(f"LAYER ĐƯỢC THÊM: {', '.join(added_layers)}")
        if removed_layers:
            report.append(f"LAYER BỊ XÓA: {', '.join(removed_layers)}")
        if not added_layers and not removed_layers:
            report.append("DANH SÁCH LAYER: không thay đổi.")

        if not block_changes and not length_changes and not added_layers and not removed_layers:
            report.append("")
            report.append("=> Hai phiên bản GIỐNG NHAU về nội dung hình học thống kê được.")
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi so sánh phiên bản: {e}"


@tool
def restore_cad_revision(file_path: str, revision: str = "") -> str:
    """Khôi phục bản vẽ CAD về một phiên bản đã lưu trước đó (mặc định: phiên bản gần nhất).

    Trước khi ghi đè, phiên bản HIỆN TẠI cũng được lưu lại thành một revision mới, nên
    thao tác khôi phục cũng có thể hoàn tác.
    """
    logger.info("Restore CAD revision: %s <- %s", file_path, revision)
    try:
        entries = _read_history(file_path)
        if not entries:
            return f"Bản vẽ '{file_path}' chưa có phiên bản nào để khôi phục."
        if not revision:
            revision = entries[-1]["revision"]

        folder = _revision_dir(file_path)
        source = os.path.join(folder, revision)
        if not os.path.exists(source):
            return f"Không tìm thấy phiên bản '{revision}'. Dùng `list_cad_revisions` để xem danh sách."

        target = resolve_safe_path(file_path)

        # Giữ nội dung bản cần khôi phục ra chỗ tạm TRƯỚC khi chụp backup: thao tác chụp
        # kéo theo dọn dẹp theo hạn mức, và nếu `revision` đang là bản cũ nhất còn giữ thì
        # chính nó sẽ bị xóa ngay trước khi kịp copy — khôi phục thất bại đúng lúc người
        # dùng cần nó nhất.
        fd, staged = tempfile.mkstemp(suffix=".dxf", dir=os.path.dirname(target) or None)
        os.close(fd)
        try:
            shutil.copy2(source, staged)
            backup = create_snapshot(file_path, note=f"Tự động lưu trước khi khôi phục về {revision}")
            shutil.copy2(staged, target)
        finally:
            try:
                os.remove(staged)
            except OSError:  # pragma: no cover - file tạm đã bị dọn
                pass

        note = f" (bản trước khi khôi phục đã được lưu thành '{backup}')" if backup else ""
        return f"Đã khôi phục bản vẽ '{file_path}' về phiên bản '{revision}'{note}."
    except Exception as e:
        return f"Lỗi khôi phục phiên bản: {e}"
