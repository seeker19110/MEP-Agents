"""Phase D: parallel supervisor + hybrid search + local embeddings."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_phase_d() -> None:
    _patch_embeddings()
    _patch_vector_search_hybrid()
    _patch_supervisor_parallel()
    try:
        import src.tools_lazy  # noqa: F401
    except Exception as e:
        logger.warning("tools_lazy skip: %s", e)


def _patch_embeddings() -> None:
    try:
        import src.vectorstore as vs
        from src.local_embeddings import get_embeddings_auto
        if getattr(vs, "_local_emb_patched", False):
            return
        vs.get_embeddings = lambda: get_embeddings_auto()
        if hasattr(vs, "_cached_embed_query"):
            try:
                vs._cached_embed_query.cache_clear()
            except Exception:
                pass
        vs._local_emb_patched = True
        logger.info("vectorstore embeddings → auto (openai/ollama/local)")
    except Exception as e:
        logger.warning("local embeddings patch skip: %s", e)


def _patch_vector_search_hybrid() -> None:
    try:
        import src.tools as tools_mod
        from langchain_core.tools import tool
        from src.hybrid_search import hybrid_search_standards, format_hybrid_results
        if getattr(tools_mod, "_hybrid_patched", False):
            return
        offline = tools_mod._offline_keyword_search

        @tool
        def search_standards(query: str) -> str:
            """Tra cứu tiêu chuẩn MEPF (hybrid: vector + từ khóa TCVN)."""
            logger.info("Hybrid search_standards: %s", query)
            try:
                hits = hybrid_search_standards(query, k=4)
                if hits:
                    return format_hybrid_results(query, hits)
            except Exception as e:
                logger.warning("hybrid failed (%s) — offline", e)
            return offline(query)

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
            tools_mod.TOOLS_BY_ROLE = {r: _swap(list(ts)) for r, ts in tools_mod.TOOLS_BY_ROLE.items()}
        tools_mod._hybrid_patched = True
        logger.info("search_standards → hybrid")
    except Exception as e:
        logger.warning("hybrid search patch skip: %s", e)


def _patch_supervisor_parallel() -> None:
    import src.agents as agents
    from langchain_core.messages import HumanMessage
    if getattr(agents, "_phase_d_parallel_patched", False):
        return
    _orig = agents.supervisor_node

    def supervisor_node(state):
        messages = state.get("messages", []) or []
        last = messages[-1] if messages else None
        if isinstance(last, HumanMessage):
            text = str(getattr(last, "content", "") or "")
            done = list(state.get("completed_agents", []) or [])
            from src.supervisor_parallel import detect_parallel_workers
            workers = detect_parallel_workers(text, done)
            if workers:
                logger.info("[PM] Parallel fan-out candidates: %s", workers)
                result = _orig(state)
                if not isinstance(result, dict):
                    result = {}
                result["parallel_workers"] = workers
                if not result.get("next") or result.get("next") == "FINISH":
                    result["next"] = workers[0]
                rest = workers[1:]
                if rest and not result.get("agent_queue"):
                    result["agent_queue"] = rest
                return result
        return _orig(state)

    agents.supervisor_node = supervisor_node
    agents._phase_d_parallel_patched = True
    logger.info("supervisor parallel detection enabled")


apply_phase_d()
