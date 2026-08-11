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
    import os
    from src.tools import auto_quantity_takeoff
    from src.workspace import get_project_root

    # Ensure uploads dir exists
    upload_dir = os.path.join(get_project_root(), "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    # Set output excel path
    output_excel_path = os.path.join("data", "boq", f"boq_{os.path.basename(dwg_path)}.xlsx")
    os.makedirs(os.path.dirname(output_excel_path), exist_ok=True)
    
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
