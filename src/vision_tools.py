"""Vision tools — YOLO CAD symbol detection (Phase C: custom MEPF weights)."""
from __future__ import annotations

import logging
import os

from langchain_core.tools import tool

from src.workspace import resolve_safe_path

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

    # Đường dẫn do LLM đưa vào: phải quy về workspace của phiên và chặn path traversal,
    # giống mọi tool file khác — không được đọc thẳng đường dẫn tuyệt đối tùy ý.
    try:
        safe_path = resolve_safe_path(image_path)
    except ValueError as e:
        return f"Lỗi AI Vision: {e}"
    if not os.path.exists(safe_path):
        return f"Ảnh '{image_path}' không tồn tại trong thư mục làm việc."

    try:
        from src.config import settings
        conf = float(getattr(settings, "yolo_confidence", 0.25) or 0.25)
    except Exception:
        conf = 0.25

    try:
        results = model.predict(safe_path, save=False)
    except Exception as e:
        logger.error("YOLO predict failed: %s", e)
        return f"Lỗi AI Vision khi nhận diện: {e}"

    lines = [f"YOLO weights={_YOLO_WEIGHTS_LOADED} conf>={conf}"]
    total = 0
    for r in results:
        names = getattr(r, "names", None) or getattr(model, "names", {}) or {}
        boxes = getattr(r, "boxes", None)
        if not boxes:
            continue
        for box in boxes:
            cls_id = int(box.cls[0]) if box.cls is not None else -1
            score = float(box.conf[0]) if box.conf is not None else 0.0
            if score < conf:
                continue
            label = names.get(cls_id, str(cls_id))
            xyxy = getattr(box, "xyxy", None)
            bbox = f" bbox={[round(x, 1) for x in xyxy[0].tolist()]}" if xyxy is not None else ""
            lines.append(f"- {label} ({score:.2f}){bbox}")
            total += 1
    if total == 0:
        return f"Không tìm thấy thiết bị nào trên ngưỡng confidence {conf} trong '{image_path}'."
    lines.insert(1, f"Tổng: {total} detection(s)")
    return "\n".join(lines)
