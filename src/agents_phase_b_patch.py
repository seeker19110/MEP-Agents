"""Phase B post-import patch: QS tools + HIL/queue-aware supervisor.

Imported from graph.py after agents + phase A patch.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_phase_b_agent_patch() -> None:
    import src.agents as agents
    from src.phase_b_bind import append_phase_b_tools, PHASE_B_DELIVERABLE
    from src.supervisor_phase_b import wrap_supervisor

    if getattr(agents, "_phase_b_patched", False):
        return

    # 1) Tool binding for QS / BIM
    _orig_gtr = agents.get_tools_for_role

    def get_tools_for_role(role: str):
        tools = list(_orig_gtr(role))
        return append_phase_b_tools(tools, role)

    agents.get_tools_for_role = get_tools_for_role
    agents.DELIVERABLE_TOOLS = set(getattr(agents, "DELIVERABLE_TOOLS", set())) | set(PHASE_B_DELIVERABLE)

    # 2) Wrap supervisor for HIL + agent_queue drain
    agents.supervisor_node = wrap_supervisor(agents.supervisor_node)

    agents._phase_b_patched = True
    logger.info("Phase B agent patch applied (QS tools + supervisor HIL/queue)")


apply_phase_b_agent_patch()
