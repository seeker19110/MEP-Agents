"""Đăng ký đường tra cứu tiêu chuẩn bằng vectorstore (Phase C perf).

Trước đây module này tạo một tool `search_standards` mới rồi tráo nó vào `tools.py` ở 4
chỗ. Nay chỉ đăng ký một hàm vào `src/standards_backend.py` — đối tượng tool giữ nguyên
danh tính, không ai có thể cầm nhầm bản cũ. Xem TECH_DEBT.md mục 10.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

BACKEND_NAME = "vectorstore"
BACKEND_PRIORITY = 10


def vectorstore_search(query: str) -> str:
    """Trả về chuỗi kết quả, hoặc "" để nhường cho đường tra cứu kế tiếp."""
    from src.config import settings
    from src.vectorstore import search_standards_docs, use_pgvector

    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    has_real_key = bool(api_key) and api_key != "dummy_key_to_prevent_crash_on_import"
    index_path = os.environ.get("FAISS_INDEX_PATH", "faiss_index")
    if not (has_real_key and (use_pgvector() or os.path.exists(index_path))):
        return ""

    docs = search_standards_docs(query, k=3)
    if not docs:
        return ""

    result = f"Kết quả RAG Tiêu chuẩn cho '{query}':\n"
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "Unknown")
        result += f"\n--- Trích đoạn {i} (Nguồn: {source}) ---\n"
        result += doc.page_content + "\n"
    return result


def apply_vector_search_bind() -> None:
    import src.tools as tools_mod
    from src.standards_backend import register_backend

    if getattr(tools_mod, "_vector_search_patched", False):
        return
    register_backend(BACKEND_NAME, vectorstore_search, priority=BACKEND_PRIORITY)
    tools_mod._vector_search_patched = True
    logger.info("search_standards: đã đăng ký backend vectorstore")


apply_vector_search_bind()
