"""Phase A CAD/QS tool binding helper (keeps agents.py changes minimal)."""
from __future__ import annotations

from src.cad_block_replace import replace_blocks_by_mapping
from src.cad_batch_edit import batch_edit_pipes, batch_replace_text, update_title_block
from src.cad_macros import prepare_drawing, full_boq

CAD_EXTRA_TOOLS = [
    replace_blocks_by_mapping,
    batch_edit_pipes,
    batch_replace_text,
    update_title_block,
    prepare_drawing,
]

QS_EXTRA_TOOLS = [
    replace_blocks_by_mapping,
    prepare_drawing,
    full_boq,
    batch_replace_text,
]

PHASE_A_DELIVERABLE = {
    "batch_edit_pipes",
    "batch_replace_text",
    "update_title_block",
    "prepare_drawing",
    "full_boq",
    "export_boq_vietnam",
    "replace_blocks_by_mapping",
}


def append_phase_a_tools(tools: list, role: str) -> list:
    """Append Phase A CAD/QS skills to the role tool list (in-place + return)."""
    role_key = (role or "").lower().strip()
    extra = CAD_EXTRA_TOOLS if role_key == "cad" else (QS_EXTRA_TOOLS if role_key == "qs" else [])
    for t in extra:
        if t not in tools:
            tools.append(t)
    return tools
