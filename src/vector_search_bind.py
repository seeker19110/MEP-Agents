"""Bind optimised vector search into tools.search_standards (Phase C perf)."""
from __future__ import annotations

import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def apply_vector_search_bind() -> None:
    import src.tools as tools_mod

    if getattr(tools_mod, "_vector_search_patched", False):
        return

    offline = tools_mod._offline_keyword_search

    @tool
    def search_standards(query: str) -> str:
        """Tra cứu Tiêu chuẩn thiết kế MEPF (TCVN, ASHRAE, NFPA...) từ cơ sở dữ liệu nội bộ.
        Dùng FAISS hoặc pgvector qua `src.vectorstore` (cache store + cache embedding).
        Không có API key / index thì rơi về offline keyword search."""
        logger.info("Tra cứu tiêu chuẩn thực: %s", query)
        try:
            from src.config import settings
            from src.vectorstore import search_standards_docs, use_pgvector

            api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
            has_real_key = bool(api_key) and api_key != "dummy_key_to_prevent_crash_on_import"
            index_path = os.environ.get("FAISS_INDEX_PATH", "faiss_index")
            can_vector = has_real_key and (use_pgvector() or os.path.exists(index_path))

            if not can_vector:
                return offline(query)

            docs = search_standards_docs(query, k=3)
            if not docs:
                return offline(query)

            result = f"Kết quả RAG Tiêu chuẩn cho '{query}':\n"
            for i, doc in enumerate(docs, 1):
                source = doc.metadata.get("source", "Unknown")
                result += f"\n--- Trích đoạn {i} (Nguồn: {source}) ---\n"
                result += doc.page_content + "\n"
            return result
        except Exception as e:
            logger.warning("Lỗi tra cứu RAG, chuyển sang offline: %s", e)
            try:
                return offline(query)
            except Exception as e2:
                return f"Lỗi tra cứu tiêu chuẩn: {e2}"

    old = tools_mod.search_standards
    tools_mod.search_standards = search_standards

    def _swap(seq):
        if not seq:
            return seq
        return [search_standards if t is old or getattr(t, "name", None) == "search_standards" else t for t in seq]

    if hasattr(tools_mod, "tools"):
        tools_mod.tools = _swap(list(tools_mod.tools))
    if hasattr(tools_mod, "_COMMON_TOOLS"):
        tools_mod._COMMON_TOOLS = _swap(list(tools_mod._COMMON_TOOLS))
    if hasattr(tools_mod, "TOOLS_BY_ROLE"):
        tools_mod.TOOLS_BY_ROLE = {
            role: _swap(list(ts)) for role, ts in tools_mod.TOOLS_BY_ROLE.items()
        }

    tools_mod._vector_search_patched = True
    logger.info("search_standards bound to optimised vectorstore path")


apply_vector_search_bind()
