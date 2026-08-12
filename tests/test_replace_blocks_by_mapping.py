"""Thay Block hàng loạt theo bảng mapping (src/cad_block_replace.py)."""
import os

import ezdxf
import pytest

from src.cad_block_replace import (
    _parse_mapping,
    replace_blocks_by_mapping,
    replace_blocks_in_document,
)
from src.create_library import main as build_library
from src.workspace import get_project_root, resolve_safe_path, set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    return set_workspace_dir(str(tmp_path / "session_replace_blocks"))


def _make_drawing_with_old_blocks(path: str):
    doc = ezdxf.new("R2010", units=4)
    doc.layers.add("E-POWER")
    old = doc.blocks.new(name="O_CAM_CU")
    old.add_circle((0, 0), radius=40)
    old.add_attdef("TAG_CU", (0, -60), text="OCAM-01", dxfattribs={"height": 20})

    other = doc.blocks.new(name="DEN_LA")
    other.add_circle((0, 0), radius=80)

    msp = doc.modelspace()
    ref1 = msp.add_blockref(
        "O_CAM_CU",
        (100, 200),
        dxfattribs={"layer": "E-POWER", "xscale": 1.5, "yscale": 1.5, "rotation": 30},
    )
    ref1.add_auto_attribs({"TAG_CU": "OCAM-01"})

    ref2 = msp.add_blockref(
        "O_CAM_CU",
        (500, 200),
        dxfattribs={"layer": "E-POWER", "xscale": 1.0, "yscale": 1.0, "rotation": 0},
    )
    ref2.add_auto_attribs({"TAG_CU": "OCAM-02"})

    msp.add_blockref("DEN_LA", (0, 0), dxfattribs={"layer": "0"})
    doc.saveas(path)
    return doc


def test_parse_mapping_accepts_simple_dict():
    rules = _parse_mapping('{"O_CAM_CU": "SOCKET", "DEN_CU": "LIGHT_DOWNLIGHT"}')
    assert len(rules) == 2
    assert rules[0]["old_block"] == "O_CAM_CU"
    assert rules[0]["new_block"] == "SOCKET"
    assert rules[0]["keep_scale"] is True


def test_parse_mapping_accepts_detailed_list():
    payload = (
        '[{"old_block": "A", "new_block": "B", "keep_scale": false, '
        '"attribute_map": {"T1": "T2"}, "set_attributes": {"MA_HIEU": "X"}, '
        '"target_layer": "E-LIGHT"}]'
    )
    rules = _parse_mapping(payload)
    assert rules[0]["keep_scale"] is False
    assert rules[0]["attribute_map"] == {"T1": "T2"}
    assert rules[0]["set_attributes"] == {"MA_HIEU": "X"}
    assert rules[0]["target_layer"] == "E-LIGHT"


def test_parse_mapping_rejects_invalid_json_structure():
    with pytest.raises(ValueError):
        _parse_mapping('"not-an-object"')


def test_replace_simple_mapping_preserves_insert_transform(workspace):
    dxf_path = "ban_ve.dxf"
    _make_drawing_with_old_blocks(resolve_safe_path(dxf_path))

    # Tạo Block đích ngay trong bản vẽ (không phụ thuộc thư viện project).
    doc = ezdxf.readfile(resolve_safe_path(dxf_path))
    sock = doc.blocks.new(name="SOCKET")
    sock.add_circle((0, 0), radius=50)
    sock.add_attdef("TAG_CU", (0, -70), text="", dxfattribs={"height": 20})
    doc.saveas(resolve_safe_path(dxf_path))

    result = replace_blocks_by_mapping.invoke(
        {
            "file_path": dxf_path,
            "mapping_json": '{"O_CAM_CU": "SOCKET"}',
            "import_from_library": False,
        }
    )

    assert "THÀNH CÔNG" in result
    assert "O_CAM_CU -> SOCKET x2" in result

    out = ezdxf.readfile(resolve_safe_path(dxf_path))
    old_inserts = list(out.modelspace().query('INSERT[name=="O_CAM_CU"]'))
    new_inserts = list(out.modelspace().query('INSERT[name=="SOCKET"]'))
    assert old_inserts == []
    assert len(new_inserts) == 2

    # Vị trí + scale + rotation của instance đầu được giữ.
    first = sorted(new_inserts, key=lambda e: e.dxf.insert.x)[0]
    assert first.dxf.insert.x == pytest.approx(100)
    assert first.dxf.insert.y == pytest.approx(200)
    assert first.dxf.xscale == pytest.approx(1.5)
    assert first.dxf.yscale == pytest.approx(1.5)
    assert first.dxf.rotation == pytest.approx(30)

    # Block không nằm trong mapping không bị đụng.
    assert len(list(out.modelspace().query('INSERT[name=="DEN_LA"]'))) == 1


def test_replace_reports_missing_target_without_touching_source(workspace):
    dxf_path = "ban_ve.dxf"
    _make_drawing_with_old_blocks(resolve_safe_path(dxf_path))

    result = replace_blocks_by_mapping.invoke(
        {
            "file_path": dxf_path,
            "mapping_json": '{"O_CAM_CU": "BLOCK_KHONG_TON_TAI"}',
            "import_from_library": False,
        }
    )

    assert "CẦN REVIEW" in result
    assert "BLOCK_KHONG_TON_TAI" in result

    out = ezdxf.readfile(resolve_safe_path(dxf_path))
    assert len(list(out.modelspace().query('INSERT[name=="O_CAM_CU"]'))) == 2


def test_replace_can_write_to_separate_output(workspace):
    dxf_path = "goc.dxf"
    _make_drawing_with_old_blocks(resolve_safe_path(dxf_path))
    doc = ezdxf.readfile(resolve_safe_path(dxf_path))
    doc.blocks.new(name="SOCKET").add_circle((0, 0), radius=50)
    doc.saveas(resolve_safe_path(dxf_path))

    result = replace_blocks_by_mapping.invoke(
        {
            "file_path": dxf_path,
            "mapping_json": '{"O_CAM_CU": "SOCKET"}',
            "output_path": "da_thay.dxf",
            "import_from_library": False,
        }
    )
    assert "THÀNH CÔNG" in result
    assert os.path.exists(resolve_safe_path("da_thay.dxf"))

    original = ezdxf.readfile(resolve_safe_path(dxf_path))
    assert len(list(original.modelspace().query('INSERT[name=="O_CAM_CU"]'))) == 2


def test_replace_imports_from_library_when_available(workspace, tmp_path, monkeypatch):
    """Khi Block đích chưa có trong bản vẽ nhưng có trong mepf_library — tự import."""
    # build_library ghi vào get_project_root()/data/blocks — tạm thời trỏ project root
    # về tmp để không đụng thư viện thật của máy dev.
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.chdir(project_root)
    # workspace module cache _DEFAULT_WORKSPACE lúc import = cwd lúc nạp module.
    # get_project_root() trả _DEFAULT_WORKSPACE — cần monkeypatch trực tiếp.
    monkeypatch.setattr("src.cad_block_replace.get_project_root", lambda: str(project_root))
    monkeypatch.setattr("src.workspace.get_project_root", lambda: str(project_root))

    build_library()
    library = project_root / "data" / "blocks" / "mepf_library.dxf"
    assert library.exists()

    set_workspace_dir(str(tmp_path / "ws"))
    dxf_path = "ban_ve.dxf"
    doc = ezdxf.new("R2010", units=4)
    doc.blocks.new(name="O_CAM_CU").add_circle((0, 0), radius=40)
    doc.modelspace().add_blockref("O_CAM_CU", (10, 20))
    doc.saveas(resolve_safe_path(dxf_path))

    result = replace_blocks_by_mapping.invoke(
        {
            "file_path": dxf_path,
            "mapping_json": '{"O_CAM_CU": "SOCKET"}',
            "import_from_library": True,
        }
    )

    assert "THÀNH CÔNG" in result
    assert "SOCKET" in result
    out = ezdxf.readfile(resolve_safe_path(dxf_path))
    assert "SOCKET" in out.blocks
    assert len(list(out.modelspace().query('INSERT[name=="SOCKET"]'))) == 1


def test_replace_with_attribute_map_and_set_attributes(workspace):
    dxf_path = "ban_ve.dxf"
    _make_drawing_with_old_blocks(resolve_safe_path(dxf_path))
    doc = ezdxf.readfile(resolve_safe_path(dxf_path))
    sock = doc.blocks.new(name="SOCKET")
    sock.add_circle((0, 0), radius=50)
    sock.add_attdef("MA_HIEU", (0, -70), text="", dxfattribs={"height": 20})
    sock.add_attdef("TAG_CU", (0, -100), text="", dxfattribs={"height": 20})
    doc.saveas(resolve_safe_path(dxf_path))

    mapping = (
        '[{"old_block": "O_CAM_CU", "new_block": "SOCKET", '
        '"attribute_map": {"TAG_CU": "TAG_CU"}, '
        '"set_attributes": {"MA_HIEU": "E-SOCKET"}}]'
    )
    result = replace_blocks_by_mapping.invoke(
        {
            "file_path": dxf_path,
            "mapping_json": mapping,
            "import_from_library": False,
        }
    )
    assert "THÀNH CÔNG" in result

    out = ezdxf.readfile(resolve_safe_path(dxf_path))
    inserts = list(out.modelspace().query('INSERT[name=="SOCKET"]'))
    assert len(inserts) == 2
    # Ít nhất một instance mang MA_HIEU đã set.
    attrib_bags = []
    for ins in inserts:
        bag = {}
        if hasattr(ins, "attribs") and ins.attribs:
            for a in ins.attribs:
                bag[a.dxf.tag] = a.dxf.text
        attrib_bags.append(bag)
    assert any(b.get("MA_HIEU") == "E-SOCKET" for b in attrib_bags)


def test_replace_blocks_in_document_unit_keeps_unmapped_blocks():
    doc = ezdxf.new()
    doc.blocks.new(name="OLD").add_line((0, 0), (1, 0))
    doc.blocks.new(name="NEW").add_line((0, 0), (2, 0))
    doc.blocks.new(name="OTHER").add_line((0, 0), (3, 0))
    msp = doc.modelspace()
    msp.add_blockref("OLD", (0, 0))
    msp.add_blockref("OTHER", (5, 0))

    stats = replace_blocks_in_document(
        doc,
        [{"old_block": "OLD", "new_block": "NEW", "keep_scale": True, "keep_rotation": True,
          "attribute_map": {}, "set_attributes": {}}],
    )
    assert stats["total_replaced"] == 1
    assert len(list(msp.query('INSERT[name=="OTHER"]'))) == 1
    assert len(list(msp.query('INSERT[name=="NEW"]'))) == 1
