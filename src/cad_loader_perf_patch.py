"""Route cad_loader.load_drawing through DXF cache."""
from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger(__name__)


def apply_cad_loader_perf_patch() -> None:
    import src.cad_loader as loader
    from src.cad_cache import readfile_cached, invalidate
    from src.workspace import resolve_safe_path

    if getattr(loader, "_perf_patched", False):
        return

    def load_drawing(file_path: str):
        safe_path = resolve_safe_path(file_path)
        notes = []
        if safe_path.lower().endswith(".dwg"):
            converted = os.path.splitext(safe_path)[0] + ".dxf"
            if os.path.exists(converted) and os.path.getmtime(converted) >= os.path.getmtime(safe_path):
                notes.append(f"Dùng lại bản .dxf đã chuyển đổi trước đó: {os.path.basename(converted)}")
            else:
                produced = loader.convert_dwg_to_dxf(safe_path, output_dir=os.path.dirname(safe_path))
                if os.path.abspath(produced) != os.path.abspath(converted):
                    shutil.move(produced, converted)
                notes.append(f"Đã tự chuyển .dwg sang .dxf: {os.path.basename(converted)}")
                invalidate(converted)
            safe_path = converted
        return readfile_cached(safe_path), notes

    loader.load_drawing = load_drawing
    _orig_resolve = loader.resolve_xref_segments

    def resolve_xref_segments(doc, base_dir: str, collect_segments_fn):
        import ezdxf
        _orig_read = ezdxf.readfile
        ezdxf.readfile = readfile_cached
        try:
            return _orig_resolve(doc, base_dir, collect_segments_fn)
        finally:
            ezdxf.readfile = _orig_read

    loader.resolve_xref_segments = resolve_xref_segments
    loader._perf_patched = True
    logger.info("cad_loader perf patch applied (DXF cache)")


apply_cad_loader_perf_patch()
