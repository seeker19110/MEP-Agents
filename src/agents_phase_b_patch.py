"""Phase B post-import patch: bind QS checklist/BOQ diff + HIL-aware supervisor helpers.

Imported from graph.py after agents + phase A patch.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_phase_b_agent_patch() -> None:
    import src.agents as agents
    from src.phase_b_bind import append_phase_b_tools, PHASE_B_DELIVERABLE

    if getattr(agents, "_phase_b_patched", False):
        return

    _orig_gtr = agents.get_tools_for_role

    def get_tools_for_role(role: str):
        tools = list(_orig_gtr(role))
        return append_phase_b_tools(tools, role)

    agents.get_tools_for_role = get_tools_for_role
    agents.DELIVERABLE_TOOLS = set(getattr(agents, "DELIVERABLE_TOOLS", set())) | set(PHASE_B_DELIVERABLE)

    agents._phase_b_patched = True
    logger.info("Phase B agent patch applied (QS checklist + BOQ diff tools)")


apply_phase_b_agent_patch()
