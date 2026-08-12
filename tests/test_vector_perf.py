"""Vector query path: cache + bind."""
from __future__ import annotations


def test_embed_query_cache(monkeypatch):
    calls = {"n": 0}

    class FakeEmb:
        def embed_query(self, q):
            calls["n"] += 1
            return [0.1, 0.2, 0.3]

    import src.vectorstore as vs
    vs._cached_embed_query.cache_clear()
    monkeypatch.setattr(vs, "get_embeddings", lambda: FakeEmb())
    a = vs.embed_query_cached("sụt áp cáp")
    b = vs.embed_query_cached("sụt áp cáp")
    assert a == b
    assert calls["n"] == 1


def test_invalidate_store_cache():
    import src.vectorstore as vs
    vs._CACHED_STORE = object()
    vs._CACHED_KEY = "x"
    vs.invalidate_store_cache()
    assert vs._CACHED_STORE is None


def test_vector_search_bind_swaps_tool():
    import src.tools as tools_mod
    import src.vector_search_bind  # noqa: F401
    assert getattr(tools_mod, "_vector_search_patched", False) is True
    assert tools_mod.search_standards.name == "search_standards"
