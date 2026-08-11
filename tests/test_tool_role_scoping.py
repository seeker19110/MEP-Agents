from src.tools import tools, get_tools_for_role, TOOLS_BY_ROLE


def test_full_registry_used_by_default_for_unknown_role():
    assert get_tools_for_role("some_unrecognized_role") == tools


def test_role_lookup_is_case_and_whitespace_insensitive():
    assert get_tools_for_role("Mechanical") == get_tools_for_role("  mechanical  ")


def test_every_role_subset_is_strictly_smaller_than_full_registry():
    for role, subset in TOOLS_BY_ROLE.items():
        assert len(subset) < len(tools), f"role '{role}' isn't actually trimmed"


def test_role_subsets_only_contain_tools_from_the_full_registry():
    tool_names = {t.name for t in tools}
    for role, subset in TOOLS_BY_ROLE.items():
        for tool in subset:
            assert tool.name in tool_names, f"role '{role}' references unknown tool {tool.name!r}"


def test_electrical_excludes_cad_and_hvac_specific_tools():
    names = {t.name for t in get_tools_for_role("electrical")}
    assert "calc_cable_size" in names
    assert "read_cad" not in names
    assert "calc_duct_size" not in names
    assert "calc_sprinkler_qty" not in names


def test_cad_role_includes_execute_python_code_and_render():
    names = {t.name for t in get_tools_for_role("cad")}
    assert {"read_cad", "write_cad", "edit_cad", "render_cad_image", "execute_python_code"} <= names


def test_qs_role_includes_write_excel_but_not_cad_editing():
    names = {t.name for t in get_tools_for_role("qs")}
    assert "write_excel" in names
    assert "read_cad" in names
    assert "write_cad" not in names
    assert "edit_cad" not in names


def test_all_roles_share_search_standards_and_basic_utilities():
    for role in TOOLS_BY_ROLE:
        names = {t.name for t in get_tools_for_role(role)}
        assert "search_standards" in names
        assert "calculate" in names
