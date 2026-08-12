"""BOQ / takeoff diff — so sánh hai file Excel khối lượng.

Khớp hạng mục theo tên (fuzzy nhẹ), báo:
- thêm mới / xoá
- thay đổi khối lượng (delta + %)
- đổi đơn vị

Deterministic, không cần LLM.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

import pandas as pd
from langchain_core.tools import tool

from src.workspace import resolve_safe_path

logger = logging.getLogger(__name__)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _find_col(columns, candidates: tuple[str, ...]) -> str | None:
    norms = {_norm(c): c for c in columns}
    for cand in candidates:
        if _norm(cand) in norms:
            return norms[_norm(cand)]
    return None


def _load_items(path: str) -> dict[str, dict[str, Any]]:
    df = pd.read_excel(path)
    name_col = _find_col(df.columns, ("Hạng mục", "Tên công tác", "Nội dung"))
    qty_col = _find_col(df.columns, ("Khối lượng", "Số lượng"))
    unit_col = _find_col(df.columns, ("Đơn vị", "Unit"))
    if not name_col or not qty_col:
        raise ValueError(f"Thiếu cột Hạng mục/Khối lượng trong {path}. Có: {list(df.columns)}")
    items: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        if not name or name.lower() == "nan":
            continue
        key = _norm(name)
        qty = pd.to_numeric(row[qty_col], errors="coerce")
        qty_v = float(qty) if pd.notna(qty) else 0.0
        unit = str(row[unit_col]).strip() if unit_col and pd.notna(row.get(unit_col)) else ""
        if key in items:
            items[key]["qty"] += qty_v
        else:
            items[key] = {"name": name, "qty": qty_v, "unit": unit}
    return items


def diff_boq_tables(
    baseline_path: str,
    current_path: str,
    *,
    qty_tolerance: float = 0.01,
) -> dict[str, Any]:
    base = _load_items(baseline_path)
    cur = _load_items(current_path)

    added, removed, changed = [], [], []
    all_keys = set(base) | set(cur)
    for k in sorted(all_keys):
        b = base.get(k)
        c = cur.get(k)
        if b and not c:
            removed.append({"name": b["name"], "qty": b["qty"], "unit": b["unit"]})
        elif c and not b:
            added.append({"name": c["name"], "qty": c["qty"], "unit": c["unit"]})
        else:
            assert b and c
            delta = c["qty"] - b["qty"]
            if abs(delta) > qty_tolerance or (b["unit"] and c["unit"] and b["unit"] != c["unit"]):
                pct = (delta / b["qty"] * 100.0) if abs(b["qty"]) > 1e-9 else None
                changed.append({
                    "name": c["name"],
                    "qty_before": b["qty"],
                    "qty_after": c["qty"],
                    "delta": round(delta, 4),
                    "delta_pct": round(pct, 2) if pct is not None else None,
                    "unit_before": b["unit"],
                    "unit_after": c["unit"],
                })

    return {
        "baseline": baseline_path,
        "current": current_path,
        "n_baseline": len(base),
        "n_current": len(cur),
        "added": added,
        "removed": removed,
        "changed": changed,
        "n_added": len(added),
        "n_removed": len(removed),
        "n_changed": len(changed),
        "identical": not (added or removed or changed),
    }


def format_boq_diff(result: dict[str, Any], max_rows: int = 30) -> str:
    lines = [
        "=== BOQ DIFF ===",
        f"Baseline: {result['baseline']} ({result['n_baseline']} HM)",
        f"Current:  {result['current']} ({result['n_current']} HM)",
    ]
    if result.get("identical"):
        lines.append("Kết quả: KHÔNG ĐỔI (identical).")
        lines.append("=== HẾT BOQ DIFF ===")
        return "\n".join(lines)

    lines.append(
        f"Thay đổi: +{result['n_added']} thêm / -{result['n_removed']} xoá / "
        f"~{result['n_changed']} đổi KL"
    )
    if result["added"]:
        lines.append("--- THÊM ---")
        for row in result["added"][:max_rows]:
            lines.append(f"  + {row['name']}: {row['qty']} {row.get('unit') or ''}".rstrip())
    if result["removed"]:
        lines.append("--- XOÁ ---")
        for row in result["removed"][:max_rows]:
            lines.append(f"  - {row['name']}: {row['qty']} {row.get('unit') or ''}".rstrip())
    if result["changed"]:
        lines.append("--- ĐỔI KHỐI LƯỢNG ---")
        for row in result["changed"][:max_rows]:
            pct = f" ({row['delta_pct']:+.1f}%)" if row.get("delta_pct") is not None else ""
            lines.append(
                f"  ~ {row['name']}: {row['qty_before']} → {row['qty_after']} "
                f"(Δ {row['delta']:+.4g}){pct}"
            )
    lines.append("=== HẾT BOQ DIFF ===")
    return "\n".join(lines)


@tool
def compare_boq(
    baseline_excel_path: str,
    current_excel_path: str,
    qty_tolerance: float = 0.01,
) -> str:
    """So sánh hai file Excel khối lượng / BOQ (baseline vs current).

    Báo hạng mục thêm/xoá và thay đổi khối lượng (delta + %).
    Dùng khi khách gửi bản vẽ revision mới hoặc sau khi AI sửa takeoff.
    Deterministic — không cần LLM.
    """
    logger.info("compare_boq: %s vs %s", baseline_excel_path, current_excel_path)
    try:
        b = resolve_safe_path(baseline_excel_path)
        c = resolve_safe_path(current_excel_path)
        if not os.path.exists(b):
            return f"Lỗi: không tìm thấy baseline {baseline_excel_path}"
        if not os.path.exists(c):
            return f"Lỗi: không tìm thấy current {current_excel_path}"
        result = diff_boq_tables(b, c, qty_tolerance=qty_tolerance)
        result["baseline"] = baseline_excel_path
        result["current"] = current_excel_path
        return format_boq_diff(result)
    except Exception as e:
        return f"Lỗi compare_boq: {e}"
