"""Điểm nối middleware cho supervisor (`src/supervisor_pipeline.py`).

Thay cho cách cũ: Phase B/D bọc rồi **gán đè** `agents.supervisor_node` lúc import. Kiểu
đó có ba chỗ mong manh mà test dưới đây khóa lại từng chỗ: thứ tự phụ thuộc import, ai giữ
tham chiếu cũ thì cầm nhầm bản chưa bọc, và không gỡ được lớp nào ra để kiểm thử.
"""
import pytest

from src import supervisor_pipeline as sp


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = dict(sp._MIDDLEWARE)
    sp.clear_middleware()
    yield
    sp.clear_middleware()
    sp._MIDDLEWARE.update(saved)


def _core(state):
    return {"next": "core"}


def test_runs_core_when_no_middleware():
    assert sp.run({}, _core) == {"next": "core"}


def test_higher_priority_runs_outermost():
    order = []

    def outer(state, call_next):
        order.append("vao-ngoai")
        result = call_next(state)
        order.append("ra-ngoai")
        return result

    def inner(state, call_next):
        order.append("vao-trong")
        result = call_next(state)
        order.append("ra-trong")
        return result

    sp.register_middleware("ngoai", outer, priority=20)
    sp.register_middleware("trong", inner, priority=10)

    assert sp.run({}, _core) == {"next": "core"}
    assert order == ["vao-ngoai", "vao-trong", "ra-trong", "ra-ngoai"]
    assert sp.registered_middleware() == ["ngoai", "trong"]


def test_middleware_can_short_circuit():
    sp.register_middleware("chan", lambda state, call_next: {"next": "chan-som"}, priority=5)
    assert sp.run({}, _core) == {"next": "chan-som"}


def test_failing_middleware_does_not_break_routing():
    """Một lớp phụ hỏng không được làm treo cả phiên làm việc — mất tính năng phụ vẫn hơn
    là người dùng không giao được việc nào."""
    def boom(state, call_next):
        raise RuntimeError("lớp này hỏng")

    sp.register_middleware("hong", boom, priority=20)
    sp.register_middleware("lanh", lambda s, nxt: {**nxt(s), "da_chay": True}, priority=10)

    assert sp.run({}, _core) == {"next": "core", "da_chay": True}


def test_registering_same_name_replaces_instead_of_stacking():
    """Import module patch hai lần không được tạo hai lớp chồng nhau — kiểu gán đè trước
    đây thì có, và không có cách nào phát hiện."""
    calls = []

    def mw(state, call_next):
        calls.append(1)
        return call_next(state)

    sp.register_middleware("trung-ten", mw, priority=10)
    sp.register_middleware("trung-ten", mw, priority=10)

    sp.run({}, _core)
    assert calls == [1]
    assert sp.registered_middleware() == ["trung-ten"]


def test_supervisor_node_identity_is_stable_and_carries_full_behaviour():
    """Điểm cốt lõi. `from src.agents import supervisor_node` lấy tham chiếu MỘT LẦN; với
    cách gán đè cũ, tham chiếu đó là bản chưa bọc và thiếu luật của Phase B/D —
    `src/graph.py` từng phải đọc lại `_agents_mod.supervisor_node` sau các dòng import chỉ
    vì lý do này."""
    from src.agents import supervisor_node as duoc_lay_som

    sp.register_middleware("them-sau", lambda s, nxt: {**nxt(s), "lop_moi": True}, priority=1)

    import src.agents as agents
    assert agents.supervisor_node is duoc_lay_som
    assert duoc_lay_som({"messages": []}).get("lop_moi") is True


def test_real_phases_register_expected_layers():
    """Thứ tự thật sau khi nạp cả hệ thống: Phase D bọc ngoài Phase B, đúng như thứ tự mà
    cách gán đè cũ tạo ra qua chuỗi import của graph.py."""
    sp._MIDDLEWARE.clear()
    import importlib

    import src.agents_phase_b_patch as pb
    import src.agents_phase_d_patch as pd_patch
    import src.agents as agents

    agents._phase_b_patched = False
    agents._phase_d_parallel_patched = False
    importlib.reload(pb)
    pd_patch._patch_supervisor_parallel()

    assert sp.registered_middleware() == ["phase_d_parallel", "phase_b_hil_queue"]
