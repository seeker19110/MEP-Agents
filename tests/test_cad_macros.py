"""Phase A macros: prepare_drawing smoke (offline, no LLM)."""
import ezdxf
import pytest

from src.workspace import resolve_safe_path, set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    return set_workspace_dir(str(tmp_path / "session_macros"))


def test_prepare_drawing_runs_pipeline(workspace):
    dxf = "dirty.dxf"
    doc = ezdxf.new("R2010", units=4)
    doc.layers.add("ONG_NUOC")
    msp = doc.modelspace()
    # zero-length junk
    msp.add_line((0, 0), (0, 0), dxfattribs={"layer": "ONG_NUOC"})
    msp.add_line((0, 0), (1000, 0), dxfattribs={"layer": "ONG_NUOC"})
    doc.saveas(resolve_safe_path(dxf))

    from src.cad_macros import prepare_drawing

    result = prepare_drawing.invoke(
        {
            "file_path": dxf,
            "run_audit": True,
            "run_optimize": True,
            "run_standardize": True,
        }
    )
    assert "PREPARE DRAWING" in result
    assert "HOÀN TẤT" in result or "OPTIMIZE" in result
