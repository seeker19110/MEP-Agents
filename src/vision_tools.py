import logging
import os
from langchain_core.tools import tool
from src.workspace import resolve_safe_path

logger = logging.getLogger(__name__)

# YOLO Model Cache
_YOLO_MODEL = None

def get_yolo_model():
    global _YOLO_MODEL
    if _YOLO_MODEL is None:
        try:
            from ultralytics import YOLO
            # Initialize a default YOLO11n model (nano) for performance
            _YOLO_MODEL = YOLO('yolo11n.pt')
        except ImportError:
            logger.error("Ultralytics YOLO is not installed.")
            return None
    return _YOLO_MODEL

@tool
def detect_cad_symbols_yolo(image_path: str) -> str:
    """[DỰ PHÒNG] Dùng Computer Vision (YOLO) để phát hiện đối tượng trên ẢNH bản vẽ (xuất
    bằng `render_cad_image`) khi `auto_quantity_takeoff`/`optimize_cad_drawing` không bóc
    được khối lượng đúng do bản vẽ "rác" (Block bị nổ, vẽ bằng Line rời rạc thay vì
    Block/Polyline nguyên vẹn — xem hàm hình học không đọc được các trường hợp này).

    LƯU Ý QUAN TRỌNG VỀ ĐỘ CHÍNH XÁC: model mặc định (`yolo11n.pt`) là model PRETRAINED
    trên bộ dữ liệu COCO (người/xe/đồ vật đời thường), CHƯA được huấn luyện riêng để nhận
    diện ký hiệu/thiết bị MEPF (van, đầu phun, tủ điện...). Vì vậy công cụ này hiện chỉ có
    giá trị tham khảo bổ sung (gợi ý còn vật gì trong ảnh, không rõ tên thiết bị MEPF thật),
    KHÔNG thay thế được kết quả bóc khối lượng bằng hình học. Muốn dùng làm nguồn chính cho
    BOQ, cần huấn luyện lại model bằng bộ ảnh ký hiệu MEPF đã gán nhãn (chưa có trong repo).

    Args:
        image_path: Đường dẫn tới file ảnh của bản vẽ (PNG/JPG do `render_cad_image` tạo ra).
    """
    model = get_yolo_model()
    if model is None:
        return "YOLO model not available. Please install ultralytics."
        
    safe_path = resolve_safe_path(image_path)
    if not os.path.exists(safe_path):
        return f"File ảnh không tồn tại: {safe_path}"
        
    try:
        results = model.predict(source=safe_path, save=False)
        detected_items = []
        for r in results:
            for box in r.boxes:
                class_id = int(box.cls[0])
                class_name = model.names[class_id]
                confidence = float(box.conf[0])
                detected_items.append(f"{class_name} ({confidence:.2f})")
                
        if not detected_items:
            return "Không tìm thấy thiết bị nào qua ảnh."
            
        return "AI Computer Vision phát hiện:\n" + "\n".join(detected_items)
    except Exception as e:
        return f"Lỗi AI Vision: {e}"
