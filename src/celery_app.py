import os
from celery import Celery

# Trước đây hardcode "redis://localhost:6379/0" — chỉ đúng khi API/Worker/Redis chạy
# CÙNG một máy (dev cục bộ). Trong Docker Compose (xem docker-compose.yml), mỗi service
# có "localhost" RIÊNG của container mình, nên Worker sẽ không bao giờ kết nối được tới
# Redis chạy ở container khác — Celery âm thầm không nhận task nào (không lỗi rõ ràng ở
# đây, chỉ là task .delay() không bao giờ được xử lý). Đọc qua biến môi trường
# CELERY_BROKER_URL/CELERY_RESULT_BACKEND (docker-compose đặt thành redis://redis:6379/0
# — "redis" là tên service), không đặt gì thì vẫn rơi về localhost như cũ cho dev cục bộ.
_REDIS_URL = os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL") or "redis://localhost:6379/0"

# Khởi tạo Celery Application sử dụng Redis làm Broker và Backend
app = Celery(
    'mep_celery',
    broker=_REDIS_URL,
    backend=os.environ.get("CELERY_RESULT_BACKEND", _REDIS_URL),
)

app.conf.update(
    task_serializer='json',
    # CHỈ 'json'. Trước đây danh sách này có cả 'pickle': Celery sẽ unpickle bất cứ
    # message nào đẩy vào broker, mà unpickle dữ liệu không tin cậy là chạy code tùy ý
    # ngay trong Worker. Redis trong `docker-compose.yml` không đặt mật khẩu, nên ai vào
    # được mạng nội bộ của Compose là chiếm được Worker. Không chỗ nào trong dự án gửi
    # task bằng pickle (`task_serializer='json'`), nên bỏ đi không mất tính năng nào.
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Ho_Chi_Minh',
    enable_utc=True,
    worker_concurrency=4,  # Default concurrency, can be overridden by worker startup
)

def _publish_event(task, payload: dict) -> None:
    """Đẩy sự kiện tiến độ lên kênh Pub/Sub để WebSocket nhận ngay.

    Best-effort tuyệt đối: không có Redis, không có request thật (chạy `.run()` trong
    test), hay kênh gián đoạn đều bỏ qua trong im lặng — client vẫn nhận đúng trạng thái
    qua đường polling dự phòng, chỉ chậm hơn. Sự cố ở kênh phụ không được làm hỏng việc
    bóc khối lượng đang chạy.
    """
    try:
        task_id = getattr(getattr(task, "request", None), "id", None)
        if not task_id:
            return
        from src.task_events import publish
        publish(task_id, payload)
    except Exception:
        pass


@app.task(bind=True)
def parse_cad_to_db_task(self, dwg_path: str, user_id: str):
    """
    Task phân tán: Bóc tách bản vẽ CAD nặng chuyển lên database.
    Được gọi qua `parse_cad_to_db_task.delay(dwg_path, user_id)`
    """
    import shutil

    from src.tools import auto_quantity_takeoff
    from src.workspace import get_user_workspace, set_workspace_dir

    # Workspace RIÊNG từng người. Trước đây mọi người ghi chung vào `uploads/` và
    # `data/boq/`: bản vẽ và bảng khối lượng của khách này nằm cạnh khách kia, và hai
    # người tải lên hai file trùng tên là ghi đè nhau trong im lặng. Tham số `user_id` vốn
    # đã có trong chữ ký hàm nhưng bị bỏ đi không dùng.
    workspace = get_user_workspace(user_id)
    set_workspace_dir(workspace)

    # Đưa bản vẽ vào workspace của người dùng trước khi xử lý. Bắt buộc, không phải cho
    # gọn: mọi tool đọc file đều đi qua `resolve_safe_path`, mà file nằm ngoài workspace
    # sẽ bị chính hàm đó từ chối.
    source = os.path.abspath(dwg_path)
    local_name = os.path.basename(source)
    local_path = os.path.join(workspace, local_name)
    if source != os.path.abspath(local_path):
        try:
            shutil.copy2(source, local_path)
        except FileNotFoundError:
            _publish_event(self, {"status": "error", "logs": [f"Không tìm thấy file: {dwg_path}"]})
            raise

    boq_dir = os.path.join(workspace, "boq")
    os.makedirs(boq_dir, exist_ok=True)
    output_excel_path = os.path.join(boq_dir, f"boq_{local_name}.xlsx")

    # Báo tiến độ trước khi chạy phần nặng (auto_quantity_takeoff là 1 lệnh gọi đồng bộ,
    # không có hook tiến độ nội bộ, nên chỉ báo được ở mức "trước/sau" thay vì % thật).
    # Client (Web/WebSocket) đọc state PROGRESS này qua `_task_status_payload` trong
    # `src/api.py` thay vì chỉ thấy PENDING tĩnh suốt quá trình xử lý.
    # Best-effort: không có request/broker thật (VD chạy `.run()` trực tiếp trong test,
    # hoặc Redis backend tạm gián đoạn) thì bỏ qua thay vì làm hỏng cả tác vụ chính.
    progress_logs = [f"Đang đọc bản vẽ: {os.path.basename(dwg_path)}",
                     "Đang bóc khối lượng (Block/Layer)..."]
    try:
        self.update_state(state='PROGRESS', meta={"logs": progress_logs})
    except Exception:
        pass
    _publish_event(self, {"status": "Processing", "logs": progress_logs})

    # Invoke StructuredTool
    try:
        result_text = auto_quantity_takeoff.invoke({
            # Đọc bản SAO trong workspace, nhưng `result["file"]` bên dưới vẫn báo đúng
            # đường dẫn khách gửi lên — đó mới là thứ khách nhận ra, bản sao là chi tiết
            # nội bộ của Worker.
            "file_path": local_path,
            "output_excel_path": output_excel_path
        })
    except Exception as e:
        # Phát sự kiện lỗi TRƯỚC khi ném lại: nếu không, client đang nghe WebSocket sẽ
        # treo cho tới khi hết thời gian chờ thay vì biết ngay là task đã hỏng.
        _publish_event(self, {"status": "error", "logs": [str(e)]})
        raise

    result = {
        "status": "success",
        "file": dwg_path,
        "excel_path": output_excel_path,
        "logs": result_text
    }
    _publish_event(self, {"status": "success",
                          "logs": ["Phân tích hoàn tất", "Bảng BOQ đã sẵn sàng."],
                          "result": result})
    return result
