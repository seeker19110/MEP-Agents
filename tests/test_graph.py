"""Điều hướng cấp thấp của đồ thị LangGraph (src/graph.py): sau agent, sau QS, sau tools."""
from langchain_core.messages import AIMessage

from src.graph import route_after_agent, route_after_qs, route_after_tools, agents as AGENT_NAMES


def _ai_message_with_tool_call():
    return AIMessage(
        content="",
        tool_calls=[{"name": "calculate", "args": {}, "id": "call_1"}],
    )


def test_route_after_agent_goes_to_tools_when_tool_call_present():
    state = {"messages": [_ai_message_with_tool_call()]}
    assert route_after_agent(state) == "tools"


def test_route_after_agent_goes_to_reviewer_without_tool_calls():
    state = {"messages": [AIMessage(content="Đã tính xong.")]}
    assert route_after_agent(state) == "reviewer"


def test_route_after_qs_goes_to_tools_when_tool_call_present():
    state = {"messages": [_ai_message_with_tool_call()]}
    assert route_after_qs(state) == "tools"


def test_route_after_qs_goes_to_qs_auditor_without_tool_calls():
    state = {"messages": [AIMessage(content="Dự toán xong.")]}
    assert route_after_qs(state) == "qs_auditor"


def test_route_after_tools_returns_to_calling_agent():
    for sender in AGENT_NAMES:
        assert route_after_tools({"sender": sender}) == sender


def test_route_after_tools_treats_qs_like_an_agent():
    assert route_after_tools({"sender": "qs"}) == "qs"


def test_route_after_tools_falls_back_to_supervisor_for_unknown_sender():
    assert route_after_tools({"sender": "someone_unexpected"}) == "supervisor"
    assert route_after_tools({}) == "supervisor"
