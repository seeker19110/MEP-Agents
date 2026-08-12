"""Graph helpers for LangGraph Send fan-out (Phase D)."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def route_supervisor(state: dict) -> Any:
    workers = list(state.get("parallel_workers") or [])
    if len(workers) >= 2:
        try:
            from src.supervisor_parallel import try_build_sends
            sends = try_build_sends(state, workers)
            if sends:
                logger.info("Graph Send parallel → %s", workers)
                return sends
        except Exception as e:
            logger.warning("Send parallel failed (%s) — sequential", e)
    return state.get("next") or "FINISH"
