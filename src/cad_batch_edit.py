"""Batch CAD edit skills — Phase A roadmap (facade).

Re-exports:
- batch_edit_pipes
- batch_replace_text
- update_title_block
"""
from src.cad_pipe_ops import batch_edit_pipes, apply_pipe_operations
from src.cad_text_ops import batch_replace_text, apply_text_replacements
from src.cad_title_ops import update_title_block

__all__ = [
    "batch_edit_pipes",
    "batch_replace_text",
    "update_title_block",
    "apply_pipe_operations",
    "apply_text_replacements",
]
