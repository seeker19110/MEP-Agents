"""Batch CAD edit skills — Phase A: batch_edit_pipes."""
from __future__ import annotations

import json
import logging
import math
import os
from typing import Any

import ezdxf
from langchain_core.tools import tool

from src.cad_revision import create_snapshot
from src.workspace import resolve_safe_path

logger = logging.getLogger(__name__)


def _parse_ops(operations_json: str) -> list[dict[str, Any]]:
    data = json.loads(operations_json)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("operations_json phải là object {...} hoặc mảng [{...}, ...].")
    ops: list[dict[str, Any]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"operations[{i}] phải là object.")
        action = (item.get("action") or item.get("op") or "").strip().lower()
        if not action:
            raise ValueError(f"operations[{i}] thiếu 'action'.")
        ops.append({**item, "action": action})
    return ops


def _entity_endpoints(entity) -> list[tuple[float, float]]:
    dxftype = entity.dxftype()
    try:
        if dxftype == "LINE":
            s, e = entity.dxf.start, entity.dxf.end
            return [(s.x, s.y), (e.x, e.y)]
        if dxftype == "LWPOLYLINE":
            pts = list(entity.get_points(format="xy"))
            if not pts:
                return []
            if entity.closed and len(pts) > 1:
                return []
            return [pts[0], pts[-1]] if len(pts) >= 2 else pts
        if dxftype == "POLYLINE":
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
            if not pts:
                return []
            if entity.is_closed and len(pts) > 1:
                return []
            return [pts[0], pts[-1]] if len(pts) >= 2 else pts
        if dxftype == "ARC":
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            a0 = math.radians(entity.dxf.start_angle)
            a1 = math.radians(entity.dxf.end_angle)
            return [
                (cx + r * math.cos(a0), cy + r * math.sin(a0)),
                (cx + r * math.cos(a1), cy + r * math.sin(a1)),
            ]
    except Exception:
        return []
    return []


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _layer_matches(layer: str, filter_layers: list[str] | None) -> bool:
    if not filter_layers:
        return True
    layer_up = layer.upper()
    return any(layer_up == f.upper() or f.upper() in layer_up for f in filter_layers)


def _op_join_gaps(msp, doc, op: dict[str, Any]) -> dict[str, Any]:
    tolerance = float(op.get("tolerance", 50.0))
    layer_filter = op.get("layer_filter") or op.get("layers")
    if isinstance(layer_filter, str):
        layer_filter = [x.strip() for x in layer_filter.split(",") if x.strip()]
    endpoints: list[tuple[float, float, Any, int, str]] = []
    candidates = list(msp.query("LINE")) + list(msp.query("LWPOLYLINE")) + list(msp.query("ARC"))
    for ent in candidates:
        layer = ent.dxf.layer
        if not _layer_matches(layer, layer_filter):
            continue
        eps = _entity_endpoints(ent)
        for idx, (x, y) in enumerate(eps):
            endpoints.append((x, y, ent, idx, layer))
    used = set()
    joined = 0
    pairs: list[str] = []
    for i, (x1, y1, e1, idx1, layer1) in enumerate(endpoints):
        if i in used:
            continue
        best_j = None
        best_d = tolerance + 1
        for j in range(i + 1, len(endpoints)):
            if j in used:
                continue
            x2, y2, e2, idx2, layer2 = endpoints[j]
            if e1 is e2:
                continue
            d = _dist((x1, y1), (x2, y2))
            if 1e-6 < d <= tolerance and d < best_d:
                best_d = d
                best_j = j
        if best_j is not None:
            x2, y2, e2, idx2, layer2 = endpoints[best_j]
            msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer1})
            used.add(i)
            used.add(best_j)
            joined += 1
            pairs.append(f"{layer1}:({x1:.0f},{y1:.0f})-({x2:.0f},{y2:.0f}) d={best_d:.1f}")
    return {
        "action": "join_gap",
        "joined": joined,
        "tolerance": tolerance,
        "details": pairs[:20],
        "open_endpoints_scanned": len(endpoints),
    }


def _op_change_layer(msp, doc, op: dict[str, Any]) -> dict[str, Any]:
    from_layers = op.get("from_layers") or op.get("from_layer") or op.get("layer_filter")
    to_layer = (op.get("to_layer") or op.get("target_layer") or "").strip()
    if not to_layer:
        raise ValueError("change_layer cần 'to_layer'.")
    if isinstance(from_layers, str):
        from_layers = [x.strip() for x in from_layers.split(",") if x.strip()]
    if not from_layers:
        raise ValueError("change_layer cần 'from_layers' (list hoặc chuỗi phẩy).")
    if to_layer not in doc.layers:
        doc.layers.add(name=to_layer)
    moved = 0
    for ent in list(msp):
        if _layer_matches(ent.dxf.layer, from_layers):
            ent.dxf.layer = to_layer
            moved += 1
    return {
        "action": "change_layer",
        "from_layers": from_layers,
        "to_layer": to_layer,
        "moved": moved,
    }


def _op_change_linetype(msp, doc, op: dict[str, Any]) -> dict[str, Any]:
    layer_filter = op.get("layer_filter") or op.get("layers")
    linetype = (op.get("linetype") or op.get("to_linetype") or "CONTINUOUS").strip()
    if isinstance(layer_filter, str):
        layer_filter = [x.strip() for x in layer_filter.split(",") if x.strip()]
    changed = 0
    for ent in list(msp):
        if not _layer_matches(ent.dxf.layer, layer_filter):
            continue
        try:
            ent.dxf.linetype = linetype
            changed += 1
        except Exception:
            pass
    return {
        "action": "change_linetype",
        "linetype": linetype,
        "layer_filter": layer_filter,
        "changed": changed,
    }


def _op_offset_polyline(msp, doc, op: dict[str, Any]) -> dict[str, Any]:
    distance = float(op.get("distance", 0.0))
    if abs(distance) < 1e-9:
        return {"action": "offset", "offset_count": 0, "note": "distance=0, bỏ qua"}
    layer_filter = op.get("layer_filter") or op.get("layers")
    if isinstance(layer_filter, str):
        layer_filter = [x.strip() for x in layer_filter.split(",") if x.strip()]
    side = (op.get("side") or "left").lower()
    sign = 1.0 if side != "right" else -1.0
    offset_count = 0
    for ent in list(msp.query("LWPOLYLINE")):
        if not _layer_matches(ent.dxf.layer, layer_filter):
            continue
        try:
            pts = list(ent.get_points(format="xy"))
            if len(pts) < 2:
                continue
            new_pts = []
            for i, (x, y) in enumerate(pts):
                if i == 0:
                    dx, dy = pts[1][0] - x, pts[1][1] - y
                elif i == len(pts) - 1:
                    dx, dy = x - pts[i - 1][0], y - pts[i - 1][1]
                else:
                    dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
                length = math.hypot(dx, dy) or 1.0
                nx, ny = -dy / length, dx / length
                new_pts.append((x + sign * distance * nx, y + sign * distance * ny))
            msp.add_lwpolyline(new_pts, dxfattribs={"layer": ent.dxf.layer}, close=bool(ent.closed))
            offset_count += 1
        except Exception:
            continue
    return {
        "action": "offset",
        "distance": distance,
        "side": side,
        "offset_count": offset_count,
    }


_PIPE_OP_HANDLERS = {
    "join_gap": _op_join_gaps,
    "join_gaps": _op_join_gaps,
    "change_layer": _op_change_layer,
    "change_linetype": _op_change_linetype,
    "offset": _op_offset_polyline,
}


def apply_pipe_operations(doc, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    msp = doc.modelspace()
    results = []
    for op in operations:
        action = op["action"]
        handler = _PIPE_OP_HANDLERS.get(action)
        if not handler:
            results.append({"action": action, "error": f"action không hỗ trợ: {action}"})
            continue
        try:
            results.append(handler(msp, doc, op))
        except Exception as e:
            results.append({"action": action, "error": str(e)})
    return results


@tool
def batch_edit_pipes(
    file_path: str,
    operations_json: str,
    output_path: str = "",
) -> str:
    """Chỉnh sửa hàng loạt tuyến ống/dây trên bản vẽ CAD (.dxf) — deterministic, không cần LLM.

    operations_json là mảng các thao tác. Các action hỗ trợ:
    1) join_gap — nối đầu mút gần nhau bằng LINE mới
       {"action":"join_gap", "tolerance":50, "layer_filter":["P-PIPE-CW","M-SAD"]}
    2) change_layer — đổi layer hàng loạt
       {"action":"change_layer", "from_layers":["ONG_NUOC"], "to_layer":"P-PIPE-CW"}
    3) change_linetype — đổi linetype theo filter layer
       {"action":"change_linetype", "layer_filter":["M-SAD"], "linetype":"DASHED"}
    4) offset — offset LWPOLYLINE song song (đơn giản)
       {"action":"offset", "distance":200, "side":"left", "layer_filter":["M-SAD"]}

    Luôn snapshot revision trước khi ghi. Chỉ xử lý modelspace.
    """
    logger.info("batch_edit_pipes: %s", file_path)
    try:
        ops = _parse_ops(operations_json)
        if not ops:
            return "operations_json rỗng — không có thao tác nào để áp dụng."

        create_snapshot(file_path, note=f"Trước batch_edit_pipes ({len(ops)} ops)")
        safe_path = resolve_safe_path(file_path)
        if not os.path.exists(safe_path):
            return f"Lỗi: Không tìm thấy file {file_path}"

        doc = ezdxf.readfile(safe_path)
        results = apply_pipe_operations(doc, ops)

        target = output_path.strip() or file_path
        out_safe = resolve_safe_path(target)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)
        doc.saveas(out_safe)

        lines = [
            "BATCH EDIT PIPES THÀNH CÔNG (deterministic, không cần LLM):",
            f"- Số thao tác: {len(ops)}",
        ]
        for r in results:
            if "error" in r:
                lines.append(f"- LỖI [{r.get('action')}]: {r['error']}")
            elif r.get("action") in ("join_gap", "join_gaps"):
                lines.append(
                    f"- join_gap: nối {r.get('joined', 0)} cặp (tolerance={r.get('tolerance')}mm, "
                    f"quét {r.get('open_endpoints_scanned', 0)} đầu mút)"
                )
                for d in r.get("details") or []:
                    lines.append(f"  · {d}")
            elif r.get("action") == "change_layer":
                lines.append(
                    f"- change_layer: {r.get('from_layers')} → {r.get('to_layer')} "
                    f"({r.get('moved', 0)} đối tượng)"
                )
            elif r.get("action") == "change_linetype":
                lines.append(
                    f"- change_linetype: → {r.get('linetype')} ({r.get('changed', 0)} đối tượng)"
                )
            elif r.get("action") == "offset":
                lines.append(
                    f"- offset: distance={r.get('distance')} side={r.get('side')} "
                    f"({r.get('offset_count', 0)} polyline)"
                )
            else:
                lines.append(f"- {r}")
        lines.append(f"- Đã lưu tại: {target}")
        return "\n".join(lines)
    except json.JSONDecodeError as e:
        return f"Lỗi parse operations_json: {e}"
    except ValueError as e:
        return f"Lỗi operations_json: {e}"
    except Exception as e:
        return f"Lỗi batch_edit_pipes: {e}"
