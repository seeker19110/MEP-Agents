import logging
import os

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from src.state import AgentState
from src.config import settings
from src.tools import tools as _base_tools
from src.cad_block_replace import replace_blocks_by_mapping
from src.cad_batch_edit import batch_edit_pipes, batch_replace_text, update_title_block
from src.cad_macros import prepare_drawing, full_boq
from src.agents import (
    supervisor_node, mechanical_agent_node, electrical_agent_node,
    plumbing_agent_node, firefighting_agent_node,
    qs_agent_node, qs_auditor_agent_node, cad_agent_node, bim_agent_node,
    reviewer_agent_node
)

# Tool mới đăng ký ngoài `src/tools.py` để tránh đụng file registry quá lớn khi mở rộng
# từng skill CAD; ToolNode phải thấy đủ tool để thực thi mọi tool_call từ agent.
tools = list(_base_tools) + [
    replace_blocks_by_mapping,
    batch_edit_pipes,
    batch_replace_text,
    update_title_block,
    prepare_drawing,
    full_boq,
]

# 1. Khởi tạo Graph
workflow = StateGraph(AgentState)

# 2. Thêm các Node cho phòng MEPF, QS, CAD, BIM và Tools
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("mechanical", mechanical_agent_node)
workflow.add_node("electrical", electrical_agent_node)
workflow.add_node("plumbing", plumbing_agent_node)
workflow.add_node("firefighting", firefighting_agent_node)
workflow.add_node("qs", qs_agent_node)
workflow.add_node("qs_auditor", qs_auditor_agent_node)
workflow.add_node("cad", cad_agent_node)
workflow.add_node("bim", bim_agent_node)
workflow.add_node("reviewer", reviewer_agent_node)
workflow.add_node("tools", ToolNode(tools))

# 3. Khai báo các Edges
workflow.add_edge(START, "supervisor")

# Hàm điều hướng sau khi Agent xử lý: Có gọi Tool hay lên Reviewer?
def route_after_agent(state: AgentState):
    last_msg = state.get("messages", [])[-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return "reviewer"
    
def route_after_qs(state: AgentState):
    last_msg = state.get("messages", [])[-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return "qs_auditor"

# Áp dụng điều hướng cho tất cả Agent
agents = ["mechanical", "electrical", "plumbing", "firefighting", "qs", "cad", "bim"]
for agent in agents:
    if agent == "qs":
        # Áp dụng điều hướng riêng cho QS (chuyển qua qs_auditor thay vì reviewer)
        workflow.add_conditional_edges("qs", route_after_qs, {"tools": "tools", "qs_auditor": "qs_auditor"})
    else:
        workflow.add_conditional_edges(
            agent,
            route_after_agent,
            {"tools": "tools", "reviewer": "reviewer"}
        )

workflow.add_edge("qs_auditor", "reviewer")


# Hàm điều hướng sau khi Tools chạy xong: Trả về Agent đã gọi
def route_after_tools(state: AgentState):
    sender = state.get("sender")
    if sender in agents or sender == "qs":
        return sender
    return "supervisor"

workflow.add_conditional_edges("tools", route_after_tools)

# Reviewer phản hồi cho Supervisor
workflow.add_edge("reviewer", "supervisor")

# Supervisor định tuyến luồng
workflow.add_conditional_edges(
    "supervisor",
    lambda state: state.get("next", "FINISH"),
    {
        "mechanical": "mechanical",
        "electrical": "electrical",
        "plumbing": "plumbing",
        "firefighting": "firefighting",
        "qs": "qs",
        "cad": "cad",
        "bim": "bim",
        "FINISH": END
    }
)

# 4. Compile đồ thị kèm checkpointer (bộ nhớ hội thoại)
logger = logging.getLogger(__name__)


def build_checkpointer(db_path: str = None):
    """Checkpointer bền vững (SQLite) nếu cấu hình được `checkpoint_db`, ngược lại RAM.

    MemorySaver mất TOÀN BỘ lịch sử hội thoại mỗi lần tiến trình khởi động lại
    (redeploy, Streamlit restart, hết phiên container), nên mặc định hệ thống ghi
    checkpoint xuống file SQLite. Nếu không dùng được (thiếu package, đĩa chỉ đọc)
    thì rơi về MemorySaver thay vì làm sập ứng dụng.
    """
    if not db_path:
        return MemorySaver()
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        import sqlite3

        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        # check_same_thread=False: Streamlit chạy mỗi rerun trên một thread khác nhau.
        conn = sqlite3.connect(db_path, check_same_thread=False)
        return SqliteSaver(conn)
    except Exception as e:  # pragma: no cover - phụ thuộc môi trường cài đặt
        logger.warning(
            "Không dùng được SQLite checkpointer (%s) — tạm dùng bộ nhớ RAM, "
            "lịch sử hội thoại sẽ mất khi restart.", e
        )
        return MemorySaver()


memory = build_checkpointer(settings.checkpoint_db)

# recursion_limit là chốt chặn cuối cùng chống vòng lặp supervisor -> agent ->
# reviewer -> supervisor. Hạn mức nghiệp vụ (số lần Reviewer được từ chối) nằm ở
# `settings.max_review_retries` trong src/agents.py.
GRAPH_CONFIG = {"recursion_limit": settings.recursion_limit}

app = workflow.compile(checkpointer=memory)
