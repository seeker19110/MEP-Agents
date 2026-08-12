"""Global perf helpers."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def test_trim_messages_window():
    from src.perf_tuning import trim_messages_for_llm
    msgs = [HumanMessage(content=f"h{i}") for i in range(5)]
    msgs += [AIMessage(content="x" * 20000, name="QSAgent")]
    msgs += [ToolMessage(content="y" * 20000, tool_call_id="1")]
    msgs += [HumanMessage(content="final")]
    out = trim_messages_for_llm(msgs)
    assert any(isinstance(m, HumanMessage) and m.content == "final" for m in out)
    assert all(not (isinstance(getattr(m, "content", None), str) and len(m.content) > 12000) for m in out)


def test_cad_cache_hit(tmp_path):
    import ezdxf
    from src.cad_cache import readfile_cached, invalidate, cache_stats
    p = tmp_path / "a.dxf"
    doc = ezdxf.new()
    doc.saveas(str(p))
    invalidate()
    d1 = readfile_cached(str(p))
    d2 = readfile_cached(str(p))
    assert d1 is d2
    assert cache_stats()["entries"] >= 1


def test_unit_price_mem_cache():
    from src.unit_price_cache import mem_get, mem_set
    mem_set("k", {"a": 1})
    assert mem_get("k") == {"a": 1}
