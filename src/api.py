import asyncio
import os
import re
import uuid
import aiofiles
from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from celery.result import AsyncResult
from src.celery_app import app as celery_app, parse_cad_to_db_task
from src.tools import build_revit_boq_excel
from src.workspace import get_project_root

app = FastAPI(
    title="MEP-Agents Cloud API",
    description="SaaS Backend for MEP-Agents Phase 3 (BIM & Cloud Era)",
    version="3.0.0"
)

_cors_origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
if _cors_origins_env:
    _CORS_ORIGINS = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    _CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(get_project_root(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_API_KEY = os.environ.get("MEP_AGENTS_API_KEY", "").strip()


def require_api_key(x_api_key: str = Header(default=""), api_key: str = ""):
    if _API_KEY and x_api_key != _API_KEY and api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai API Key (header X-API-Key hoặc query ?api_key=).")


_SAFE_UPLOAD_EXTENSIONS = {".dwg", ".dxf"}


def _safe_upload_filename(raw_filename: str) -> str:
    base = os.path.basename(raw_filename or "")
    name, ext = os.path.splitext(base)
    ext = ext.lower()
    if ext not in _SAFE_UPLOAD_EXTENSIONS:
        ext = ".dxf"
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("._") or uuid.uuid4().hex[:8]
    return f"{name}{ext}"

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

@app.post("/api/v1/takeoff", response_model=TaskResponse, dependencies=[Depends(require_api_key)])
async def upload_and_takeoff(file: UploadFile = File(...)):
    safe_filename = _safe_upload_filename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    async with aiofiles.open(file_path, "wb") as buffer:
        content = await file.read()
        await buffer.write(content)
    task = parse_cad_to_db_task.delay(file_path, user_id="web_client")
    return TaskResponse(
        task_id=task.id,
        message=f"File {file.filename} đã được đưa vào hàng đợi xử lý phân tán. Dùng task_id để theo dõi."
    )

def _task_status_payload(task_result: AsyncResult) -> dict:
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
    return {"status": "Processing", "logs": ["Đang khởi tạo Swarm...", "Mechanical: Đang phân tích ống gió..."]}


@app.get("/api/v1/task/{task_id}", dependencies=[Depends(require_api_key)])
def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    return _task_status_payload(task_result)


@app.websocket("/ws/task/{task_id}")
async def ws_task_status(websocket: WebSocket, task_id: str, api_key: str = ""):
    if _API_KEY and api_key != _API_KEY:
        await websocket.close(code=1008)
        return
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
            await _WS_POLL_SLEEP(1.0)
    except WebSocketDisconnect:
        return
    await websocket.close()

@app.get("/api/v1/download/{task_id}", dependencies=[Depends(require_api_key)])
def download_boq(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    if task_result.state == 'SUCCESS':
        excel_path = task_result.result.get("excel_path")
        if excel_path and os.path.exists(excel_path):
            return FileResponse(excel_path, filename=f"Bao_Cao_BOQ_{task_id[:8]}.xlsx")
    return {"error": "File not found"}

@app.post("/api/v1/revit/analyze", dependencies=[Depends(require_api_key)])
async def analyze_revit_model(payload: RevitPayload):
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


@app.get("/api/v1/revit/download/{filename}", dependencies=[Depends(require_api_key)])
def download_revit_boq(filename: str):
    safe_name = os.path.basename(filename)
    excel_path = os.path.join(UPLOAD_DIR, safe_name)
    if not excel_path.startswith(UPLOAD_DIR) or not os.path.exists(excel_path):
        return {"error": "File not found"}
    return FileResponse(excel_path, filename=safe_name)

@app.post("/api/v1/autocad/analyze", dependencies=[Depends(require_api_key)])
async def analyze_autocad_model(payload: AutoCADPayload):
    if not os.path.exists(payload.file_path):
        return {"status": "error", "message": f"Không tìm thấy file: {payload.file_path}"}
    task = parse_cad_to_db_task.delay(payload.file_path, user_id="cad_client")
    message = f"Dự án CAD: {payload.project_name}\n"
    message += f"Đã nhận lệnh từ AutoCAD. File: {payload.file_path}\n"
    message += f"Swarm AI đang xử lý khối lượng dưới nền. Task ID: {task.id}\n"
    message += "Vui lòng xem kết quả chi tiết trên Web!"
    return {"status": "success", "message": message, "task_id": task.id}


# Phase C: dual JWT / API-key auth + /api/v1/auth routes
import src.api_phase_c_mount  # noqa: F401
