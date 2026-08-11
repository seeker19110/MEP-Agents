from src.state import replace_errors


def test_replace_errors_clears_previous_errors():
    """Regression test for the infinite-loop / permanent-auto-approve bug: the reducer
    used to be operator.add, so returning errors=[] to "clear" the list was a no-op
    (old + [] == old), meaning the Reviewer guardrail was auto-approving everything
    forever after the first rejection in a thread."""
    old = ["Thiếu trích dẫn tiêu chuẩn TCVN."]
    assert replace_errors(old, []) == []


def test_replace_errors_replaces_not_accumulates():
    old = ["lỗi cũ"]
    new = ["lỗi mới"]
    result = replace_errors(old, new)
    assert result == new
    assert "lỗi cũ" not in result
