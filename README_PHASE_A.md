# Phase A — CAD Skills (in progress on branch feat/phase-a-cad-skills)

This branch implements the first phase of the upgrade roadmap:

1. `batch_edit_pipes` — join_gap / change_layer / change_linetype / offset
2. `batch_replace_text` — find & replace TEXT/MTEXT/ATTRIB
3. `update_title_block` — fill title block attributes
4. `prepare_drawing` macro — audit → optimize → standardize
5. `full_boq` macro — prepare → takeoff → cost → export

Status: core files are being pushed in subsequent commits on this branch.
Preferred CAD skill order remains: replace_blocks_by_mapping → batch_edit_pipes → batch_replace_text → title block/layout.
