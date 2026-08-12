"""Apply Phase A agents.py binding. Run from repo root: python scripts/apply_phase_a_agents.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] if (Path(__file__).parent.name == "scripts") else Path.cwd()
agents = ROOT / "src" / "agents.py"
text = agents.read_text(encoding="utf-8")

replacements = [
    (
        "from src.cad_block_replace import replace_blocks_by_mapping",
        "from src.cad_phase_a_bind import append_phase_a_tools, PHASE_A_DELIVERABLE",
    ),
    (
        '''    tools = list(get_tools_for_role(role))
    if (role or "").lower().strip() in ("cad", "qs") and replace_blocks_by_mapping not in tools:
        tools.append(replace_blocks_by_mapping)''',
        '''    tools = list(get_tools_for_role(role))
    tools = append_phase_a_tools(tools, role)''',
    ),
    (
        'DELIVERABLE_TOOLS = {"auto_quantity_takeoff", "write_excel", "calc_boq_cost", "write_word", "write_cad", "edit_cad", "replace_blocks_by_mapping"}',
        'DELIVERABLE_TOOLS = {"auto_quantity_takeoff", "write_excel", "calc_boq_cost", "write_word", "write_cad", "edit_cad"} | PHASE_A_DELIVERABLE',
    ),
]

for old, new in replacements:
    if old not in text:
        if new in text or "append_phase_a_tools" in text:
            print("already applied:", old[:60])
            continue
        raise SystemExit(f"pattern not found: {old[:80]!r}")
    text = text.replace(old, new, 1)
    print("applied:", old[:60])

# Prompt enrichments (idempotent)
cad_line = "gọi `replace_blocks_by_mapping(file_path=..., mapping_json=...)`."
cad_extra = """gọi `replace_blocks_by_mapping(file_path=..., mapping_json=...)`.
    - SỬA ỐNG HÀNG LOẠT: `batch_edit_pipes(file_path=..., operations_json=...)` (join_gap/change_layer/change_linetype/offset).
    - FIND & REPLACE TEXT: `batch_replace_text(file_path=..., find=..., replace=...)` (regex, dry_run).
    - ĐIỀN KHUNG TÊN: `update_title_block(file_path=..., attributes_json=...)`.
    - CHUẨN BỊ BẢN VẼ: `prepare_drawing(file_path=...)` (audit→optimize→standardize)."""
if "batch_edit_pipes(file_path=" not in text and cad_line in text:
    text = text.replace(cad_line, cad_extra)
    print("CAD prompt enriched")

qs_old = "NGAY LẬP TỨC gọi tool `auto_quantity_takeoff(file_path=...)` cho bản vẽ được giao."
qs_new = "Ưu tiên `full_boq(file_path=...)` khi cần takeoff+dự toán; hoặc `prepare_drawing` rồi `auto_quantity_takeoff(file_path=...)` cho bản vẽ được giao."
if qs_old in text:
    text = text.replace(qs_old, qs_new, 1)
    print("QS prompt updated")

agents.write_text(text, encoding="utf-8")
print("Wrote", agents)
