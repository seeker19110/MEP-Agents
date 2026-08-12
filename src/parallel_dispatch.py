"""Parallel M/E/P/F fan-out helpers for LangGraph.

Supervisor may request several discipline agents in one hop. We expand that
into sequential-but-batched routing first (safe with existing checkpointer),
and expose `plan_parallel_agents` for future Send()-based fan-out.

Phase B MVP: parse multi-intent from supervisor context and return an ordered
queue stored in state.context['agent_queue']. Supervisor drains the queue.
"""
from __future__ import annotations

import re
from typing import Sequence

WORKER_AGENTS = (
    "mechanical",
    "electrical",
    "plumbing",
    "firefighting",
    "qs",
    "cad",
    "bim",
)

# Keyword → agent hints for multi-intent detection (Vietnamese + English)
_INTENT_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(hvac|điều hòa|dieu hoa|thông gió|thong gio|ống gió|ong gio)\b", re.I), "mechanical"),
    (re.compile(r"\b(điện|dien|chiếu sáng|chieu sang|cáp|cap|tủ điện|tu dien)\b", re.I), "electrical"),
    (re.compile(r"\b(nước|nuoc|cấp thoát|cap thoat|plumbing|bơm nước|bom nuoc)\b", re.I), "plumbing"),
    (re.compile(r"\b(pccc|chữa cháy|chua chay|sprinkler|fire\s*fight)\b", re.I), "firefighting"),
    (re.compile(r"\b(bóc khối|boc khoi|dự toán|du toan|boq|khối lượng|khoi luong)\b", re.I), "qs"),
    (re.compile(r"\b(cad|bản vẽ|ban ve|dxf|dwg)\b", re.I), "cad"),
    (re.compile(r"\b(bim|clash|ifc|xung đột|xung dot)\b", re.I), "bim"),
]


def detect_parallel_agents(user_text: str, already_done: Sequence[str] | None = None) -> list[str]:
    """Detect which discipline agents a single user request implies.

    Returns ordered unique list, excluding agents already completed this turn.
    """
    done = set(already_done or [])
    found: list[str] = []
    for pat, agent in _INTENT_MAP:
        if agent in done or agent in found:
            continue
        if pat.search(user_text or ""):
            found.append(agent)
    return found


def plan_agent_queue(
    user_text: str,
    *,
    already_done: Sequence[str] | None = None,
    prefer_single: str | None = None,
) -> list[str]:
    """Build queue: multi-intent → list; else single prefer_single if provided."""
    multi = detect_parallel_agents(user_text, already_done=already_done)
    if len(multi) >= 2:
        return multi
    if prefer_single and prefer_single in WORKER_AGENTS:
        if prefer_single not in set(already_done or []):
            return [prefer_single]
    return multi[:1]


def next_from_queue(queue: Sequence[str], completed: Sequence[str] | None = None) -> str | None:
    """Pop-logical next agent still not completed."""
    done = set(completed or [])
    for a in queue:
        if a not in done and a in WORKER_AGENTS:
            return a
    return None
