"""Cross-cutting LLM context trimming — cut token cost without changing tool logic."""
from __future__ import annotations

import os
from typing import Any, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def _max_messages() -> int:
    try:
        from src.config import settings
        return int(getattr(settings, "agent_message_window", 0) or os.environ.get("AGENT_MESSAGE_WINDOW", "24"))
    except Exception:
        return int(os.environ.get("AGENT_MESSAGE_WINDOW", "24"))


def _max_tool_chars() -> int:
    try:
        from src.config import settings
        return int(getattr(settings, "max_tool_result_chars", 0) or os.environ.get("MAX_TOOL_RESULT_CHARS", "6000"))
    except Exception:
        return int(os.environ.get("MAX_TOOL_RESULT_CHARS", "6000"))


def _truncate_content(content: Any, limit: int) -> Any:
    if not isinstance(content, str) or len(content) <= limit:
        return content
    head = limit // 2
    tail = limit - head - 80
    return (
        content[:head]
        + f"\n\n…[đã cắt {len(content) - limit} ký tự để tiết kiệm token]…\n\n"
        + content[-tail:]
    )


def trim_messages_for_llm(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    msgs = list(messages or [])
    if not msgs:
        return msgs
    max_n = max(6, _max_messages())
    max_chars = max(1000, _max_tool_chars())
    last_human_idx = max((i for i, m in enumerate(msgs) if isinstance(m, HumanMessage)), default=-1)
    if len(msgs) > max_n:
        start = max(0, len(msgs) - max_n)
        if last_human_idx >= 0 and last_human_idx < start:
            head = msgs[last_human_idx : last_human_idx + 1]
            tail = msgs[-(max_n - 1) :]
            msgs = head + tail
        else:
            msgs = msgs[start:]
    out: list[BaseMessage] = []
    for m in msgs:
        content = getattr(m, "content", None)
        new_content = _truncate_content(content, max_chars)
        if new_content is content:
            out.append(m)
            continue
        if isinstance(m, ToolMessage):
            out.append(ToolMessage(content=new_content, tool_call_id=getattr(m, "tool_call_id", "") or "", name=getattr(m, "name", None)))
        elif isinstance(m, AIMessage):
            out.append(AIMessage(content=new_content, name=getattr(m, "name", None), tool_calls=getattr(m, "tool_calls", None) or []))
        elif isinstance(m, HumanMessage):
            out.append(HumanMessage(content=new_content))
        else:
            out.append(m)
    return out
