# Phase A — CAD Skills (merged)

Merged via PR #26 (`ab5a8d9`) + binding commit on main.

## Skills

1. `batch_edit_pipes` — join_gap / change_layer / change_linetype / offset
2. `batch_replace_text` — find & replace TEXT/MTEXT/ATTRIB
3. `update_title_block` — fill title block attributes
4. `prepare_drawing` — audit → optimize → standardize (+ optional replace_blocks)
5. `full_boq` — prepare → takeoff → cost → export BOQ VN

## Wiring

- **ToolNode** (`src/graph.py`): registers all Phase A tools for execution
- **LLM bind** (`src/agents_phase_a_patch.py`): patches `get_tools_for_role` so CAD/QS agents see the skills; expands `DELIVERABLE_TOOLS` for Reviewer checks
- **Helper** (`src/cad_phase_a_bind.py`): role → tool lists

Preferred CAD skill order: `replace_blocks_by_mapping` → `batch_edit_pipes` → `batch_replace_text` → title block/layout.
