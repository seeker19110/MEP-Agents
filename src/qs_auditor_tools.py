"""QS Auditor — checklist deterministic (không cần LLM).

Kiểm tra kết quả takeoff / dự toán theo danh sách cố định:
- cột bắt buộc trên Excel khối lượng
- % hao hụt đã cộng
- hạng mục thiếu đơn giá
- Block lệch scale / cảnh báo trong Ghi chú
- tổng khối lượng bất thường (0 hoặc NaN)

Dùng bởi QS Auditor agent hoặc gọi trực tiếp qua tool.
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

_REQUIRED_COLS = ("Hạng mục", "Khối lượng")
_OPTIONAL_HINTS = ("Đơn vị", "Ghi chú", "Hệ", "Mã hiệu")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _find_col(columns, candidates: tuple[str, ...]) -> str | None:
    norms = {_norm(c): c for c in columns}
    for cand in candidates:
        if _norm(cand) in norms:
            return norms[_norm(cand)]
    return None


def run_qs_checklist(
    excel_path: str,
    *,
    cost_excel_path: str = "",
    min_items: int = 1,
    max_zero_qty_ratio: float = 0.3,
) -> dict[str, Any]:
    """Chạy checklist trên file Excel takeoff (và tuỳ chọn file dự toán)."""
    checks: list[dict[str, Any]] = []
    path = resolve_safe_path(excel_path)
    if not os.path.exists(path):
        return {
            "ok": False,
            "score": 0,
            "checks": [{"id": "file_exists", "pass": False, "detail": f"Không tìm thấy {excel_path}"}],
        }

    try:
        df = pd.read_excel(path)
    except Exception as e:
        return {
            "ok": False,
            "score": 0,
            "checks": [{"id": "readable", "pass": False, "detail": f"Không đọc được Excel: {e}"}],
        }

    name_col = _find_col(df.columns, ("Hạng mục", "Tên công tác", "Nội dung"))
    qty_col = _find_col(df.columns, ("Khối lượng", "Số lượng"))
    note_col = _find_col(df.columns, ("Ghi chú", "Note"))
    unit_col = _find_col(df.columns, ("Đơn vị", "Unit"))

    checks.append({
        "id": "required_columns",
        "pass": bool(name_col and qty_col),
        "detail": (
            f"Cột tên={name_col!r}, khối lượng={qty_col!r}"
            if name_col and qty_col
            else f"Thiếu cột bắt buộc. Có: {list(df.columns)}"
        ),
    })

    n_items = len(df) if name_col else 0
    checks.append({
        "id": "min_items",
        "pass": n_items >= min_items,
        "detail": f"{n_items} hạng mục (min={min_items})",
    })

    zero_ratio = 0.0
    if qty_col and n_items:
        qty = pd.to_numeric(df[qty_col], errors="coerce")
        zero_ratio = float(((qty.fillna(0) <= 0).sum()) / n_items)
        checks.append({
            "id": "zero_qty_ratio",
            "pass": zero_ratio <= max_zero_qty_ratio,
            "detail": f"{zero_ratio:.0%} hạng mục KL≤0 (ngưỡng {max_zero_qty_ratio:.0%})",
        })
    else:
        checks.append({"id": "zero_qty_ratio", "pass": False, "detail": "Không kiểm tra được KL"})

    wastage_mentions = 0
    scale_warnings = 0
    if note_col:
        notes = df[note_col].astype(str).fillna("")
        wastage_mentions = int(notes.str.contains(r"hao hụt|wastage", case=False, regex=True).sum())
        scale_warnings = int(notes.str.contains(r"scale|tỷ lệ|lệch", case=False, regex=True).sum())
    checks.append({
        "id": "wastage_noted",
        "pass": wastage_mentions > 0 or n_items == 0,
        "detail": f"{wastage_mentions} dòng ghi nhận hao hụt (ống/dây)",
        "severity": wastage_mentions == 0 and n_items > 0,
    })
    checks.append({
        "id": "scale_warnings",
        "pass": True,
        "detail": f"{scale_warnings} dòng cảnh báo scale/tỷ lệ",
        "severity": scale_warnings > 0,
    })

    missing_price = 0
    if cost_excel_path:
        cpath = resolve_safe_path(cost_excel_path)
        if os.path.exists(cpath):
            try:
                cdf = pd.read_excel(cpath)
                note_c = _find_col(cdf.columns, ("Ghi chú", "Note"))
                if note_c:
                    missing_price = int(
                        cdf[note_c].astype(str).str.contains("CHƯA CÓ ĐƠN GIÁ", case=False, na=False).sum()
                    )
                checks.append({
                    "id": "missing_unit_price",
                    "pass": missing_price == 0,
                    "detail": f"{missing_price} hạng mục chưa có đơn giá trong {cost_excel_path}",
                })
            except Exception as e:
                checks.append({
                    "id": "missing_unit_price",
                    "pass": False,
                    "detail": f"Không đọc cost excel: {e}",
                })
        else:
            checks.append({
                "id": "missing_unit_price",
                "pass": False,
                "detail": f"Không tìm thấy cost excel: {cost_excel_path}",
            })
    else:
        checks.append({
            "id": "missing_unit_price",
            "pass": True,
            "detail": "Bỏ qua (không truyền cost_excel_path)",
            "severity": True,
        })

    if unit_col:
        blank_units = int(df[unit_col].isna().sum() + (df[unit_col].astype(str).str.strip() == "").sum())
        checks.append({
            "id": "units_filled",
            "pass": blank_units == 0,
            "detail": f"{blank_units} hạng mục thiếu đơn vị",
        })

    hard = [c for c in checks if not c.get("severity")]
    passed = sum(1 for c in hard if c["pass"])
    score = int(round(100 * passed / max(len(hard), 1)))
    ok = all(c["pass"] for c in hard)

    return {
        "ok": ok,
        "score": score,
        "n_items": n_items,
        "checks": checks,
        "excel_path": excel_path,
        "cost_excel_path": cost_excel_path or None,
    }


def format_checklist_report(result: dict[str, Any]) -> str:
    lines = [
        "=== QS AUDITOR CHECKLIST ===",
        f"Kết quả: {'ĐẠT' if result.get('ok') else 'CHƯA ĐẠT'} — điểm {result.get('score', 0)}/100",
        f"File: {result.get('excel_path')} ({result.get('n_items', 0)} hạng mục)",
    ]
    if result.get("cost_excel_path"):
        lines.append(f"Cost file: {result['cost_excel_path']}")
    for c in result.get("checks") or []:
        mark = "✓" if c.get("pass") else "✗"
        soft = " (info)" if c.get("severity") else ""
        lines.append(f"  {mark} [{c.get('id')}]{soft}: {c.get('detail')}")
    lines.append("=== HẾT CHECKLIST ===")
    return "\n".join(lines)


@tool
def qs_audit_checklist(
    takeoff_excel_path: str,
    cost_excel_path: str = "",
    min_items: int = 1,
) -> str:
    """Kiểm toán QS deterministic trên file Excel khối lượng (và tuỳ chọn file dự toán).

    Checklist cố định: cột bắt buộc, số hạng mục, tỷ lệ KL≤0, ghi nhận hao hụt,
    cảnh báo scale, hạng mục thiếu đơn giá. Không cần LLM — phù hợp model yếu/offline.

    Gọi SAU `auto_quantity_takeoff` / `calc_boq_cost`. Trả về ĐẠT/CHƯA ĐẠT + điểm 0–100.
    """
    logger.info("qs_audit_checklist: %s", takeoff_excel_path)
    try:
        result = run_qs_checklist(
            takeoff_excel_path,
            cost_excel_path=cost_excel_path,
            min_items=min_items,
        )
        return format_checklist_report(result)
    except Exception as e:
        return f"Lỗi qs_audit_checklist: {e}"
