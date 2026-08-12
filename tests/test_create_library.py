"""Sinh thư viện Block CAD chuẩn MEPF (src/create_library.py)."""
import os

import ezdxf
import pytest

from src.cad_standards import BLOCK_STANDARD
from src.create_library import _tag_with_standard_attributes, main


def test_tag_with_standard_attributes_adds_hidden_attdefs_for_known_block():
    doc = ezdxf.new()
    block = doc.blocks.new(name="DIFFUSER_SUPPLY")
    _tag_with_standard_attributes(block, "DIFFUSER_SUPPLY")

    tags = {a.dxf.tag: a.dxf.text for a in block.query("ATTDEF")}
    std = BLOCK_STANDARD["DIFFUSER_SUPPLY"]
    assert tags.get("MA_HIEU") == std["ma_hieu"]
    assert tags.get("MO_TA") == std["description"]


def test_tag_with_standard_attributes_noop_for_unknown_block():
    doc = ezdxf.new()
    block = doc.blocks.new(name="NOT_A_REAL_BLOCK_NAME")
    _tag_with_standard_attributes(block, "NOT_A_REAL_BLOCK_NAME")
    assert list(block.query("ATTDEF")) == []


def test_main_generates_library_file_with_all_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main()

    out_path = os.path.join(tmp_path, "data", "blocks", "mepf_library.dxf")
    assert os.path.exists(out_path)

    doc = ezdxf.readfile(out_path)
    expected_blocks = {
        "DIFFUSER_SUPPLY", "DIFFUSER_RETURN", "FCU", "LIGHT_PANEL",
        "LIGHT_DOWNLIGHT", "SOCKET", "SWITCH", "SPRINKLER", "PUMP",
    }
    block_names = {b.name for b in doc.blocks if not b.name.startswith("*")}
    assert expected_blocks.issubset(block_names)
