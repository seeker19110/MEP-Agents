"""Per-session workspace isolation and path-traversal protection.

All file tools (read_excel, write_cad, ...) accept a `file_path` argument
supplied directly by the LLM. Without a guard rail, that path could point
anywhere on disk (`../../etc/passwd`) and, in a multi-user Streamlit
deployment, every session would read/write the same shared directory,
leaking one user's drawings/reports to another. `resolve_safe_path`
confines every file operation to the *current* session's workspace
directory, tracked via a contextvar so tool functions don't need the
LLM-supplied argument list changed to carry a session id.
"""
import contextvars
import os

_DEFAULT_WORKSPACE = os.path.abspath(os.getcwd())

_workspace_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "workspace_dir", default=_DEFAULT_WORKSPACE
)


def set_workspace_dir(path: str) -> str:
    """Set the active workspace directory for the current context (e.g. one Streamlit session)."""
    abs_path = os.path.abspath(path)
    os.makedirs(abs_path, exist_ok=True)
    _workspace_var.set(abs_path)
    return abs_path


def get_workspace_dir() -> str:
    return _workspace_var.get()


def get_project_root() -> str:
    """The fixed project root (not session-specific) — used for shared, trusted
    resources like the central CAD block library, which must stay reachable
    regardless of which per-session workspace is currently active."""
    return _DEFAULT_WORKSPACE


def resolve_safe_path(file_path: str) -> str:
    """Resolve `file_path` against the active workspace, rejecting any path that escapes it."""
    root = get_workspace_dir()
    candidate = os.path.abspath(os.path.join(root, file_path))
    if candidate != root and not candidate.startswith(root + os.sep):
        raise ValueError(
            f"Đường dẫn '{file_path}' nằm ngoài phạm vi làm việc cho phép (workspace: {root})."
        )
    return candidate
