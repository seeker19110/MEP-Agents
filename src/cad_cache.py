"""Process-level DXF document cache keyed by (abspath, mtime_ns, size)."""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

import ezdxf

logger = logging.getLogger(__name__)

# Giữ tham chiếu tới hàm gốc NGAY khi import: `cad_loader_perf_patch` tạm thời gán
# `ezdxf.readfile = readfile_cached` khi đọc xref, nên nếu ở đây gọi qua
# `ezdxf.readfile` thì mỗi lần cache miss sẽ tự gọi lại chính mình → đệ quy vô hạn
# (biểu hiện: "Không đọc được XREF ...: maximum recursion depth exceeded", nội dung
# xref bị bỏ khỏi khối lượng).
_ezdxf_readfile = ezdxf.readfile

_LOCK = threading.Lock()
_CACHE: dict[tuple[str, int, int], Any] = {}
_MAX_ENTRIES = int(os.environ.get("CAD_CACHE_MAX", "8"))


def _key(path: str) -> tuple[str, int, int] | None:
    try:
        st = os.stat(path)
        return (os.path.abspath(path), int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))), int(st.st_size))
    except OSError:
        return None


def readfile_cached(path: str):
    k = _key(path)
    if k is None:
        return _ezdxf_readfile(path)
    with _LOCK:
        doc = _CACHE.get(k)
        if doc is not None:
            logger.debug("CAD cache HIT %s", path)
            return doc
    logger.debug("CAD cache MISS %s", path)
    doc = _ezdxf_readfile(path)
    with _LOCK:
        _CACHE[k] = doc
        while len(_CACHE) > _MAX_ENTRIES:
            _CACHE.pop(next(iter(_CACHE)))
    return doc


def invalidate(path: str | None = None) -> None:
    with _LOCK:
        if path is None:
            _CACHE.clear()
            return
        abs_p = os.path.abspath(path)
        for k in list(_CACHE):
            if k[0] == abs_p:
                del _CACHE[k]


def cache_stats() -> dict:
    with _LOCK:
        return {"entries": len(_CACHE), "max": _MAX_ENTRIES}
