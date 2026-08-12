"""Phase A: batch_edit_pipes / batch_replace_text / update_title_block."""
import os

import ezdxf
import pytest

from src.cad_batch_edit import (
    apply_pipe_operations,
    apply_text_replacements,
    batch_edit_pipes,
    batch_replace_text,
    update_title_block,
)
from src.workspace import resolve_safe_path, set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    return set_workspace_dir(str(tmp_path / "session_batch_edit"))


def _pipe_drawing(path: str, gap: float = 40.0):
    """Hai đoạn LINE cùng layer, đầu mút cách nhau `gap` mm."""
    doc = ezdxf.new("R2010", units=4)
    doc.layers.add("P-PIPE-CW")
    doc.layers.add("ONG_NUOC")
    msp = doc.modelspace()
    msp.add_line((0, 0), (1000, 0), dxfattribs={"layer": "P-PIPE-CW"})
    msp.add_line((1000 + gap, 0), (2000 + gap, 0), dxfattribs={"layer": "P-PIPE-CW"})
    msp.add_line((0, 500), (800, 500), dxfattribs={"layer": "ONG_NUOC"})
    msp.add_text("Ø110 uPVC", dxfattribs={"layer": "P-PIPE-CW", "height": 50}).set_placement((100, 50))
    msp.add_text("Ống gió 600x400", dxfattribs={"layer": "0", "height": 50}).set_placement((100, 600))
    doc.saveas(path)
    return doc


def test_join_gap_connects_nearby_endpoints(workspace):
    dxf = "pipes.dxf"
    _pipe_drawing(resolve_safe_path(dxf), gap=40.0)

    result = batch_edit_pipes.invoke(
        {
            "file_path": dxf,
            "operations_json": '[{"action":"join_gap","tolerance":50,"layer_filter":["P-PIPE-CW"]}]',
        }
    )
    assert "THÀNH CÔNG" in result
    assert "nối 1 cặp" in result or "join_gap: nối 1" in result

    out = ezdxf.readfile(resolve_safe_path(dxf))
    lines = list(out.modelspace().query("LINE"))
    # original 3 + 1 connector
    assert len(lines) == 4


def test_join_gap_respects_tolerance(workspace):
    dxf = "pipes.dxf"
    _pipe_drawing(resolve_safe_path(dxf), gap=200.0)

    result = batch_edit_pipes.invoke(
        {
            "file_path": dxf,
            "operations_json": '[{"action":"join_gap","tolerance":50}]',
        }
    )
    assert "nối 0 cặp" in result or "join_gap: nối 0" in result


def test_change_layer(workspace):
    dxf = "pipes.dxf"
    _pipe_drawing(resolve_safe_path(dxf))

    result = batch_edit_pipes.invoke(
        {
            "file_path": dxf,
            "operations_json": (
                '[{"action":"change_layer","from_layers":["ONG_NUOC"],"to_layer":"P-PIPE-CW"}]'
            ),
        }
    )
    assert "THÀNH CÔNG" in result
    out = ezdxf.readfile(resolve_safe_path(dxf))
    layers = {e.dxf.layer for e in out.modelspace().query("LINE")}
    assert "ONG_NUOC" not in layers
    assert "P-PIPE-CW" in layers


def test_batch_replace_text_simple(workspace):
    dxf = "pipes.dxf"
    _pipe_drawing(resolve_safe_path(dxf))

    result = batch_replace_text.invoke(
        {
            "file_path": dxf,
            "find": "Ø110",
            "replace": "DN100",
        }
    )
    assert "THÀNH CÔNG" in result
    assert "1" in result  # 1 chỗ

    out = ezdxf.readfile(resolve_safe_path(dxf))
    texts = []
    for e in out.modelspace().query("TEXT"):
        texts.append(e.dxf.text)
    assert any("DN100" in t for t in texts)
    assert not any("Ø110" in t for t in texts)


def test_batch_replace_text_dry_run_does_not_write(workspace):
    dxf = "pipes.dxf"
    _pipe_drawing(resolve_safe_path(dxf))

    result = batch_replace_text.invoke(
        {
            "file_path": dxf,
            "find": "Ø110",
            "replace": "DN100",
            "dry_run": True,
        }
    )
    assert "DRY-RUN" in result
    out = ezdxf.readfile(resolve_safe_path(dxf))
    texts = [e.dxf.text for e in out.modelspace().query("TEXT")]
    assert any("Ø110" in t for t in texts)


def test_batch_replace_text_regex(workspace):
    dxf = "pipes.dxf"
    _pipe_drawing(resolve_safe_path(dxf))

    result = batch_replace_text.invoke(
        {
            "file_path": dxf,
            "find": r"600x400",
            "replace": "800x500",
            "use_regex": True,
        }
    )
    assert "THÀNH CÔNG" in result
    out = ezdxf.readfile(resolve_safe_path(dxf))
    texts = [e.dxf.text for e in out.modelspace().query("TEXT")]
    assert any("800x500" in t for t in texts)


def test_update_title_block_fills_attributes(workspace):
    dxf = "title.dxf"
    doc = ezdxf.new("R2010", units=4)
    blk = doc.blocks.new("KHUNG_TEN")
    blk.add_attdef("TEN_CT", (0, 0), text="", dxfattribs={"height": 20})
    blk.add_attdef("TY_LE", (0, -30), text="", dxfattribs={"height": 20})
    blk.add_attdef("NGAY", (0, -60), text="", dxfattribs={"height": 20})
    ref = doc.modelspace().add_blockref("KHUNG_TEN", (0, 0))
    ref.add_auto_attribs({"TEN_CT": "", "TY_LE": "", "NGAY": ""})
    doc.saveas(resolve_safe_path(dxf))

    result = update_title_block.invoke(
        {
            "file_path": dxf,
            "attributes_json": '{"TEN_CT":"Chung cu ABC","TY_LE":"1:100","NGAY":"12/08/2026"}',
            "block_name": "KHUNG_TEN",
        }
    )
    assert "THÀNH CÔNG" in result

    out = ezdxf.readfile(resolve_safe_path(dxf))
    ins = list(out.modelspace().query('INSERT[name=="KHUNG_TEN"]'))[0]
    bag = {a.dxf.tag: a.dxf.text for a in ins.attribs}
    assert bag.get("TEN_CT") == "Chung cu ABC"
    assert bag.get("TY_LE") == "1:100"
    assert bag.get("NGAY") == "12/08/2026"


def test_apply_pipe_operations_unit_change_layer():
    doc = ezdxf.new()
    doc.layers.add("A")
    doc.layers.add("B")
    msp = doc.modelspace()
    msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "A"})
    results = apply_pipe_operations(
        doc,
        [{"action": "change_layer", "from_layers": ["A"], "to_layer": "B"}],
    )
    assert results[0]["moved"] == 1
    assert list(msp)[0].dxf.layer == "B"


def test_apply_text_replacements_unit():
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_text("Hello Ø110", dxfattribs={"height": 10}).set_placement((0, 0))
    stats = apply_text_replacements(doc, "Ø110", "DN100")
    assert stats["changed"] == 1
    assert "DN100" in list(msp.query("TEXT"))[0].dxf.text
