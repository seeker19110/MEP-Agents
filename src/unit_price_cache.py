"""In-process LRU for unit prices when Redis is down (QS path)."""
from __future__ import annotations

import os
import time
from typing import Any

_MEM: dict[str, tuple[float, Any]] = {}
_TTL = float(os.environ.get("UNIT_PRICE_MEM_TTL", "300"))


def mem_get(key: str):
    item = _MEM.get(key)
    if not item:
        return None
    ts, val = item
    if time.time() - ts > _TTL:
        _MEM.pop(key, None)
        return None
    return val


def mem_set(key: str, value: Any) -> None:
    _MEM[key] = (time.time(), value)
    if len(_MEM) > 32:
        oldest = min(_MEM.items(), key=lambda kv: kv[1][0])[0]
        _MEM.pop(oldest, None)
