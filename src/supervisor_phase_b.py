"""Phase B supervisor wrapper: HIL gate + multi-intent agent_queue drain.

Wraps `src.agents.supervisor_node` without rewriting the large agents.py.
Applied from `agents_phase_b_patch` after import.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from src.hil import clear_human_gate, is_approval_text
from src.parallel_dispatch import next_from_queue, plan_agent_queue
from src.state import RESET

logger = logging.getLogger(__name__)


def _last_human_text(messages) -> str:
    for msg in reversed(messages or []):
        if isinstance(msg, HumanMessage):
            return str(getattr(msg, "content", "") or "")
    return ""


def wrap_supervisor(orig_supervisor):
    """Return a supervisor_node that adds Phase B routing rules."""

    def supervisor_node(state: dict[str, Any]):
        messages = state.get("messages", []) or []
        if not messages:
            return {"next": "FINISH"}

        last_msg = messages[-1]
        done = list(state.get("completed_agents", []) or [])
        queue = list(state.get("agent_queue", []) or [])
        awaiting = bool(state.get("awaiting_human"))

        # --- HIL: paused for human ---
        if awaiting:
            if isinstance(last_msg, HumanMessage):
                text = str(getattr(last_msg, "content", "") or "")
                if is_approval_text(text):
                    logger.info("[PM/HIL] Human approved — clearing gate")
                    cleared = clear_human_gate()
                    # Typical post-CAD path: continue QS if still in queue or default qs
                    nxt = next_from_queue(queue, completed=done) or "qs"
                    return {
                        **cleared,
                        "next": nxt,
                        "completed_agents": [RESET],
                        "retry_count": 0,
                        "agent_queue": queue if queue else ["qs"],
                    }
                # New non-approval request while gate open → treat as fresh turn
                logger.info("[PM/HIL] New request while gate open — reset gate + replan")
            else:
                # Still waiting; do not route workers
                return {"next": "FINISH"}

        # --- New human message: plan multi-intent queue ---
        if isinstance(last_msg, HumanMessage):
            text = str(getattr(last_msg, "content", "") or "")
            # Bare approval without open gate (e.g. button spam) → FINISH
            if is_approval_text(text) and not awaiting and not done:
                return {
                    "next": "FINISH",
                    "awaiting_human": False,
                    "hil_reason": "",
                    "completed_agents": [RESET],
                    "retry_count": 0,
                    "agent_queue": [],
                }

            planned = plan_agent_queue(text, already_done=[])
            reset = {
                "completed_agents": [RESET],
                "retry_count": 0,
                "agent_queue": planned,
                "awaiting_human": False,
                "hil_reason": "",
            }
            # Multi-intent (≥2): drain deterministically without LLM
            if len(planned) >= 2:
                nxt = next_from_queue(planned, completed=[])
                logger.info("[PM] Multi-intent queue %s → first %s", planned, nxt)
                return {"next": nxt, **reset}
            # Single intent: still set queue, prefer deterministic route
            if len(planned) == 1:
                logger.info("[PM] Single-intent queue → %s", planned[0])
                return {"next": planned[0], **reset}
            # No keyword hit → fall through to original LLM supervisor
            result = orig_supervisor(state)
            # Ensure reset fields applied
            if isinstance(result, dict):
                result = {**reset, **result, "agent_queue": planned or list(result.get("agent_queue") or [])}
            return result

        # --- After Reviewer ---
        if getattr(last_msg, "name", "") == "ReviewerAgent":
            content = str(getattr(last_msg, "content", "") or "")
            if "TỪ CHỐI" in content:
                # Keep original reject → rework behaviour
                return orig_supervisor(state)

            # CAD hard gate → HIL pause
            if done and done[-1] == "cad":
                logger.info("[PM/HIL] CAD complete — pause for human approval")
                return {
                    "next": "FINISH",
                    "awaiting_human": True,
                    "hil_reason": "CAD đã chỉnh sửa bản vẽ — mở file kiểm tra rồi bấm DUYỆT để tiếp tục (QS).",
                }

            # Drain remaining multi-intent queue before LLM
            nxt = next_from_queue(queue, completed=done)
            if nxt:
                logger.info("[PM] Drain queue %s (done=%s) → %s", queue, done, nxt)
                return {"next": nxt}

        # Default: original supervisor
        return orig_supervisor(state)

    return supervisor_node
