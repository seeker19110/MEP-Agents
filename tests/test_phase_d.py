"""Phase D: hybrid, parallel detect, lazy cache."""
from __future__ import annotations


def test_detect_parallel_workers():
    from src.supervisor_parallel import detect_parallel_workers
    w = detect_parallel_workers("Tính điện chiếu sáng và chọn AHU điều hòa cho văn phòng")
    assert "electrical" in w and "mechanical" in w
    assert detect_parallel_workers("Bóc khối lượng file dxf") == []


def test_rrf_hybrid_keyword_only(monkeypatch):
    from src import hybrid_search as hs
    monkeypatch.setattr(hs, "_vector_hits", lambda q, k=8: [])
    monkeypatch.setattr(
        hs,
        "_keyword_hits",
        lambda q, k=8: [("a.txt", "TCVN 9206 cáp điện", 0.5), ("b.txt", "ống gió", 0.2)],
    )
    hits = hs.hybrid_search_standards("TCVN 9206", k=2)
    assert hits and "9206" in hits[0][1]


def test_tools_lazy_cache():
    """Cache tool theo vai trò nay nằm THẲNG trong `src.tools` (module `tools_lazy` đã
    xóa), nên có tác dụng với mọi người gọi chứ không chỉ ai import `src.graph` trước."""
    import src.tools as tools_mod

    tools_mod.clear_role_tools_cache()
    a = tools_mod.get_tools_for_role("electrical")
    b = tools_mod.get_tools_for_role("electrical")
    assert len(a) == len(b) and len(a) > 0
    assert tools_mod._ROLE_CACHE.get("electrical") is not None


def test_role_tools_cache_can_be_invalidated():
    """Cache phải có đường ra. Bản `tools_lazy` cũ chỉ có đường vào: thêm tool lúc chạy
    thì vai trò đã được hỏi trước đó mãi nhận danh sách cũ, im lặng không cảnh báo."""
    import src.tools as tools_mod

    tools_mod.clear_role_tools_cache()
    before = len(tools_mod.get_tools_for_role("electrical"))
    tools_mod.register_role_tool("electrical", tools_mod.read_cad)
    after = len(tools_mod.get_tools_for_role("electrical"))
    try:
        assert after == before + 1, "thêm tool lúc chạy phải thấy ngay ở lượt gọi sau"
    finally:
        tools_mod.TOOLS_BY_ROLE["electrical"].remove(tools_mod.read_cad)
        tools_mod.clear_role_tools_cache()


def test_role_tools_result_is_a_copy():
    """Người gọi sửa danh sách nhận được không được làm hỏng bản trong cache —
    `agents.build_tools_for_llm` có `append` thêm tool vào chính danh sách này."""
    import src.tools as tools_mod

    tools_mod.clear_role_tools_cache()
    first = tools_mod.get_tools_for_role("plumbing")
    n = len(first)
    first.append("rác")
    assert len(tools_mod.get_tools_for_role("plumbing")) == n


def test_embedding_backend_name_runs(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-dummy")
    monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
    from src.local_embeddings import embedding_backend_name
    assert embedding_backend_name() in ("openai", "ollama", "local", "sentence-transformers")
