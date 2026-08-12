"""Thay thế Block hàng loạt theo bảng mapping (deterministic, không cần LLM).

Khác với `standardize_cad_drawing` (chỉ ĐỔI TÊN Block/Layer, không đụng hình học):
tool này THAY hẳn định nghĩa Block — dùng khi khách đưa bản vẽ với ký hiệu cũ/lạ
và muốn đồng bộ về thư viện chuẩn `data/blocks/mepf_library.dxf`.

An toàn:
- Luôn `create_snapshot` trước khi ghi.
- Chỉ thay INSERT trên modelspace (không đụng nested block bên trong định nghĩa
  Block khác — nested cần xử lý riêng vì rủi ro làm hỏng cụm thiết bị).
- Nếu Block đích không có trong bản vẽ lẫn thư viện → bỏ qua mapping đó và báo cáo
  rõ, không đoán bừa.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import ezdxf
from ezdxf.addons import importer
from langchain_core.tools import tool

from src.cad_revision import create_snapshot
from src.workspace import get_project_root, resolve_safe_path

logger = logging.getLogger(__name__)


def _parse_mapping(mapping_json: str) -> list[dict[str, Any]]:
    """Nhận 2 dạng input phổ biến từ agent:

    1. Dict đơn giản: {"OLD_NAME": "NEW_NAME", ...}
    2. List chi tiết:
       [{"old_block": "...", "new_block": "...", "keep_scale": true,
         "keep_rotation": true, "attribute_map": {"TAG_CU": "MA_HIEU"},
         "set_attributes": {"MA_HIEU": "E-SOCKET"}}, ...]
    """
    data = json.loads(mapping_json)
    rules: list[dict[str, Any]] = []

    if isinstance(data, dict):
        for old, new in data.items():
            if not isinstance(old, str) or not isinstance(new, str):
                raise ValueError(
                    "Mapping dict phải là {\"old_block\": \"new_block\"} với cả hai là chuỗi."
                )
            rules.append(
                {
                    "old_block": old.strip(),
                    "new_block": new.strip(),
                    "keep_scale": True,
                    "keep_rotation": True,
                    "attribute_map": {},
                    "set_attributes": {},
                }
            )
        return rules

    if isinstance(data, list):
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(f"Phần tử mapping[{i}] phải là object.")
            old = (item.get("old_block") or item.get("from") or "").strip()
            new = (item.get("new_block") or item.get("to") or "").strip()
            if not old or not new:
                raise ValueError(
                    f"Phần tử mapping[{i}] thiếu old_block/new_block (hoặc from/to)."
                )
            rules.append(
                {
                    "old_block": old,
                    "new_block": new,
                    "keep_scale": bool(item.get("keep_scale", True)),
                    "keep_rotation": bool(item.get("keep_rotation", True)),
                    "attribute_map": dict(item.get("attribute_map") or {}),
                    "set_attributes": dict(item.get("set_attributes") or {}),
                    "target_layer": (item.get("target_layer") or "").strip() or None,
                }
            )
        return rules

    raise ValueError("mapping_json phải là object {...} hoặc mảng [{...}, ...].")


def _ensure_block_definition(doc, block_name: str, lib_doc) -> bool:
    """Đảm bảo `block_name` có trong `doc`. Import từ thư viện nếu thiếu.
    Trả về True nếu định nghĩa đã sẵn sàng."""
    if block_name in doc.blocks:
        return True
    if lib_doc is not None and block_name in lib_doc.blocks:
        imp = importer.Importer(lib_doc, doc)
        imp.import_block(block_name)
        imp.finalize()
        return block_name in doc.blocks
    return False


def _read_insert_attribs(entity) -> dict[str, str]:
    result = {}
    if not hasattr(entity, "attribs") or not entity.attribs:
        return result
    for attrib in entity.attribs:
        if hasattr(attrib, "dxf") and hasattr(attrib.dxf, "tag"):
            result[attrib.dxf.tag] = getattr(attrib.dxf, "text", "") or ""
    return result


def _build_new_attrib_values(
    old_attribs: dict[str, str],
    attribute_map: dict[str, str],
    set_attributes: dict[str, str],
) -> dict[str, str]:
    """Ghép attribute: giữ nguyên tag cũ không map, áp attribute_map, rồi set_attributes
    (set_attributes thắng nếu trùng tag)."""
    merged = dict(old_attribs)
    for old_tag, new_tag in attribute_map.items():
        if old_tag in old_attribs:
            merged[new_tag] = old_attribs[old_tag]
            if new_tag != old_tag:
                merged.pop(old_tag, None)
    merged.update({k: str(v) for k, v in set_attributes.items()})
    return merged


def replace_blocks_in_document(
    doc,
    rules: list[dict[str, Any]],
    lib_doc=None,
) -> dict[str, Any]:
    """Thực thi thay Block trên một document ezdxf đã mở. Trả về thống kê."""
    msp = doc.modelspace()
    stats = {
        "replaced": {},  # old -> {"new": ..., "count": n}
        "skipped_missing_target": [],
        "skipped_missing_source": [],
        "imported_from_library": [],
        "total_replaced": 0,
    }

    # Gom INSERT theo tên block một lần để tránh quét lặp khi nhiều rule.
    inserts_by_name: dict[str, list] = {}
    for entity in list(msp.query("INSERT")):
        name = entity.dxf.name
        if name.startswith("*"):
            continue
        inserts_by_name.setdefault(name, []).append(entity)

    for rule in rules:
        old_name = rule["old_block"]
        new_name = rule["new_block"]
        keep_scale = rule.get("keep_scale", True)
        keep_rotation = rule.get("keep_rotation", True)
        attribute_map = rule.get("attribute_map") or {}
        set_attributes = rule.get("set_attributes") or {}
        target_layer = rule.get("target_layer")

        sources = inserts_by_name.get(old_name, [])
        if not sources:
            stats["skipped_missing_source"].append(old_name)
            continue

        if old_name == new_name:
            # Chỉ cập nhật attribute / layer, không thay định nghĩa.
            pass
        else:
            existed = new_name in doc.blocks
            if not _ensure_block_definition(doc, new_name, lib_doc):
                stats["skipped_missing_target"].append(
                    f"{old_name} -> {new_name} (không có trong bản vẽ lẫn thư viện)"
                )
                continue
            if not existed and new_name in doc.blocks:
                stats["imported_from_library"].append(new_name)

        count = 0
        for entity in sources:
            insert = entity.dxf.insert
            layer = target_layer or entity.dxf.layer
            if layer not in doc.layers:
                doc.layers.add(name=layer)

            xscale = entity.dxf.xscale if keep_scale else 1.0
            yscale = entity.dxf.yscale if keep_scale else 1.0
            zscale = getattr(entity.dxf, "zscale", 1.0) if keep_scale else 1.0
            rotation = entity.dxf.rotation if keep_rotation else 0.0

            old_attribs = _read_insert_attribs(entity)
            new_attribs = _build_new_attrib_values(
                old_attribs, attribute_map, set_attributes
            )

            new_ref = msp.add_blockref(
                new_name,
                (insert.x, insert.y, getattr(insert, "z", 0.0)),
                dxfattribs={
                    "layer": layer,
                    "xscale": xscale,
                    "yscale": yscale,
                    "zscale": zscale,
                    "rotation": rotation,
                },
            )

            # Gắn attribute nếu Block đích có ATTDEF tương ứng.
            if new_attribs:
                try:
                    new_ref.add_auto_attribs(new_attribs)
                except Exception:
                    # Một số Block không có ATTDEF — bỏ qua, không làm hỏng thay thế.
                    logger.debug(
                        "Không gắn được attribute cho Block '%s' (có thể thiếu ATTDEF).",
                        new_name,
                    )

            msp.delete_entity(entity)
            count += 1

        if count:
            stats["replaced"][old_name] = {"new": new_name, "count": count}
            stats["total_replaced"] += count
            # Cập nhật cache: old hết, new tăng (không cần vì đã xử lý xong rule).
            inserts_by_name.pop(old_name, None)

    return stats


def _format_report(stats: dict[str, Any], file_path: str, target_path: str) -> str:
    lines = [
        "THAY THẾ BLOCK THEO MAPPING THÀNH CÔNG (deterministic, không cần LLM):",
        f"- Tổng số instance đã thay: {stats['total_replaced']}",
    ]
    if stats["replaced"]:
        detail = "; ".join(
            f"{old} -> {info['new']} x{info['count']}"
            for old, info in sorted(stats["replaced"].items())
        )
        lines.append(f"- Chi tiết: {detail}")
    else:
        lines.append("- Chi tiết: (không có instance nào được thay)")

    if stats["imported_from_library"]:
        lines.append(
            "- Đã import từ thư viện mepf_library.dxf: "
            + ", ".join(sorted(set(stats["imported_from_library"])))
        )
    if stats["skipped_missing_source"]:
        lines.append(
            "- Không tìm thấy INSERT nguồn (bỏ qua): "
            + ", ".join(sorted(set(stats["skipped_missing_source"])))
        )
    if stats["skipped_missing_target"]:
        lines.append(
            "- CẦN REVIEW — Block đích thiếu (không thay): "
            + "; ".join(stats["skipped_missing_target"])
        )
    lines.append(f"- File nguồn: {file_path}")
    lines.append(f"- Đã lưu tại: {target_path}")
    lines.append(
        "- Lưu ý: chỉ thay INSERT trên modelspace; Block lồng nhau bên trong định nghĩa "
        "Block khác không bị đụng. Dùng `optimize_cad_drawing` sau nếu muốn purge định nghĩa cũ."
    )
    return "\n".join(lines)


@tool
def replace_blocks_by_mapping(
    file_path: str,
    mapping_json: str,
    output_path: str = "",
    import_from_library: bool = True,
) -> str:
    """Thay thế hàng loạt Block trong bản vẽ CAD (.dxf) theo bảng mapping.

    Dùng khi cần ĐỔI HẲN ký hiệu/thiết bị cũ sang Block chuẩn (khác với
    `standardize_cad_drawing` chỉ đổi TÊN, không thay hình học).

    mapping_json hỗ trợ 2 dạng:
    1) Đơn giản: '{"O_CAM_CU": "SOCKET", "DEN_CU": "LIGHT_DOWNLIGHT"}'
    2) Chi tiết: '[{"old_block": "O_CAM_CU", "new_block": "SOCKET",
       "keep_scale": true, "keep_rotation": true,
       "attribute_map": {"TAG_CU": "MA_HIEU"},
       "set_attributes": {"MA_HIEU": "E-SOCKET"},
       "target_layer": "E-POWER"}]'

    - Giữ nguyên vị trí chèn; scale/rotation giữ theo cờ (mặc định giữ).
    - Tự import Block đích từ data/blocks/mepf_library.dxf nếu bản vẽ chưa có
      (khi import_from_library=true).
    - Luôn snapshot revision trước khi ghi. Chỉ xử lý INSERT trên modelspace.
    """
    logger.info("Replace blocks by mapping: %s", file_path)
    try:
        rules = _parse_mapping(mapping_json)
        if not rules:
            return "mapping_json rỗng — không có quy tắc thay thế nào để áp dụng."

        create_snapshot(
            file_path,
            note=f"Trước khi replace_blocks_by_mapping ({len(rules)} quy tắc)",
        )
        safe_path = resolve_safe_path(file_path)
        if not os.path.exists(safe_path):
            return f"Lỗi: Không tìm thấy file {file_path}"

        doc = ezdxf.readfile(safe_path)

        lib_doc = None
        if import_from_library:
            library_path = os.path.join(
                get_project_root(), "data", "blocks", "mepf_library.dxf"
            )
            if os.path.exists(library_path):
                lib_doc = ezdxf.readfile(library_path)

        stats = replace_blocks_in_document(doc, rules, lib_doc=lib_doc)

        target_path = output_path.strip() or file_path
        out_safe = resolve_safe_path(target_path)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)
        doc.saveas(out_safe)

        return _format_report(stats, file_path, target_path)
    except json.JSONDecodeError as e:
        return f"Lỗi parse mapping_json (JSON không hợp lệ): {e}"
    except ValueError as e:
        return f"Lỗi mapping_json: {e}"
    except Exception as e:
        return f"Lỗi thay thế Block theo mapping: {e}"
