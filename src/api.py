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
# Nạp thẳng từ module định nghĩa. Trước đây phải đi vòng qua `src.tools` (nơi re-export)
# để né vòng import giữa `tools` và `qs_tools` — vòng đó nay đã được cắt bằng
# `src/mepf_spec.py`, xem TECH_DEBT.md mục 12.
from src.qs_tools import build_revit_boq_excel
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


def _jwt_enabled() -> bool:
    """JWT có được bật không. Gói trong try để thiếu module Phase C thì vẫn chạy được."""
    try:
        from src.auth_jwt import jwt_enabled
        return bool(jwt_enabled())
    except Exception:
        return False


def require_api_key(
    x_api_key: str = Header(default=""),
    api_key: str = "",
    authorization: str = Header(default=""),
):
    """Xác thực kép: `Authorization: Bearer <JWT>` HOẶC `X-API-Key` / `?api_key=`.

    Hàm này CỐ Ý nằm ngay trong `src/api.py` chứ không phải gắn thêm từ module Phase C.
    FastAPI chốt `Depends(require_api_key)` vào từng route ngay lúc định nghĩa route; gán
    đè `api.require_api_key` SAU đó (cách `src/api_phase_c_mount.py` từng làm) không đổi
    được route nào cả — các route vẫn giữ bản hàm cũ chỉ biết API key. Hậu quả thật: bật
    JWT mà không đặt `MEP_AGENTS_API_KEY` thì mọi endpoint mở toang cho khách nặc danh,
    trong khi đọc code lại tưởng đã có xác thực. Xem `docs/RA_SOAT_LO_HONG.md` mục 1.
    """
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if _jwt_enabled():
            from src.auth_jwt import decode_access_token
            decode_access_token(token)  # ném HTTPException 401 nếu token sai/hết hạn
            return

    if _API_KEY:
        if x_api_key == _API_KEY or api_key == _API_KEY:
            return
        raise HTTPException(
            status_code=401,
            detail="Thiếu hoặc sai xác thực (Bearer JWT hoặc X-API-Key / ?api_key=).",
        )

    # Không đặt API key nhưng có bật JWT => vẫn phải có Bearer hợp lệ, không được mở cửa.
    if _jwt_enabled():
        raise HTTPException(
            status_code=401,
            detail="Cần Authorization: Bearer <token> (hoặc đặt MEP_AGENTS_API_KEY).",
        )
    # Không đặt gì cả => mở như cũ (dev cục bộ), đúng triết lý graceful fallback.


def _ws_authorized(api_key: str = "", token: str = "") -> bool:
    """Cùng luật với `require_api_key`, nhưng trả bool vì WebSocket không dùng HTTPException."""
    if token and _jwt_enabled():
        try:
            from src.auth_jwt import decode_access_token
            decode_access_token(token)
            return True
        except Exception:
            return False
    if _API_KEY:
        return api_key == _API_KEY
    return not _jwt_enabled()


_SAFE_UPLOAD_EXTENSIONS = {".dwg", ".dxf"}


def _safe_upload_filename(raw_filename: str) -> str:
    base = os.path.basename(raw_filename or "")
    name, ext = os.path.splitext(base)
    ext = ext.lower()
    if ext not in _SAFE_UPLOAD_EXTENSIONS:
        ext = ".dxf"
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("._") or uuid.uuid4().hex[:8]
    return f"{name}{ext}"

def _strict_paths_enabled() -> bool:
    """Bật thì `/api/v1/autocad/analyze` chỉ nhận file NẰM TRONG workspace của server."""
    return os.environ.get("MEP_AGENTS_STRICT_PATHS", "").strip().lower() in ("1", "true", "yes")


def _validate_cad_path(file_path: str) -> tuple[bool, str]:
    """Kiểm tra đường dẫn bản vẽ do client (plugin AutoCAD) gửi lên.

    Endpoint này nhận đường dẫn TUYỆT ĐỐI trên máy chủ — thiết kế vốn dành cho kịch bản
    plugin và server chạy cùng máy. Khi server chạy tách biệt, đường dẫn tùy ý biến nó
    thành công cụ dò file: `os.path.exists` trả lời "có/không" cho mọi đường dẫn khách
    hàng đoán. Hai lớp chặn:

    1. LUÔN chặn: đuôi file phải là .dwg/.dxf — cắt hẳn việc dò đường dẫn ngoài CAD.
    2. `MEP_AGENTS_STRICT_PATHS=true`: buộc file nằm trong workspace của server. Mặc định
       TẮT để không phá kịch bản plugin cùng máy đang chạy được; triển khai nhiều người
       dùng thì PHẢI bật. Xem `docs/RA_SOAT_LO_HONG.md` mục 4.
    """
    ext = os.path.splitext(file_path or "")[1].lower()
    if ext not in _SAFE_UPLOAD_EXTENSIONS:
        return False, f"Chỉ nhận bản vẽ .dwg/.dxf, không nhận: {file_path}"
    if _strict_paths_enabled():
        from src.workspace import resolve_safe_path
        try:
            resolve_safe_path(file_path)
        except ValueError as e:
            return False, str(e)
    return True, ""


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
async def ws_task_status(websocket: WebSocket, task_id: str, api_key: str = "", token: str = ""):
    # WebSocket không đặt được header tùy ý khi mở từ trình duyệt, nên xác thực đi qua
    # query: `?api_key=` (khóa chung) hoặc `?token=` (JWT). Trước đây chỉ chấp nhận
    # `api_key`, nên khi hệ thống chạy chế độ JWT thì kênh WebSocket hoặc là mở toang
    # (không đặt API key) hoặc là không có cách nào vào được.
    if not _ws_authorized(api_key=api_key, token=token):
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
    ok, reason = _validate_cad_path(payload.file_path)
    if not ok:
        return {"status": "error", "message": reason}
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
