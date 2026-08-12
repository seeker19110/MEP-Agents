"""Phase A: agent binding patch wires CAD/QS tools + DELIVERABLE_TOOLS."""


def test_phase_a_patch_extends_cad_tools():
    import src.agents as agents
    import src.agents_phase_a_patch  # noqa: F401 — apply patch

    tools = agents.get_tools_for_role("cad")
    names = {getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools}
    assert "batch_edit_pipes" in names
    assert "batch_replace_text" in names
    assert "update_title_block" in names
    assert "prepare_drawing" in names
    assert "replace_blocks_by_mapping" in names


def test_phase_a_patch_extends_qs_tools():
    import src.agents as agents
    import src.agents_phase_a_patch  # noqa: F401

    tools = agents.get_tools_for_role("qs")
    names = {getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools}
    assert "full_boq" in names
    assert "prepare_drawing" in names
    assert "batch_replace_text" in names


def test_phase_a_deliverable_tools():
    import src.agents as agents
    import src.agents_phase_a_patch  # noqa: F401

    assert "full_boq" in agents.DELIVERABLE_TOOLS
    assert "prepare_drawing" in agents.DELIVERABLE_TOOLS
    assert "batch_edit_pipes" in agents.DELIVERABLE_TOOLS
    assert "auto_quantity_takeoff" in agents.DELIVERABLE_TOOLS
