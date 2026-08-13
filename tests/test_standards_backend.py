"""Điểm mở rộng tra cứu tiêu chuẩn (`src/standards_backend.py`).

Thay cho cách cũ: Phase C/D tạo tool `search_standards` mới rồi tráo nó vào 4 chỗ trong
`src/tools.py`. Kiểu tráo đó để lại bản cũ trong tay bất kỳ ai đã sao chép danh sách tool
từ trước — đúng lớp lỗi đã gây sự cố XREF ở PR #32.
"""
import pytest

from src import standards_backend as sb


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = dict(sb._BACKENDS)
    sb.clear_backends()
    yield
    sb.clear_backends()
    sb._BACKENDS.update(saved)


def test_falls_back_when_no_backend_registered():
    assert sb.run_search("TCVN 7447", lambda q: f"offline:{q}") == "offline:TCVN 7447"


def test_highest_priority_backend_wins():
    sb.register_backend("thap", lambda q: "thap", priority=1)
    sb.register_backend("cao", lambda q: "cao", priority=20)
    assert sb.run_search("x", lambda q: "offline") == "cao"
    assert sb.active_backend() == "cao"


def test_empty_result_yields_to_next_backend():
    """Backend không tìm được gì phải nhường, không được nuốt luôn câu hỏi."""
    sb.register_backend("cao", lambda q: "", priority=20)
    sb.register_backend("thap", lambda q: "thap", priority=1)
    assert sb.run_search("x", lambda q: "offline") == "thap"


def test_failing_backend_does_not_break_the_call():
    """Tra cứu tiêu chuẩn luôn phải trả về câu trả lời dùng được, kể cả khi
    vector store hỏng hoặc mất mạng."""
    def boom(query):
        raise RuntimeError("vector store sập")

    sb.register_backend("hong", boom, priority=20)
    assert sb.run_search("x", lambda q: "offline") == "offline"


def test_tool_object_identity_is_stable_across_registration():
    """Điểm cốt lõi: đăng ký backend KHÔNG được thay đối tượng tool. Ai đã giữ tham chiếu
    tool từ trước (ToolNode, cache theo vai trò) vẫn phải dùng đúng đường mới."""
    import src.tools as tools_mod

    before = tools_mod.search_standards
    sb.register_backend("gia", lambda q: f"backend:{q}", priority=99)

    assert tools_mod.search_standards is before
    assert before.invoke({"query": "TCVN 7447"}) == "backend:TCVN 7447"
