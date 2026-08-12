from typing import Annotated, Sequence, TypedDict, Any
from langchain_core.messages import BaseMessage
import operator

def update_dict(old_dict: dict, new_dict: dict) -> dict:
    """Merge two dictionaries, updating existing keys."""
    res = old_dict.copy()
    res.update(new_dict)
    return res

def replace_errors(old_errors: Sequence[str], new_errors: Sequence[str]) -> Sequence[str]:
    """Replace (not accumulate) the errors list.

    LangGraph reducers only ever combine old + new; with `operator.add`,
    returning `errors=[]` to clear the list is a no-op (old + [] == old),
    so once any error occurs it stays truthy for the rest of the thread.
    This reducer makes each node's returned value the new state instead.
    """
    return new_errors

RESET = "__RESET__"

def append_or_reset(old: Sequence[str], new: Sequence[str]) -> Sequence[str]:
    """Cộng dồn danh sách, trừ khi node gửi lên sentinel RESET thì xóa sạch.

    Cần thiết vì `completed_agents` chỉ có ý nghĩa trong phạm vi MỘT yêu cầu của khách
    hàng: sang câu hỏi mới, mọi bộ phận phải được coi là chưa chạy. Reducer thuần
    `operator.add` không cho phép xóa (old + [] == old).
    """
    if list(new) == [RESET]:
        return []
    return list(old) + list(new)


def replace_queue(old: Sequence[str], new: Sequence[str]) -> Sequence[str]:
    """Last-write-wins queue (Phase B multi-intent drain)."""
    return list(new)


class AgentState(TypedDict):
    """The routing state of the multi-agent system."""
    # Messages in the conversation
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # The next node to route to, if decided by supervisor
    next: str
    
    # Shared context dictionary (e.g. extracted variables, metadata)
    context: Annotated[dict[str, Any], update_dict]
    
    # Errors occurred during execution, if any (replaced, not accumulated, each update)
    errors: Annotated[Sequence[str], replace_errors]
    
    # Track the last active worker (e.g. "rag_agent" or "tool_agent")
    # so Reviewer knows who to send back to if there's an error.
    sender: str

    # How many times the Reviewer has rejected work on the current request.
    # Plain int (no reducer) => last write wins, so a node can both increment it and
    # reset it to 0. This is what bounds the self-correction loop: previously the
    # Reviewer had to blindly auto-approve any second attempt to avoid looping
    # forever, which meant retried work was never actually reviewed.
    retry_count: int

    # Names of the worker agents that already produced output for this request,
    # in order. Lets the Supervisor act like a real PM (e.g. run 'electrical'
    # then 'qs') instead of re-routing from the last message alone.
    completed_agents: Annotated[Sequence[str], append_or_reset]

    # --- Phase B: Human-in-the-loop ---
    # When True, supervisor should FINISH and wait for human approval text.
    awaiting_human: bool
    hil_reason: str

    # --- Phase B: multi-intent agent queue (ordered remaining workers) ---
    agent_queue: Annotated[Sequence[str], replace_queue]
