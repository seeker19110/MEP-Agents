"""Phase A post-import patch for agents (avoids rewriting large agents.py).

Import this module from graph.py AFTER `src.agents` is imported so that:
- get_tools_for_role includes Phase A CAD/QS skills (also under Anthropic tool-search)
- DELIVERABLE_TOOLS recognizes Phase A macros as real deliverables
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_phase_a_agent_patch() -> None:
    import src.agents as agents
    from src.cad_phase_a_bind import append_phase_a_tools, PHASE_A_DELIVERABLE

    if getattr(agents, "_phase_a_patched", False):
        return

    # 1) Patch get_tools_for_role in agents module globals so build_tools_for_llm
    #    picks up Phase A tools BEFORE any Anthropic defer_loading conversion.
    _orig_gtr = agents.get_tools_for_role

    def get_tools_for_role(role: str):
        return append_phase_a_tools(list(_orig_gtr(role)), role)

    agents.get_tools_for_role = get_tools_for_role

    # 2) Expand deliverable tool set used by Reviewer structural checks
    agents.DELIVERABLE_TOOLS = set(agents.DELIVERABLE_TOOLS) | set(PHASE_A_DELIVERABLE)

    agents._phase_a_patched = True
    logger.info(
        "Phase A agent patch applied (CAD/QS tools via get_tools_for_role + DELIVERABLE_TOOLS)"
    )


apply_phase_a_agent_patch()
