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
from src.qs_auditor_tools import qs_audit_checklist
from src.boq_diff import compare_boq
from src.agents import (
    supervisor_node, mechanical_agent_node, electrical_agent_node,
    plumbing_agent_node, firefighting_agent_node,
    qs_agent_node, qs_auditor_agent_node, cad_agent_node, bim_agent_node,
    reviewer_agent_node
)
import src.agents_phase_a_patch  # noqa: F401
import src.agents_phase_b_patch  # noqa: F401
from src import agents as _agents_mod
supervisor_node = _agents_mod.supervisor_node

tools = list(_base_tools) + [
    replace_blocks_by_mapping,
    batch_edit_pipes,
    batch_replace_text,
    update_title_block,
    prepare_drawing,
    full_boq,
    qs_audit_checklist,
    compare_boq,
]

workflow = StateGraph(AgentState)

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

workflow.add_edge(START, "supervisor")

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

agents = ["mechanical", "electrical", "plumbing", "firefighting", "qs", "cad", "bim"]
for agent in agents:
    if agent == "qs":
        workflow.add_conditional_edges("qs", route_after_qs, {"tools": "tools", "qs_auditor": "qs_auditor"})
    else:
        workflow.add_conditional_edges(agent, route_after_agent, {"tools": "tools", "reviewer": "reviewer"})

workflow.add_edge("qs_auditor", "reviewer")

def route_after_tools(state: AgentState):
    sender = state.get("sender")
    if sender in agents or sender == "qs":
        return sender
    return "supervisor"

workflow.add_conditional_edges("tools", route_after_tools)
workflow.add_edge("reviewer", "supervisor")

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

logger = logging.getLogger(__name__)


def build_checkpointer(db_path: str = None):
    """Checkpointer: Postgres (Phase C) → SQLite → Memory."""
    try:
        from src.checkpointer_factory import try_postgres_checkpointer
        pg = try_postgres_checkpointer()
        if pg is not None:
            return pg
    except Exception as e:  # pragma: no cover
        logger.warning("Postgres checkpointer skip: %s", e)

    if not db_path:
        return MemorySaver()
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        import sqlite3
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        return SqliteSaver(conn)
    except Exception as e:  # pragma: no cover
        logger.warning("Không dùng được SQLite checkpointer (%s) — tạm dùng RAM.", e)
        return MemorySaver()


memory = build_checkpointer(settings.checkpoint_db)
GRAPH_CONFIG = {"recursion_limit": settings.recursion_limit}
app = workflow.compile(checkpointer=memory)
