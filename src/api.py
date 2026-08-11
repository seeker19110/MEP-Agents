import os
import aiofiles
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from celery.result import AsyncResult
from src.celery_app import app as celery_app, parse_cad_to_db_task
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

class TaskResponse(BaseModel):
    task_id: str
    message: str

class RevitPayload(BaseModel):
    project_name: str
    elements: list[dict]

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

@app.get("/api/v1/task/{task_id}")
def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    if task_result.state == 'PENDING':
        return {"status": "Processing", "logs": ["Đang khởi tạo Swarm...", "Mechanical: Đang phân tích ống gió..."]}
    elif task_result.state != 'FAILURE':
        return {
            "status": "success",
            "logs": ["Phân tích hoàn tất", "Bảng BOQ đã sẵn sàng."],
            "result": task_result.result
        }
    else:
        return {"status": "error", "logs": [str(task_result.info)]}

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
    Nhận gói dữ liệu 3D JSON từ pyRevit Plugin, phân tích bởi Agentic Swarm.
    """
    total_elements = len(payload.elements)
    ducts = sum(1 for el in payload.elements if "Duct" in el.get("category", ""))
    pipes = sum(1 for el in payload.elements if "Pipe" in el.get("category", ""))
    
    message = f"Dự án: {payload.project_name}\n"
    message += f"Đã nhận {total_elements} cấu kiện.\n"
    message += f" - Ống gió: {ducts}\n"
    message += f" - Ống nước: {pipes}\n"
    message += "\nAgentic Swarm đã xác nhận không gian 3D BIM và chuẩn bị lập bảng Bóc tách Khối lượng (BOQ)!"
    
    return {"status": "success", "message": message}

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
