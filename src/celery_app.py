import os
from celery import Celery

# Khởi tạo Celery Application sử dụng Redis làm Broker và Backend
app = Celery(
    'mep_celery',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

app.conf.update(
    task_serializer='json',
    accept_content=['json', 'pickle'],
    result_serializer='json',
    timezone='Asia/Ho_Chi_Minh',
    enable_utc=True,
    worker_concurrency=4,  # Default concurrency, can be overridden by worker startup
)

@app.task(bind=True)
def parse_cad_to_db_task(self, dwg_path: str, user_id: str):
    """
    Task phân tán: Bóc tách bản vẽ CAD nặng chuyển lên database.
    Được gọi qua `parse_cad_to_db_task.delay(dwg_path, user_id)`
    """
    from src.tools import auto_quantity_takeoff
    from src.workspace import get_project_root

    # Ensure uploads dir exists
    upload_dir = os.path.join(get_project_root(), "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    # Set output excel path
    output_excel_path = os.path.join("data", "boq", f"boq_{os.path.basename(dwg_path)}.xlsx")
    os.makedirs(os.path.dirname(output_excel_path), exist_ok=True)

    # Báo tiến độ trước khi chạy phần nặng (auto_quantity_takeoff là 1 lệnh gọi đồng bộ,
    # không có hook tiến độ nội bộ, nên chỉ báo được ở mức "trước/sau" thay vì % thật).
    # Client (Web/WebSocket) đọc state PROGRESS này qua `_task_status_payload` trong
    # `src/api.py` thay vì chỉ thấy PENDING tĩnh suốt quá trình xử lý.
    # Best-effort: không có request/broker thật (VD chạy `.run()` trực tiếp trong test,
    # hoặc Redis backend tạm gián đoạn) thì bỏ qua thay vì làm hỏng cả tác vụ chính.
    try:
        self.update_state(state='PROGRESS', meta={
            "logs": [f"Đang đọc bản vẽ: {os.path.basename(dwg_path)}",
                     "Đang bóc khối lượng (Block/Layer)..."],
        })
    except Exception:
        pass

    # Invoke StructuredTool
    result_text = auto_quantity_takeoff.invoke({
        "file_path": dwg_path,
        "output_excel_path": output_excel_path
    })
    
    return {
        "status": "success", 
        "file": dwg_path, 
        "excel_path": output_excel_path,
        "logs": result_text
    }
