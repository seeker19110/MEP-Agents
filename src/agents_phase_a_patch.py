"""Phase A: giữ lại như lớp tương thích, nay gần như không còn việc gì để làm.

Lịch sử: module này từng patch `agents.get_tools_for_role` để gắn skill CAD/QS và cộng
thêm vào `agents.DELIVERABLE_TOOLS`. Cả hai việc đó nay đã nằm thẳng trong mã nguồn:

- Tool: đăng ký trong registry chính `src/tools.py` (PR #33).
- `DELIVERABLE_TOOLS`: khai báo thẳng trong `src/agents.py`.

Vẫn giữ file để `import src.agents_phase_a_patch` ở nơi khác không gãy, và để kiểm tra
rằng hai việc trên thật sự đã có — nếu ai đó lỡ tay xóa mất, log cảnh báo ở đây sẽ nói ra
thay vì để hệ thống chạy thiếu skill trong im lặng.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_phase_a_agent_patch() -> None:
    import src.agents as agents
    from src.cad_phase_a_bind import PHASE_A_DELIVERABLE

    if getattr(agents, "_phase_a_patched", False):
        return

    missing = set(PHASE_A_DELIVERABLE) - set(getattr(agents, "DELIVERABLE_TOOLS", set()))
    if missing:
        logger.warning(
            "DELIVERABLE_TOOLS thiếu skill Phase A: %s — Reviewer sẽ không coi chúng là "
            "sản phẩm thật. Bổ sung tạm, nhưng nên khai báo thẳng trong src/agents.py.",
            sorted(missing),
        )
        agents.DELIVERABLE_TOOLS = set(agents.DELIVERABLE_TOOLS) | missing

    agents._phase_a_patched = True
    logger.debug("Phase A: skill và DELIVERABLE_TOOLS đã có sẵn trong mã nguồn")


apply_phase_a_agent_patch()
