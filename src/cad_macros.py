"""Macro tools — gom chuỗi CAD/QS thành 1 lần gọi tool (phù hợp model yếu/offline).

- prepare_drawing: audit → optimize → standardize  (+ optional replace_blocks)
- full_boq: auto_quantity_takeoff → calc_boq_cost → export_boq_vietnam
"""
from __future__ import annotations

import json
import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def prepare_drawing(
    file_path: str,
    output_path: str = "",
    run_optimize: bool = True,
    run_standardize: bool = True,
    run_audit: bool = True,
    block_mapping_json: str = "",
) -> str:
    """Chuẩn bị bản vẽ CAD trước khi bóc khối lượng — 1 lần gọi tool duy nhất.

    Pipeline deterministic:
    1) audit_cad_drawing_errors (chỉ đọc, báo cáo)
    2) optimize_cad_drawing (overkill + purge + xóa rác)
    3) standardize_cad_drawing (đổi tên layer/block về chuẩn nội bộ)
    4) (tuỳ chọn) replace_blocks_by_mapping nếu truyền block_mapping_json

    Dùng TRƯỚC `auto_quantity_takeoff` / `full_boq` để giảm sai lệch khối lượng
    do bản vẽ bẩn, layer lạ, block trùng.
    """
    logger.info("prepare_drawing macro: %s", file_path)
    sections: list[str] = ["=== PREPARE DRAWING (macro) ==="]
    working = file_path
    target = output_path.strip()

    try:
        if run_audit:
            from src.tools import audit_cad_drawing_errors
            audit_report = audit_cad_drawing_errors.invoke({"file_path": working})
            sections.append("--- AUDIT ---")
            sections.append(str(audit_report))

        if run_optimize:
            from src.tools import optimize_cad_drawing
            kwargs = {"file_path": working}
            # First write step may redirect to output_path
            if target:
                kwargs["output_path"] = target
            opt_report = optimize_cad_drawing.invoke(kwargs)
            sections.append("--- OPTIMIZE ---")
            sections.append(str(opt_report))
            if target:
                working = target

        if run_standardize:
            from src.tools import standardize_cad_drawing
            kwargs = {"file_path": working}
            if target and not run_optimize:
                kwargs["output_path"] = target
            std_report = standardize_cad_drawing.invoke(kwargs)
            sections.append("--- STANDARDIZE ---")
            sections.append(str(std_report))
            if target:
                working = target

        if block_mapping_json and block_mapping_json.strip():
            from src.cad_block_replace import replace_blocks_by_mapping
            kwargs = {
                "file_path": working,
                "mapping_json": block_mapping_json,
                "import_from_library": True,
            }
            if target:
                kwargs["output_path"] = target
            rep_report = replace_blocks_by_mapping.invoke(kwargs)
            sections.append("--- REPLACE BLOCKS ---")
            sections.append(str(rep_report))
            if target:
                working = target

        sections.append(f"=== HOÀN TẤT prepare_drawing — file làm việc: {working} ===")
        sections.append(
            "Gợi ý: tiếp theo gọi `full_boq` hoặc `auto_quantity_takeoff` trên file này."
        )
        return "\n".join(sections)
    except Exception as e:
        sections.append(f"LỖI prepare_drawing: {e}")
        return "\n".join(sections)


@tool
def full_boq(
    file_path: str,
    wastage_percent: float = 5.0,
    mep_only: bool = False,
    drawing_unit: str = "",
    project_name: str = "",
    skip_prepare: bool = False,
) -> str:
    """Bóc khối lượng + lập dự toán + xuất BOQ Việt Nam — 1 lần gọi tool duy nhất.

    Pipeline:
    1) (mặc định) prepare_drawing nếu skip_prepare=false
    2) auto_quantity_takeoff → Excel khối lượng
    3) calc_boq_cost → Excel dự toán có tiền
    4) export_boq_vietnam → bảng nộp thầu theo chương mục

    skip_prepare=true khi đã chạy prepare_drawing trước đó trong cùng phiên.
    """
    logger.info("full_boq macro: %s skip_prepare=%s", file_path, skip_prepare)
    sections: list[str] = ["=== FULL BOQ (macro) ==="]
    working = file_path

    try:
        if not skip_prepare:
            prep = prepare_drawing.invoke({"file_path": working})
            sections.append(str(prep))

        from src.qs_tools import auto_quantity_takeoff, calc_boq_cost, export_boq_vietnam

        takeoff_kwargs: dict = {
            "file_path": working,
            "wastage_percent": wastage_percent,
            "mep_only": mep_only,
        }
        if drawing_unit:
            takeoff_kwargs["drawing_unit"] = drawing_unit

        # auto_quantity_takeoff signature may vary — pass only known keys safely
        try:
            takeoff_report = auto_quantity_takeoff.invoke(takeoff_kwargs)
        except Exception:
            # Fallback without optional kwargs
            takeoff_report = auto_quantity_takeoff.invoke({"file_path": working})
        sections.append("--- TAKEOFF ---")
        sections.append(str(takeoff_report))

        # Infer quantity excel path from common naming conventions in takeoff report
        qty_excel = _guess_excel_from_report(str(takeoff_report), prefer="khoi_luong")
        if not qty_excel:
            sections.append(
                "CẢNH BÁO: không suy ra được file Excel khối lượng từ báo cáo takeoff — "
                "bỏ qua calc_boq_cost / export_boq_vietnam. Hãy gọi riêng với file Excel cụ thể."
            )
            return "\n".join(sections)

        try:
            cost_report = calc_boq_cost.invoke({"excel_path": qty_excel})
        except Exception:
            try:
                cost_report = calc_boq_cost.invoke({"file_path": qty_excel})
            except Exception as e:
                cost_report = f"Lỗi calc_boq_cost: {e}"
        sections.append("--- COST ---")
        sections.append(str(cost_report))

        cost_excel = _guess_excel_from_report(str(cost_report), prefer="du_toan") or qty_excel
        export_kwargs: dict = {"excel_path": cost_excel}
        if project_name:
            export_kwargs["project_name"] = project_name
        try:
            export_report = export_boq_vietnam.invoke(export_kwargs)
        except Exception:
            try:
                export_report = export_boq_vietnam.invoke({"file_path": cost_excel})
            except Exception as e:
                export_report = f"Lỗi export_boq_vietnam: {e}"
        sections.append("--- EXPORT BOQ VN ---")
        sections.append(str(export_report))

        sections.append("=== HOÀN TẤT full_boq ===")
        return "\n".join(sections)
    except Exception as e:
        sections.append(f"LỖI full_boq: {e}")
        return "\n".join(sections)


def _guess_excel_from_report(report: str, prefer: str = "") -> str:
    """Tìm đường dẫn .xlsx xuất hiện trong báo cáo tool."""
    import re
    paths = re.findall(r"[\w./\\-]+\.xlsx", report, flags=re.IGNORECASE)
    if not paths:
        return ""
    if prefer:
        for p in paths:
            if prefer.lower() in p.lower():
                return p
    return paths[-1]
