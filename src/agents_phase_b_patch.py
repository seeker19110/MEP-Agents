"""Phase B: đăng ký luật điều phối (chốt chặn HIL + hàng đợi đa ý định).

Trước đây module này gán đè `agents.supervisor_node` bằng bản đã bọc. Nay đăng ký một
middleware vào `src/supervisor_pipeline.py` — hàm `supervisor_node` giữ nguyên danh tính,
thứ tự các lớp nằm ở mức ưu tiên chứ không phụ thuộc thứ tự import. Xem TECH_DEBT.md mục 10.

Tool của Phase B (`qs_audit_checklist`, `compare_boq`) đã nằm sẵn trong registry chính
`src/tools.py` từ PR #33, không cần gắn thêm ở đây nữa.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Ưu tiên của lớp Phase B. Thấp hơn Phase D nên nằm TRONG — giữ đúng thứ tự cũ, khi
#: Phase D bọc sau nên nằm ngoài cùng.
PHASE_B_PRIORITY = 10


def apply_phase_b_agent_patch() -> None:
    import src.agents as agents
    from src.phase_b_bind import PHASE_B_DELIVERABLE
    from src.supervisor_phase_b import wrap_supervisor
    from src.supervisor_pipeline import register_middleware

    if getattr(agents, "_phase_b_patched", False):
        return

    agents.DELIVERABLE_TOOLS = set(getattr(agents, "DELIVERABLE_TOOLS", set())) | set(PHASE_B_DELIVERABLE)

    def phase_b_middleware(state, call_next):
        # `wrap_supervisor` vốn nhận hàm gốc rồi trả về hàm mới — dạng đó khớp thẳng với
        # middleware, chỉ cần truyền `call_next` vào chỗ của hàm gốc.
        return wrap_supervisor(call_next)(state)

    register_middleware("phase_b_hil_queue", phase_b_middleware, priority=PHASE_B_PRIORITY)

    agents._phase_b_patched = True
    logger.info("Phase B: đã đăng ký middleware điều phối (HIL + hàng đợi)")


apply_phase_b_agent_patch()
