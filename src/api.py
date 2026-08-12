import asyncio
import os
import uuid
import aiofiles
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from celery.result import AsyncResult
from src.celery_app import app as celery_app, parse_cad_to_db_task
# Import qua `src.tools` (không import trực tiếp `src.qs_tools`) để tránh vòng import:
# `qs_tools` import từ `tools` ở module-level, nên nếu tiến trình import `qs_tools`
# TRƯỚC khi `tools` từng được nạp, `tools` sẽ cố import ngược lại `qs_tools` khi nó
# còn dở dang -> ImportError. Nạp qua `tools` (điểm vào an toàn, tự xử lý đúng thứ tự)
# tránh được vòng lặp này.
from src.tools import build_revit_boq_excel
from src.workspace import get_project_root

app = FastAPI(
    title="MEP-Agents Cloud API",
    description="SaaS Backend for MEP-Agents Phase 3 (BIM & Cloud Era)",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(get_project_root(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Alias thay vì gọi `asyncio.sleep` trực tiếp trong `ws_task_status` — xem comment ở đó.
_WS_POLL_SLEEP = asyncio.sleep

class TaskResponse(BaseModel):
    task_id: str
    message: str

class RevitPayload(BaseModel):
    project_name: str
    elements: list[dict]
    wastage_percent: float = 5.0

class AutoCADPayload(BaseModel):
    project_name: str
    file_path: str


@app.get("/")
def root():
    return {"status": "ok", "message": "Welcome to MEP-Agents Cloud API v3.0"}

@app.post("/api/v1/takeoff", response_model=TaskResponse)
async def upload_and_takeoff(file: UploadFile = File(...)):
    """
    Nhận file CAD (.dwg/.dxf) từ Client (Web App), lưu trữ và đẩy vào hàng đợi Celery (Redis)
    để xử lý phân tán, trả về Task ID cho client theo dõi tiến độ (Real-time).
    """
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    
    async with aiofiles.open(file_path, "wb") as buffer:
        content = await file.read()
        await buffer.write(content)
        
    # Gửi sang Celery Queue (Distributed Processing)
    task = parse_cad_to_db_task.delay(file_path, user_id="web_client")
    
    return TaskResponse(
        task_id=task.id,
        message=f"File {file.filename} đã được đưa vào hàng đợi xử lý phân tán. Dùng task_id để theo dõi."
    )

def _task_status_payload(task_result: AsyncResult) -> dict:
    """Chuyển state Celery thành payload trạng thái cho client (dùng chung cho endpoint
    HTTP polling cũ và WebSocket real-time mới bên dưới).

    Trước đây `elif task_result.state != 'FAILURE'` coi MỌI state khác PENDING/FAILURE là
    'success' — hoạt động "đúng" chỉ vì trước giờ Celery task này không bao giờ phát ra
    state nào khác ngoài PENDING/SUCCESS/FAILURE. Từ khi `parse_cad_to_db_task` phát thêm
    state PROGRESS (xem `src/celery_app.py`), logic cũ sẽ báo "success" giả trong lúc tác
    vụ còn đang chạy. Ở đây so khớp state tường minh để không còn phụ thuộc ngầm định đó.
    """
    state = task_result.state
    if state == 'SUCCESS':
        return {
            "status": "success",
            "logs": ["Phân tích hoàn tất", "Bảng BOQ đã sẵn sàng."],
            "result": task_result.result,
        }
    if state == 'FAILURE':
        return {"status": "error", "logs": [str(task_result.info)]}
    if state == 'PROGRESS':
        meta = task_result.info if isinstance(task_result.info, dict) else {}
        return {"status": "Processing", "logs": meta.get("logs") or ["Đang xử lý..."]}
    # PENDING/STARTED/RETRY hoặc state tương lai khác: vẫn coi là đang xử lý.
    return {"status": "Processing", "logs": ["Đang khởi tạo Swarm...", "Mechanical: Đang phân tích ống gió..."]}


@app.get("/api/v1/task/{task_id}")
def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    return _task_status_payload(task_result)


@app.websocket("/ws/task/{task_id}")
async def ws_task_status(websocket: WebSocket, task_id: str):
    """Đẩy trạng thái tác vụ Celery real-time qua WebSocket thay vì để client tự polling
    HTTP mỗi 1.5s (xem `TECH_DEBT.md` mục 4). Server vẫn kiểm tra Redis/Celery backend theo
    chu kỳ ngắn ở phía trong (Celery result backend không có cơ chế push sẵn), nhưng CLIENT
    chỉ mở đúng 1 kết nối và chỉ nhận dữ liệu khi có thay đổi thật, thay vì tạo lại 1 HTTP
    request driver mỗi lần polling. Tự đóng kết nối khi tác vụ xong (success/error).
    """
    await websocket.accept()
    task_result = AsyncResult(task_id, app=celery_app)
    last_payload = None
    try:
        while True:
            payload = _task_status_payload(task_result)
            if payload != last_payload:
                await websocket.send_json(payload)
                last_payload = payload
            if payload["status"] in ("success", "error"):
                break
            # Alias riêng (thay vì gọi `asyncio.sleep` trực tiếp) để test có thể patch
            # đúng lệnh chờ của endpoint này mà không đụng tới `asyncio.sleep` toàn cục —
            # nhiều thứ khác trong ASGI stack (TestClient/anyio) cũng gọi `asyncio.sleep`
            # nội bộ để nhường CPU, nên patch toàn cục sẽ ảnh hưởng luôn cả những lệnh đó.
            await _WS_POLL_SLEEP(1.0)
    except WebSocketDisconnect:
        return
    await websocket.close()

@app.get("/api/v1/download/{task_id}")
def download_boq(task_id: str):
    # Trả về file Excel thật từ Celery result
    task_result = AsyncResult(task_id, app=celery_app)
    if task_result.state == 'SUCCESS':
        excel_path = task_result.result.get("excel_path")
        if excel_path and os.path.exists(excel_path):
            return FileResponse(excel_path, filename=f"Bao_Cao_BOQ_{task_id[:8]}.xlsx")
            
    return {"error": "File not found"}

@app.post("/api/v1/revit/analyze")
async def analyze_revit_model(payload: RevitPayload):
    """
    Nhận gói dữ liệu 3D JSON từ pyRevit Plugin và LẬP BOQ THẬT ngay (khối lượng ống/gió
    quy đổi mm -> m + hao hụt, phụ kiện/thiết bị đếm theo Cái) — dùng chung quy ước đơn
    vị/hao hụt với `auto_quantity_takeoff` (luồng AutoCAD) qua `build_revit_boq_excel`,
    để hai luồng cho ra kết quả tương đương, đối chiếu được trực tiếp, thay vì Revit chỉ
    đếm số cấu kiện như trước.
    """
    total_elements = len(payload.elements)
    ducts = sum(1 for el in payload.elements if "Duct" in el.get("category", ""))
    pipes = sum(1 for el in payload.elements if "Pipe" in el.get("category", ""))

    filename = f"BOQ_Revit_{uuid.uuid4().hex[:8]}.xlsx"
    excel_path = os.path.join(UPLOAD_DIR, filename)
    written_path = build_revit_boq_excel(payload.elements, excel_path,
                                          wastage_percent=payload.wastage_percent)

    message = f"Dự án: {payload.project_name}\n"
    message += f"Đã nhận {total_elements} cấu kiện.\n"
    message += f" - Ống gió: {ducts}\n"
    message += f" - Ống nước: {pipes}\n"
    if written_path:
        message += (f"\nĐã lập bảng khối lượng (BOQ) thật, đã cộng {payload.wastage_percent:.0f}% "
                     f"hao hụt vật tư. Tải về tại /api/v1/revit/download/{filename}")
        return {"status": "success", "message": message, "boq_filename": filename}

    message += "\nKhông có cấu kiện MEP nào có thể bóc khối lượng trong mô hình này."
    return {"status": "success", "message": message}


@app.get("/api/v1/revit/download/{filename}")
def download_revit_boq(filename: str):
    # `filename` do chính server sinh ra (uuid + đuôi cố định) ở analyze_revit_model,
    # nhưng vẫn chặn path traversal (../) và giới hạn vào đúng UPLOAD_DIR để an toàn.
    safe_name = os.path.basename(filename)
    excel_path = os.path.join(UPLOAD_DIR, safe_name)
    if not excel_path.startswith(UPLOAD_DIR) or not os.path.exists(excel_path):
        return {"error": "File not found"}
    return FileResponse(excel_path, filename=safe_name)

@app.post("/api/v1/autocad/analyze")
async def analyze_autocad_model(payload: AutoCADPayload):
    """
    Nhận đường dẫn file từ AutoCAD (via COM), đẩy vào hàng đợi phân tích bởi Agentic Swarm / Celery.
    """
    if not os.path.exists(payload.file_path):
        return {"status": "error", "message": f"Không tìm thấy file: {payload.file_path}"}
        
    task = parse_cad_to_db_task.delay(payload.file_path, user_id="cad_client")
    
    message = f"Dự án CAD: {payload.project_name}\n"
    message += f"Đã nhận lệnh từ AutoCAD. File: {payload.file_path}\n"
    message += f"Swarm AI đang xử lý khối lượng dưới nền. Task ID: {task.id}\n"
    message += "Vui lòng xem kết quả chi tiết trên Web!"
    
    return {"status": "success", "message": message, "task_id": task.id}
