"""Phase B tool binding — QS Auditor checklist + BOQ diff for QS/QSAuditor roles."""
from __future__ import annotations

from src.qs_auditor_tools import qs_audit_checklist
from src.boq_diff import compare_boq

QS_PHASE_B_TOOLS = [
    qs_audit_checklist,
    compare_boq,
]

PHASE_B_DELIVERABLE = {
    "qs_audit_checklist",
    "compare_boq",
}


def append_phase_b_tools(tools: list, role: str) -> list:
    role_key = (role or "").lower().strip()
    if role_key in ("qs", "qsauditor", "qs_auditor", "bim"):
        for t in QS_PHASE_B_TOOLS:
            if t not in tools:
                tools.append(t)
    return tools
