# Phase B — Workflow (branch feat/phase-b-workflow)

## Deliverables

1. **QS Auditor checklist** (`src/qs_auditor_tools.py` → `qs_audit_checklist`)
   - Cột bắt buộc, số HM, KL≤0, hao hụt, scale, thiếu đơn giá
2. **BOQ diff** (`src/boq_diff.py` → `compare_boq`)
   - Thêm / xoá / đổi khối lượng giữa 2 Excel takeoff
3. **HIL helpers** (`src/hil.py`)
   - `request_human_gate` / `clear_human_gate` / `is_approval_text`
   - State: `awaiting_human`, `hil_reason`
4. **Parallel intent queue** (`src/parallel_dispatch.py`)
   - `detect_parallel_agents` / `plan_agent_queue` / `next_from_queue`
   - State: `agent_queue`

## Wiring

- ToolNode + `agents_phase_b_patch` bind checklist/diff to QS/BIM roles
- AgentState extended for HIL + queue

## Tests

```bash
uv run pytest tests/test_phase_b.py -q
```

## Next (still on this phase)

- Wire supervisor to drain `agent_queue` automatically
- Streamlit/API surface for `hil_status` + resume on approval text
- Optional LangGraph `Send()` true parallel fan-out
