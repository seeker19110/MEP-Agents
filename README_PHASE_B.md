# Phase B — Workflow (merged via PR #27)

## Deliverables

1. **QS Auditor checklist** (`qs_audit_checklist`) — deterministic score 0–100
2. **BOQ diff** (`compare_boq`) — add/remove/qty delta between takeoff Excels
3. **HIL** (`src/hil.py` + supervisor wrap) — `awaiting_human` after CAD; resume on DUYỆT
4. **Multi-intent queue** (`parallel_dispatch` + supervisor) — e.g. điện + dự toán → electrical then qs

## Wiring

- `agents_phase_b_patch` binds tools + wraps `supervisor_node`
- `supervisor_phase_b.wrap_supervisor`: queue drain, CAD→HIL gate, approval resume
- ToolNode registers checklist + compare_boq
- State: `awaiting_human`, `hil_reason`, `agent_queue`

## Tests

```bash
uv run pytest tests/test_phase_b.py -q
```
