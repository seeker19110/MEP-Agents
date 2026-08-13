"""Global perf helpers."""
from __future__ import annotations

import pytest
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


def test_xref_resolution_survives_readfile_being_patched_to_the_cache(tmp_path):
    """Regression kép:

    1. Cache không được gọi ngược qua `ezdxf.readfile` ở nhánh miss — trước đây kết hợp
       với patch gán đè sẽ thành đệ quy vô hạn, xref bị bỏ khỏi khối lượng mà chỉ để lại
       một dòng note khó hiểu.
    2. Việc gộp xref KHÔNG được đụng vào biến toàn cục `ezdxf.readfile` — Phase D chạy
       song song bằng thread, gán đè là không an toàn (xem test thread bên dưới)."""
    import ezdxf
    from src import cad_cache, cad_loader

    cad_cache.invalidate()
    xref_file = tmp_path / "phu.dxf"
    xdoc = ezdxf.new()
    xdoc.modelspace().add_line((0, 0), (100, 0), dxfattribs={"layer": "PIPE"})
    xdoc.saveas(str(xref_file))

    doc = ezdxf.new()
    doc.blocks.new("REF1", dxfattribs={"flags": 4, "xref_path": "phu.dxf"})
    doc.modelspace().add_blockref("REF1", (500, 500))

    def collect(space):
        return [
            {"layer": e.dxf.layer, "start": (e.dxf.start.x, e.dxf.start.y, 0),
             "end": (e.dxf.end.x, e.dxf.end.y, 0), "length": 100.0, "is_arc": False}
            for e in space if e.dxftype() == "LINE"
        ]

    segments, notes = cad_loader.resolve_xref_segments(doc, str(tmp_path), collect)
    assert len(segments) == 1, notes
    assert segments[0]["start"] == pytest.approx((500, 500, 0))
    assert ezdxf.readfile is not cad_cache.readfile_cached  # không đụng biến toàn cục


def test_xref_resolution_never_mutates_global_readfile(tmp_path):
    """`resolve_xref_segments` từng gán đè `ezdxf.readfile` suốt lời gọi rồi khôi phục
    trong `finally`. Chạy nhiều luồng (Phase D fan-out, Celery worker) thì hai lời gọi
    chồng nhau khôi phục nhầm của nhau, khiến `ezdxf.readfile` kẹt vĩnh viễn ở bản cache —
    mọi chỗ đọc DXF sau đó nhận về cùng một doc dùng chung, ai sửa doc là hỏng dữ liệu của
    người khác.

    Test kiểm tra thẳng bất biến "không bao giờ đụng biến toàn cục", quan sát NGAY TRONG
    lúc lời gọi đang chạy. Kiểm bằng cách chạy đua nhiều luồng thì không chắc chắn — lỗi
    chỉ lộ khi các luồng gối nhau đúng nhịp."""
    import ezdxf
    from src import cad_cache, cad_loader

    cad_cache.invalidate()
    original_readfile = ezdxf.readfile

    xdoc = ezdxf.new()
    xdoc.modelspace().add_line((0, 0), (100, 0), dxfattribs={"layer": "PIPE"})
    xdoc.saveas(str(tmp_path / "phu.dxf"))

    doc = ezdxf.new()
    doc.blocks.new("REF1", dxfattribs={"flags": 4, "xref_path": "phu.dxf"})
    doc.modelspace().add_blockref("REF1", (0, 0))

    seen_inside = []

    def collect(space):
        seen_inside.append(ezdxf.readfile)
        return [
            {"layer": e.dxf.layer, "start": (e.dxf.start.x, e.dxf.start.y, 0),
             "end": (e.dxf.end.x, e.dxf.end.y, 0), "length": 100.0, "is_arc": False}
            for e in space if e.dxftype() == "LINE"
        ]

    segments, notes = cad_loader.resolve_xref_segments(doc, str(tmp_path), collect)

    assert len(segments) == 1, notes
    assert seen_inside, "collect_segments_fn chưa từng được gọi — test không kiểm được gì"
    assert all(f is original_readfile for f in seen_inside), (
        "ezdxf.readfile bị thay trong lúc gộp xref — không an toàn khi chạy nhiều luồng"
    )
    assert ezdxf.readfile is original_readfile
