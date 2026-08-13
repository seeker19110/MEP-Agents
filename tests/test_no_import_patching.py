"""Không module nào được gán đè hàm/tool của module khác lúc import.

Đây là bất biến số 6 của dự án (`docs/DAC_TA_HE_THONG.md` mục 11). Kiểu nối "patch lúc
import" đã sinh ra ba sự cố thật:

1. `cad_cache` tự gọi chính mình gây đệ quy vô hạn → **mọi XREF bị loại khỏi khối lượng**
   trong im lặng (PR #32).
2. `api_phase_c_mount` gán đè `require_api_key` sau khi FastAPI đã chốt dependency vào
   route → **xác thực JWT chưa từng có hiệu lực**, API mở toang (PR #39).
3. Các tối ưu hiệu năng chỉ có tác dụng với ai import `src.graph` trước — Celery worker,
   `python -m src.ingest`, test gọi thẳng module đều lặng lẽ chạy bản chưa tối ưu.

Bốn module patch hiệu năng nay đã bị xóa, logic nằm thẳng trong hàm gốc.
"""
import importlib
import subprocess
import sys

import pytest

DELETED_PATCH_MODULES = [
    "src.agents_perf_patch",
    "src.qs_perf_patch",
    "src.cad_loader_perf_patch",
    "src.tools_lazy",
]


@pytest.mark.parametrize("module_name", DELETED_PATCH_MODULES)
def test_perf_patch_modules_are_gone(module_name):
    """Xóa hẳn chứ không để lại lớp tương thích rỗng: còn file là còn người import lại."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def _run_isolated(code: str) -> str:
    """Chạy trong tiến trình MỚI, cố ý KHÔNG import `src.graph`.

    Phải tách tiến trình: trong cùng một phiên pytest, file test khác đã import
    `src.graph` rồi, nên mọi patch (nếu còn) đã được áp — đúng cái làm lớp lỗi này vô
    hình suốt thời gian dài.
    """
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return result.stdout.strip()


def test_message_trimming_works_without_importing_graph():
    """Cắt bớt message phải có tác dụng ngay cả khi không ai import `src.graph`.

    Celery worker nạp `src.tools` chứ không nạp `src.graph` — trước đây nghĩa là worker
    chạy với lịch sử hội thoại đầy đủ, tốn token gấp bội mà không có dấu hiệu gì.
    """
    out = _run_isolated(
        "import sys; from langchain_core.messages import HumanMessage;"
        "from src.agents import _trimmed_messages;"
        "msgs=[HumanMessage(content=f'tin {i}') for i in range(200)];"
        "print(len(_trimmed_messages({'messages': msgs}, 'X')), 'src.graph' in sys.modules)"
    )
    count, graph_loaded = out.split()
    assert graph_loaded == "False", "test phải chạy khi CHƯA nạp src.graph"
    assert int(count) < 200, "message không được cắt khi thiếu src.graph"


def test_dxf_cache_works_without_importing_graph():
    """`load_drawing` phải đọc qua cache dù không ai import `src.graph`."""
    out = _run_isolated(
        "import sys, inspect; from src import cad_loader;"
        "src_code = inspect.getsource(cad_loader.load_drawing);"
        "print('cad_cache.readfile_cached' in src_code, 'src.graph' in sys.modules)"
    )
    cached, graph_loaded = out.split()
    assert graph_loaded == "False"
    assert cached == "True"


def test_role_tool_cache_works_without_importing_graph():
    out = _run_isolated(
        "import sys; import src.tools as t;"
        "t.get_tools_for_role('electrical');"
        "print(t._ROLE_CACHE.get('electrical') is not None, 'src.graph' in sys.modules)"
    )
    cached, graph_loaded = out.split()
    assert graph_loaded == "False"
    assert cached == "True"


def test_core_functions_keep_identity_after_loading_graph():
    """Danh tính hàm không đổi sau khi nạp `src.graph`.

    Đây là điều kiện khiến `from src.agents import supervisor_node` ở bất kỳ đâu, vào bất
    kỳ lúc nào, cũng nhận đúng hành vi đầy đủ — thứ mà kiểu patch không bảo đảm được.
    """
    out = _run_isolated(
        "from src.agents import call_mepf_agent, supervisor_node;"
        "from src.cad_loader import load_drawing;"
        "from src.tools import get_tools_for_role;"
        "from src.qs_tools import load_unit_prices;"
        "import src.graph;"
        "import src.agents as a, src.cad_loader as c, src.tools as t, src.qs_tools as q;"
        "print(call_mepf_agent is a.call_mepf_agent, supervisor_node is a.supervisor_node,"
        " load_drawing is c.load_drawing, get_tools_for_role is t.get_tools_for_role,"
        " load_unit_prices is q.load_unit_prices)"
    )
    assert out == "True True True True True", out


def test_unit_price_cache_does_not_unpickle_redis_data():
    """Bảng đơn giá đọc từ Redis phải qua Arrow IPC, không phải pickle.

    `pickle.loads` trên dữ liệu lấy từ Redis là chạy code tùy ý trong tiến trình QS —
    cùng lớp lỗi với `accept_content=['pickle']` của Celery.
    """
    import inspect

    from src import qs_tools

    source = inspect.getsource(qs_tools.load_unit_prices)
    # Bỏ dòng chú thích: bản thân đoạn code có ghi chú giải thích VÌ SAO không dùng
    # pickle, và chú thích đó không phải là việc dùng pickle.
    code_only = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    assert "pickle" not in code_only, "load_unit_prices không được dùng pickle"
    assert "read_ipc" in code_only
