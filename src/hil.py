"""Human-in-the-loop (HIL) helpers — pause graph for human approval.

Phase B: formalize the existing soft CAD-approval gate into explicit state
flags that API / Streamlit can read and resume.

Flow:
1. A node sets `awaiting_human=True` + `hil_reason` (+ optional payload in context)
2. Supervisor / gate routes to END while flag is set (pause)
3. Client sends approval message (e.g. "DUYỆT") → `clear_hil()` → graph continues

Also exposes `request_cad_approval` helper used after CAD edits.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Phrases that clear the HIL gate (matched case-insensitively, substring OK)
APPROVAL_PHRASES = (
    "duyệt",
    "duyet",
    "approve",
    "approved",
    "ok tiếp",
    "ok tiep",
    "tiếp tục",
    "tiep tuc",
    "tiến hành",
    "tien hanh",
    "đồng ý",
    "dong y",
)


def is_approval_text(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return any(p in t for p in APPROVAL_PHRASES)


def request_human_gate(
    reason: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return AgentState partial update that pauses the graph for human input."""
    ctx: dict[str, Any] = {}
    if payload:
        ctx["hil_payload"] = payload
    return {
        "awaiting_human": True,
        "hil_reason": reason,
        "context": ctx,
        "next": "FINISH",
    }


def clear_human_gate() -> dict[str, Any]:
    """Return AgentState partial update that resumes after approval."""
    return {
        "awaiting_human": False,
        "hil_reason": "",
        "context": {"hil_payload": None},
    }


def hil_status(state: dict[str, Any]) -> dict[str, Any]:
    """Snapshot for API/UI."""
    return {
        "awaiting_human": bool(state.get("awaiting_human")),
        "hil_reason": state.get("hil_reason") or "",
        "hil_payload": (state.get("context") or {}).get("hil_payload"),
    }
