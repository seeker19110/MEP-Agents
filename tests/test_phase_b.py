"""Phase B: QS checklist, BOQ diff, HIL, parallel intent detection."""
from __future__ import annotations

import pandas as pd
import pytest

from src.workspace import resolve_safe_path, set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    return set_workspace_dir(str(tmp_path / "session_phase_b"))


def _write_takeoff(path, rows):
    pd.DataFrame(rows).to_excel(path, index=False)


def test_qs_checklist_pass(workspace):
    from src.qs_auditor_tools import run_qs_checklist, format_checklist_report

    path = resolve_safe_path("takeoff.xlsx")
    _write_takeoff(
        path,
        [
            {"Hạng mục": "Ống PPR Ø25", "Đơn vị": "m", "Khối lượng": 120.5, "Ghi chú": "đã cộng 5% hao hụt vật tư"},
            {"Hạng mục": "FCU 2.5HP", "Đơn vị": "bộ", "Khối lượng": 8, "Ghi chú": ""},
        ],
    )
    result = run_qs_checklist(path)
    assert result["ok"] is True
    assert result["score"] >= 80
    text = format_checklist_report(result)
    assert "ĐẠT" in text


def test_qs_checklist_missing_columns(workspace):
    from src.qs_auditor_tools import run_qs_checklist

    path = resolve_safe_path("bad.xlsx")
    _write_takeoff(path, [{"Foo": 1}])
    result = run_qs_checklist(path)
    assert result["ok"] is False
    ids = {c["id"]: c["pass"] for c in result["checks"]}
    assert ids["required_columns"] is False


def test_qs_checklist_missing_unit_price(workspace):
    from src.qs_auditor_tools import run_qs_checklist

    takeoff = resolve_safe_path("takeoff.xlsx")
    cost = resolve_safe_path("cost.xlsx")
    _write_takeoff(
        takeoff,
        [{"Hạng mục": "Ống", "Đơn vị": "m", "Khối lượng": 10, "Ghi chú": "đã cộng 5% hao hụt"}],
    )
    _write_takeoff(
        cost,
        [
            {
                "Hạng mục": "Ống",
                "Khối lượng": 10,
                "Thành tiền": 0,
                "Ghi chú": "CHƯA CÓ ĐƠN GIÁ - cần bổ sung",
            }
        ],
    )
    result = run_qs_checklist(takeoff, cost_excel_path=cost)
    assert result["ok"] is False
    miss = next(c for c in result["checks"] if c["id"] == "missing_unit_price")
    assert miss["pass"] is False


def test_boq_diff_detects_changes(workspace):
    from src.boq_diff import diff_boq_tables, format_boq_diff

    base = resolve_safe_path("base.xlsx")
    cur = resolve_safe_path("cur.xlsx")
    _write_takeoff(
        base,
        [
            {"Hạng mục": "Ống PPR Ø25", "Đơn vị": "m", "Khối lượng": 100},
            {"Hạng mục": "FCU", "Đơn vị": "bộ", "Khối lượng": 5},
        ],
    )
    _write_takeoff(
        cur,
        [
            {"Hạng mục": "Ống PPR Ø25", "Đơn vị": "m", "Khối lượng": 120},
            {"Hạng mục": "Sprinkler", "Đơn vị": "cái", "Khối lượng": 40},
        ],
    )
    result = diff_boq_tables(base, cur)
    assert result["n_added"] == 1
    assert result["n_removed"] == 1
    assert result["n_changed"] == 1
    text = format_boq_diff(result)
    assert "BOQ DIFF" in text
    assert "Sprinkler" in text


def test_boq_diff_identical(workspace):
    from src.boq_diff import diff_boq_tables

    p = resolve_safe_path("same.xlsx")
    rows = [{"Hạng mục": "A", "Đơn vị": "m", "Khối lượng": 1}]
    _write_takeoff(p, rows)
    result = diff_boq_tables(p, p)
    assert result["identical"] is True


def test_hil_approval_phrases():
    from src.hil import is_approval_text, request_human_gate, clear_human_gate

    assert is_approval_text("DUYỆT BẢN VẼ")
    assert is_approval_text("ok tiếp tục đi")
    assert not is_approval_text("từ chối")
    gate = request_human_gate("CAD đã sửa, chờ duyệt", payload={"file": "a.dxf"})
    assert gate["awaiting_human"] is True
    assert gate["next"] == "FINISH"
    cleared = clear_human_gate()
    assert cleared["awaiting_human"] is False


def test_parallel_intent_multi():
    from src.parallel_dispatch import detect_parallel_agents, plan_agent_queue, next_from_queue

    text = "Thiết kế hệ thống điện và lập dự toán khối lượng"
    agents = detect_parallel_agents(text)
    assert "electrical" in agents
    assert "qs" in agents
    queue = plan_agent_queue(text)
    assert len(queue) >= 2
    assert next_from_queue(queue, completed=["electrical"]) == "qs"
