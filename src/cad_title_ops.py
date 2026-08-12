"""update_title_block — fill title-block attributes."""
from __future__ import annotations

import json
import logging
import os

import ezdxf
from langchain_core.tools import tool

from src.cad_revision import create_snapshot
from src.workspace import resolve_safe_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# update_title_block (MVP)
# ---------------------------------------------------------------------------

@tool
def update_title_block(
    file_path: str,
    attributes_json: str,
    block_name: str = "",
    layout: str = "",
    output_path: str = "",
) -> str:
    """Điền attribute khung tên (title block) trên bản vẽ CAD (.dxf).

    attributes_json: '{"TEN_CT":"Chung cư ABC", "TY_LE":"1:100", "NGAY":"12/08/2026"}'
    - block_name: tên Block khung tên (rỗng = tự tìm INSERT có nhiều ATTDEF nhất trên layout)
    - layout: tên paperspace (rỗng = duyệt mọi layout + modelspace)

    Chỉ cập nhật ATTRIB đã tồn tại trên INSERT — không tạo ATTDEF mới.
    Snapshot trước khi ghi.
    """
    logger.info("update_title_block: %s", file_path)
    try:
        attrs = json.loads(attributes_json)
        if not isinstance(attrs, dict) or not attrs:
            return "attributes_json phải là object JSON không rỗng."

        create_snapshot(file_path, note="Trước update_title_block")
        safe_path = resolve_safe_path(file_path)
        if not os.path.exists(safe_path):
            return f"Lỗi: Không tìm thấy file {file_path}"

        doc = ezdxf.readfile(safe_path)

        # Collect candidate spaces
        spaces = []
        if layout:
            try:
                spaces.append(doc.layouts.get(layout))
            except Exception:
                return f"Không tìm thấy layout '{layout}'."
        else:
            spaces.append(doc.modelspace())
            for name in doc.layout_names_in_taborder():
                if name.upper() == "MODEL":
                    continue
                try:
                    spaces.append(doc.layouts.get(name))
                except Exception:
                    pass

        def _attrib_count(ins) -> int:
            if hasattr(ins, "attribs") and ins.attribs:
                return len(list(ins.attribs))
            return 0

        updated_total = 0
        targets_info = []

        for space in spaces:
            inserts = list(space.query("INSERT"))
            if block_name:
                inserts = [i for i in inserts if i.dxf.name.upper() == block_name.upper()]
            else:
                # Auto-pick: INSERT with most attributes (>= 2)
                inserts = [i for i in inserts if _attrib_count(i) >= 2]
                if inserts:
                    inserts = [max(inserts, key=_attrib_count)]

            for ins in inserts:
                if not hasattr(ins, "attribs") or not ins.attribs:
                    continue
                local = 0
                for attrib in ins.attribs:
                    tag = attrib.dxf.tag
                    # Case-insensitive tag match
                    for k, v in attrs.items():
                        if tag.upper() == str(k).upper():
                            attrib.dxf.text = str(v)
                            local += 1
                            break
                if local:
                    updated_total += local
                    targets_info.append(f"{ins.dxf.name}@{getattr(space, 'name', 'Model')} x{local}")

        target = output_path.strip() or file_path
        out_safe = resolve_safe_path(target)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)
        doc.saveas(out_safe)

        if updated_total == 0:
            return (
                "UPDATE_TITLE_BLOCK: không cập nhật được attribute nào. "
                "Kiểm tra block_name / tag trong attributes_json có khớp ATTDEF trên bản vẽ không. "
                f"File giữ nguyên tại: {target}"
            )
        return (
            "UPDATE TITLE BLOCK THÀNH CÔNG:\n"
            f"- Số attribute đã điền: {updated_total}\n"
            f"- Targets: {'; '.join(targets_info)}\n"
            f"- Đã lưu tại: {target}"
        )
    except json.JSONDecodeError as e:
        return f"Lỗi parse attributes_json: {e}"
    except Exception as e:
        return f"Lỗi update_title_block: {e}"
