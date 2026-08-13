"""Skill Phase A/B phải nằm sẵn trong registry chính (`src.tools`), không phụ thuộc
tầng patch lúc import.

Trước đây các skill này chỉ được gắn vào khi `src.graph` được import (kéo theo
`agents_phase_a_patch`/`agents_phase_b_patch`). Ai import thẳng `src.tools` — test, script,
hay một entrypoint khác — sẽ nhận bộ tool thiếu mà không có dấu hiệu gì. Test này import
`src.tools` ĐỘC LẬP, không đụng tới graph/patch, để khóa lại hành vi đó.
"""
import pytest

from src.tools import TOOLS_BY_ROLE, get_tools_for_role, tools


def _names(role):
    return {t.name for t in get_tools_for_role(role)}


@pytest.mark.parametrize("role,expected", [
    ("cad", {"replace_blocks_by_mapping", "batch_edit_pipes", "batch_replace_text",
             "update_title_block", "prepare_drawing"}),
    ("qs", {"replace_blocks_by_mapping", "prepare_drawing", "full_boq", "batch_replace_text",
            "qs_audit_checklist", "compare_boq"}),
    ("bim", {"qs_audit_checklist", "compare_boq"}),
])
def test_role_registry_contains_phase_a_b_skills(role, expected):
    assert expected <= _names(role)


def test_flat_tool_list_covers_every_role_tool():
    """`tools` là danh sách ToolNode dùng để THỰC THI. Tool nào bind cho agent mà không có
    ở đây thì model gọi được nhưng chạy sẽ lỗi."""
    flat = {t.name for t in tools}
    for role in TOOLS_BY_ROLE:
        missing = _names(role) - flat
        assert not missing, f"vai trò {role} bind tool không có trong ToolNode: {missing}"


def test_no_duplicate_tool_names_in_registry():
    """ToolNode nhận hai tool trùng tên là hành vi không xác định — tool nào thắng tùy thứ
    tự. Dễ xảy ra khi vừa đăng ký trong registry vừa gắn thêm bằng patch."""
    names = [t.name for t in tools]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"tool trùng tên trong `tools`: {dupes}"

    for role in TOOLS_BY_ROLE:
        role_names = [t.name for t in get_tools_for_role(role)]
        role_dupes = {n for n in role_names if role_names.count(n) > 1}
        assert not role_dupes, f"vai trò {role} có tool trùng tên: {role_dupes}"
