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
    import src.tools_lazy as tl
    tl.clear_role_tools_cache()
    a = tl.get_tools_for_role_cached("electrical")
    b = tl.get_tools_for_role_cached("electrical")
    assert len(a) == len(b) and len(a) > 0


def test_embedding_backend_name_runs(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-dummy")
    monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
    from src.local_embeddings import embedding_backend_name
    assert embedding_backend_name() in ("openai", "ollama", "local", "sentence-transformers")
