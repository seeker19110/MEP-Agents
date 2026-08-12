"""Patch call_mepf_agent to trim message history before each LLM call."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_agents_perf_patch() -> None:
    import src.agents as agents
    from src.perf_tuning import trim_messages_for_llm

    if getattr(agents, "_perf_patched", False):
        return

    _orig = agents.call_mepf_agent

    def call_mepf_agent(state, system_prompt: str, agent_name: str):
        try:
            raw = state.get("messages", []) if isinstance(state, dict) else []
            trimmed = trim_messages_for_llm(raw)
            if len(trimmed) != len(raw):
                logger.debug("[perf] %s messages %s → %s", agent_name, len(raw), len(trimmed))
            state = {**state, "messages": trimmed}
        except Exception as e:
            logger.debug("[perf] trim skipped: %s", e)
        return _orig(state, system_prompt, agent_name)

    agents.call_mepf_agent = call_mepf_agent
    agents._perf_patched = True
    logger.info("agents perf patch applied (message window trim)")


apply_agents_perf_patch()
