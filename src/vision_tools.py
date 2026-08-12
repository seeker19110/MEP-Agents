"""Vision tools — YOLO CAD symbol detection (Phase C: custom MEPF weights)."""
from __future__ import annotations

import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_YOLO_MODEL = None
_YOLO_WEIGHTS_LOADED = None


def get_yolo_model():
    global _YOLO_MODEL, _YOLO_WEIGHTS_LOADED
    try:
        from src.yolo_mepf import resolve_weights_path
        from src.config import settings
        weights = resolve_weights_path(getattr(settings, "yolo_weights", "") or "")
    except Exception:
        weights = os.environ.get("YOLO_WEIGHTS", "").strip() or "yolo11n.pt"

    if _YOLO_MODEL is not None and _YOLO_WEIGHTS_LOADED == weights:
        return _YOLO_MODEL
    try:
        from ultralytics import YOLO
        _YOLO_MODEL = YOLO(weights)
        _YOLO_WEIGHTS_LOADED = weights
        logger.info("YOLO loaded: %s", weights)
    except Exception as e:
        logger.error("Cannot load YOLO (%s)", e)
        _YOLO_MODEL = None
        _YOLO_WEIGHTS_LOADED = None
    return _YOLO_MODEL


@tool
def detect_cad_symbols_yolo(image_path: str) -> str:
    """[DỰ PHÒNG] YOLO trên ảnh bản vẽ. Đặt YOLO_WEIGHTS=best.pt sau fine-tune MEPF."""
    model = get_yolo_model()
    if model is None:
        return "YOLO model not available. Please install ultralytics."
    if not os.path.exists(image_path):
        return f"Không tìm thấy ảnh: {image_path}"
    try:
        from src.config import settings
        conf = float(getattr(settings, "yolo_confidence", 0.25) or 0.25)
    except Exception:
        conf = 0.25
    results = model.predict(image_path, conf=conf, verbose=False)
    lines = [f"YOLO weights={_YOLO_WEIGHTS_LOADED} conf>={conf}"]
    total = 0
    for r in results:
        names = r.names or {}
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls[0]) if box.cls is not None else -1
            score = float(box.conf[0]) if box.conf is not None else 0.0
            label = names.get(cls_id, str(cls_id))
            xyxy = box.xyxy[0].tolist() if box.xyxy is not None else []
            lines.append(f"- {label}: {score:.2f} bbox={[round(x, 1) for x in xyxy]}")
            total += 1
    if total == 0:
        lines.append("Không phát hiện đối tượng nào trên ngưỡng confidence.")
    else:
        lines.insert(1, f"Tổng: {total} detection(s)")
    return "\n".join(lines)
