"""Parallel fan-out detection for independent MEP disciplines (Phase D)."""
from __future__ import annotations

import logging
import re
from typing import Sequence

logger = logging.getLogger(__name__)

_PARALLEL_SAFE = frozenset({"mechanical", "electrical", "plumbing", "firefighting"})

_HINTS = {
    "mechanical": re.compile(
        r"\b(hvac|điều hòa|dieu hoa|thông gió|thong gio|chiller|ahu|vrv|ống gió|ong gio|cooling|duct)\b", re.I),
    "electrical": re.compile(
        r"\b(điện|dien|chiếu sáng|chieu sang|cáp|cap|tủ điện|tu dien|breaker|voltage|kVA|kW)\b", re.I),
    "plumbing": re.compile(
        r"\b(cấp nước|cap nuoc|thoát nước|thoat nuoc|plumbing|bơm nước|bom nuoc|ống nước|ong nuoc)\b", re.I),
    "firefighting": re.compile(
        r"\b(pccc|chữa cháy|chua chay|sprinkler|fire\s*fight|bơm chữa cháy)\b", re.I),
}

_BLOCK_PARALLEL = re.compile(
    r"\b(bóc khối|boc khoi|boq|dự toán|du toan|cad|bản vẽ|ban ve|dxf|dwg|sửa bản vẽ|xref)\b", re.I)


def detect_parallel_workers(text: str, done: Sequence[str] | None = None) -> list[str]:
    if not text or _BLOCK_PARALLEL.search(text):
        return []
    done_set = {d.lower() for d in (done or [])}
    found = []
    for role, pat in _HINTS.items():
        if role in done_set:
            continue
        if pat.search(text):
            found.append(role)
    return found if len(found) >= 2 else []


def try_build_sends(state: dict, workers: list[str]):
    if len(workers) < 2:
        return None
    try:
        from langgraph.types import Send
    except ImportError:
        try:
            from langgraph.constants import Send
        except ImportError:
            logger.warning("LangGraph Send not available — sequential fallback")
            return None
    safe = [w for w in workers if w in _PARALLEL_SAFE]
    if len(safe) < 2:
        return None
    return [Send(w, state) for w in safe]
