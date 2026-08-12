"""Lazy role tool resolution cache (Phase D)."""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_ROLE_CACHE: dict[str, list] = {}


def get_tools_for_role_cached(role: str) -> list:
    key = (role or "").lower().strip()
    with _LOCK:
        hit = _ROLE_CACHE.get(key)
        if hit is not None:
            return list(hit)
    from src.tools import get_tools_for_role
    tools = list(get_tools_for_role(key))
    with _LOCK:
        _ROLE_CACHE[key] = tools
    return list(tools)


def clear_role_tools_cache() -> None:
    with _LOCK:
        _ROLE_CACHE.clear()


def patch_get_tools_for_role() -> None:
    import src.tools as tools_mod
    if getattr(tools_mod, "_lazy_role_cache_patched", False):
        return
    _orig = tools_mod.get_tools_for_role

    def get_tools_for_role(role: str) -> list:
        key = (role or "").lower().strip()
        with _LOCK:
            hit = _ROLE_CACHE.get(key)
            if hit is not None:
                return list(hit)
        tools = list(_orig(role))
        with _LOCK:
            _ROLE_CACHE[key] = tools
        return list(tools)

    tools_mod.get_tools_for_role = get_tools_for_role
    tools_mod._lazy_role_cache_patched = True
    logger.info("get_tools_for_role role-cache enabled")


patch_get_tools_for_role()
