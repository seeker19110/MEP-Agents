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
