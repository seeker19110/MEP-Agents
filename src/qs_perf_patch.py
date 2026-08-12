"""Add in-process unit-price cache under Redis."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_qs_perf_patch() -> None:
    try:
        import src.qs_tools as qs
    except Exception as e:
        logger.warning("qs_perf_patch skip: %s", e)
        return
    if getattr(qs, "_perf_patched", False):
        return

    _orig = qs.load_unit_prices

    def load_unit_prices(csv_path: str = None):
        from src.unit_price_cache import mem_get, mem_set
        key = f"unit_prices:{csv_path or 'default'}"
        hit = mem_get(key)
        if hit is not None:
            return hit
        df = _orig(csv_path)
        try:
            mem_set(key, df)
        except Exception:
            pass
        return df

    qs.load_unit_prices = load_unit_prices
    qs._perf_patched = True
    logger.info("qs_perf_patch applied (in-process unit price cache)")


apply_qs_perf_patch()
