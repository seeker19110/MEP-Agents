"""Phase D: parallel supervisor + hybrid search + local embeddings."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_phase_d() -> None:
    # Việc chọn nguồn embedding nay nằm thẳng trong `src/vectorstore.py::get_embeddings`,
    # không còn gắn bằng patch — nhờ vậy `python -m src.ingest` (không import graph) cũng
    # dùng được embedding cục bộ. Xem TECH_DEBT.md mục 10.
    _patch_vector_search_hybrid()
    _patch_supervisor_parallel()
    try:
        import src.tools_lazy  # noqa: F401
    except Exception as e:
        logger.warning("tools_lazy skip: %s", e)


def _patch_vector_search_hybrid() -> None:
    """Đăng ký đường tra cứu lai (vector + từ khóa RRF) làm backend ưu tiên cao nhất.

    Trước đây hàm này tạo tool `search_standards` mới rồi tráo vào 4 chỗ trong `tools.py`.
    Nay chỉ đăng ký một hàm — đối tượng tool giữ nguyên danh tính. Xem
    `src/standards_backend.py` và TECH_DEBT.md mục 10.
    """
    try:
        import src.tools as tools_mod
        from src.hybrid_search import hybrid_search_standards, format_hybrid_results
        from src.standards_backend import register_backend

        if getattr(tools_mod, "_hybrid_patched", False):
            return

        def hybrid_backend(query: str) -> str:
            hits = hybrid_search_standards(query, k=4)
            if not hits:
                return ""
            return format_hybrid_results(query, hits)

        register_backend("hybrid", hybrid_backend, priority=20)
        tools_mod._hybrid_patched = True
        logger.info("search_standards: đã đăng ký backend hybrid")
    except Exception as e:
        logger.warning("hybrid search patch skip: %s", e)


#: Ưu tiên của lớp Phase D. Cao hơn Phase B nên nằm NGOÀI — giữ đúng thứ tự cũ, khi
#: Phase D bọc sau Phase B nên ở ngoài cùng.
PHASE_D_PRIORITY = 20


def _patch_supervisor_parallel() -> None:
    """Đăng ký lớp phát hiện fan-out song song.

    Trước đây gán đè `agents.supervisor_node`; nay đăng ký middleware nên không phụ thuộc
    thứ tự import và không ai cầm nhầm bản chưa bọc. Xem `src/supervisor_pipeline.py`.
    """
    import src.agents as agents
    from langchain_core.messages import HumanMessage
    from src.supervisor_pipeline import register_middleware

    if getattr(agents, "_phase_d_parallel_patched", False):
        return

    def phase_d_middleware(state, call_next):
        messages = state.get("messages", []) or []
        last = messages[-1] if messages else None
        if isinstance(last, HumanMessage):
            text = str(getattr(last, "content", "") or "")
            done = list(state.get("completed_agents", []) or [])
            from src.supervisor_parallel import detect_parallel_workers
            workers = detect_parallel_workers(text, done)
            if workers:
                logger.info("[PM] Parallel fan-out candidates: %s", workers)
                result = call_next(state)
                if not isinstance(result, dict):
                    result = {}
                result["parallel_workers"] = workers
                if not result.get("next") or result.get("next") == "FINISH":
                    result["next"] = workers[0]
                rest = workers[1:]
                if rest and not result.get("agent_queue"):
                    result["agent_queue"] = rest
                return result
        return call_next(state)

    register_middleware("phase_d_parallel", phase_d_middleware, priority=PHASE_D_PRIORITY)
    agents._phase_d_parallel_patched = True
    logger.info("Phase D: đã đăng ký middleware fan-out song song")


apply_phase_d()
