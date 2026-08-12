"""batch_replace_text — find & replace TEXT/MTEXT/ATTRIB."""
from __future__ import annotations

import logging
import os
import re
from typing import Any

import ezdxf
from langchain_core.tools import tool

from src.cad_revision import create_snapshot
from src.workspace import resolve_safe_path

logger = logging.getLogger(__name__)


def _layer_matches(layer: str, filter_layers: list[str] | None) -> bool:
    if not filter_layers:
        return True
    layer_up = layer.upper()
    return any(layer_up == f.upper() or f.upper() in layer_up for f in filter_layers)

# ---------------------------------------------------------------------------
# batch_replace_text
# ---------------------------------------------------------------------------

def _text_of(entity) -> str:
    try:
        from src.cad_geometry import plain_entity_text
        return plain_entity_text(entity) or ""
    except Exception:
        try:
            if entity.dxftype() == "TEXT":
                return entity.dxf.text or ""
            if entity.dxftype() == "MTEXT":
                return entity.plain_text() if hasattr(entity, "plain_text") else (entity.text or "")
        except Exception:
            return ""
    return ""


def _set_text(entity, new_text: str) -> None:
    dxftype = entity.dxftype()
    if dxftype == "TEXT":
        entity.dxf.text = new_text
    elif dxftype == "MTEXT":
        try:
            entity.text = new_text
        except Exception:
            entity.dxf.text = new_text
    elif dxftype == "ATTRIB":
        entity.dxf.text = new_text


def apply_text_replacements(
    doc,
    find: str,
    replace: str,
    *,
    use_regex: bool = False,
    case_sensitive: bool = True,
    layer_filter: list[str] | None = None,
    block_name_filter: list[str] | None = None,
    include_attribs: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    msp = doc.modelspace()
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(find if use_regex else re.escape(find), flags)

    changed = 0
    samples: list[str] = []

    def _maybe_replace(entity, scope: str):
        nonlocal changed
        if layer_filter and not _layer_matches(entity.dxf.layer, layer_filter):
            return
        old = _text_of(entity)
        if not old:
            return
        new, n = pattern.subn(replace, old)
        if n == 0 or new == old:
            return
        if not dry_run:
            _set_text(entity, new)
        changed += 1
        if len(samples) < 15:
            samples.append(f"{scope}: '{old}' → '{new}'")

    for ent in list(msp.query("TEXT")) + list(msp.query("MTEXT")):
        _maybe_replace(ent, "model")

    if include_attribs:
        for ins in list(msp.query("INSERT")):
            bname = ins.dxf.name
            if block_name_filter and not any(
                bname.upper() == b.upper() or b.upper() in bname.upper()
                for b in block_name_filter
            ):
                continue
            if hasattr(ins, "attribs") and ins.attribs:
                for attrib in ins.attribs:
                    _maybe_replace(attrib, f"attrib@{bname}")

    return {
        "changed": changed,
        "samples": samples,
        "dry_run": dry_run,
        "find": find,
        "replace": replace,
    }


@tool
def batch_replace_text(
    file_path: str,
    find: str,
    replace: str,
    output_path: str = "",
    use_regex: bool = False,
    case_sensitive: bool = True,
    layer_filter: str = "",
    block_name_filter: str = "",
    include_attribs: bool = True,
    dry_run: bool = False,
) -> str:
    """Find & replace hàng loạt TEXT/MTEXT/ATTRIB trên bản vẽ CAD (.dxf).

    - find / replace: chuỗi tìm và thay (hỗ trợ regex khi use_regex=true)
    - layer_filter: danh sách layer cách nhau bởi dấu phẩy (rỗng = mọi layer)
    - block_name_filter: chỉ đụng ATTRIB của các Block tên khớp (rỗng = mọi Block)
    - include_attribs: có thay attribute của INSERT hay không (mặc định có)
    - dry_run: chỉ báo cáo, không ghi file

    Ví dụ: đổi Ø110 → DN100, hoặc mã hiệu FCU-01 → FCU-A-01.
    Luôn snapshot trước khi ghi (trừ dry_run).
    """
    logger.info("batch_replace_text: %s find=%r", file_path, find)
    try:
        if not find:
            return "Tham số 'find' rỗng — không có gì để tìm."

        layers = [x.strip() for x in layer_filter.split(",") if x.strip()] or None
        blocks = [x.strip() for x in block_name_filter.split(",") if x.strip()] or None

        if not dry_run:
            create_snapshot(file_path, note=f"Trước batch_replace_text find={find!r}")

        safe_path = resolve_safe_path(file_path)
        if not os.path.exists(safe_path):
            return f"Lỗi: Không tìm thấy file {file_path}"

        doc = ezdxf.readfile(safe_path)
        stats = apply_text_replacements(
            doc,
            find,
            replace,
            use_regex=use_regex,
            case_sensitive=case_sensitive,
            layer_filter=layers,
            block_name_filter=blocks,
            include_attribs=include_attribs,
            dry_run=dry_run,
        )

        target = output_path.strip() or file_path
        if not dry_run:
            out_safe = resolve_safe_path(target)
            parent = os.path.dirname(out_safe)
            if parent:
                os.makedirs(parent, exist_ok=True)
            doc.saveas(out_safe)

        mode = "DRY-RUN (chưa ghi file)" if dry_run else "THÀNH CÔNG"
        lines = [
            f"BATCH REPLACE TEXT {mode}:",
            f"- Tìm: {find!r} → Thay: {replace!r} (regex={use_regex}, case_sensitive={case_sensitive})",
            f"- Số chỗ đã {'khớp' if dry_run else 'thay'}: {stats['changed']}",
        ]
        for s in stats["samples"]:
            lines.append(f"  · {s}")
        if stats["changed"] > len(stats["samples"]):
            lines.append(f"  · ... và {stats['changed'] - len(stats['samples'])} chỗ khác")
        if not dry_run:
            lines.append(f"- Đã lưu tại: {target}")
        return "\n".join(lines)
    except Exception as e:
        return f"Lỗi batch_replace_text: {e}"
