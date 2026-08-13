import asyncio
import logging
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

logger = logging.getLogger(__name__)

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
) -> str:
    """Xác thực kép: `Authorization: Bearer <JWT>` HOẶC `X-API-Key` / `?api_key=`.

    **Trả về danh tính** của người gọi (`sub` của JWT, hoặc `SHARED_KEY_IDENTITY` khi
    dùng khóa chung, hoặc `ANONYMOUS` khi không bật xác thực). Endpoint nào cần kiểm tra
    quyền sở hữu thì nhận giá trị này qua `identity: str = Depends(require_api_key)` thay
    vì khai trong `dependencies=[...]` (chỗ đó vứt giá trị trả về đi).

    Hàm này CỐ Ý nằm ngay trong `src/api.py` chứ không phải gắn thêm từ module Phase C.
    FastAPI chốt `Depends(require_api_key)` vào từng route ngay lúc định nghĩa route; gán
    đè `api.require_api_key` SAU đó (cách `src/api_phase_c_mount.py` từng làm) không đổi
    được route nào cả — các route vẫn giữ bản hàm cũ chỉ biết API key. Hậu quả thật: bật
    JWT mà không đặt `MEP_AGENTS_API_KEY` thì mọi endpoint mở toang cho khách nặc danh,
    trong khi đọc code lại tưởng đã có xác thực. Xem `docs/RA_SOAT_LO_HONG.md` mục 1.
    """
    from src.task_owner import ANONYMOUS, SHARED_KEY_IDENTITY

    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if _jwt_enabled():
            from src.auth_jwt import decode_access_token
            claims = decode_access_token(token)  # ném HTTPException 401 nếu token sai
            return str(claims.get("sub") or SHARED_KEY_IDENTITY)

    if _API_KEY:
        if x_api_key == _API_KEY or api_key == _API_KEY:
            return SHARED_KEY_IDENTITY
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
    return ANONYMOUS


def require_quota(identity: str = Depends(require_api_key)) -> str:
    """Xác thực + giới hạn tần suất. Dùng cho endpoint tạo việc nặng (đọc CAD, gọi LLM).

    Trả về danh tính y như `require_api_key` để endpoint dùng tiếp cho quyền sở hữu.
    """
    from src.rate_limit import check

    allowed, retry_after = check(identity, scope="write")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Gọi quá nhanh. Thử lại sau {retry_after} giây.",
            headers={"Retry-After": str(retry_after)},
        )
    return identity


def _require_task_owner(task_id: str, identity: str) -> None:
    """Chặn xem/tải task của người khác. Ném 403 nếu không phải chủ."""
    from src.task_owner import is_owner

    if not is_owner(task_id, identity):
        raise HTTPException(
            status_code=403,
            detail=("Task này không thuộc về bạn, hoặc hệ thống không còn bản ghi chủ sở "
                    "hữu của nó. Hãy chạy lại phân tích để nhận task_id mới."),
        )


def _ws_identity(api_key: str = "", token: str = "") -> str | None:
    """Danh tính của người mở WebSocket, hoặc None nếu không qua được xác thực.

    Cùng luật với `require_api_key`, nhưng trả giá trị thay vì ném HTTPException —
    WebSocket phải đóng kết nối bằng mã lỗi chứ không trả được HTTP status.
    """
    from src.task_owner import ANONYMOUS, SHARED_KEY_IDENTITY

    if token and _jwt_enabled():
        try:
            from src.auth_jwt import decode_access_token
            claims = decode_access_token(token)
            return str(claims.get("sub") or SHARED_KEY_IDENTITY)
        except Exception:
            return None
    if _API_KEY:
        return SHARED_KEY_IDENTITY if api_key == _API_KEY else None
    return None if _jwt_enabled() else ANONYMOUS


def _ws_authorized(api_key: str = "", token: str = "") -> bool:
    """Giữ lại cho chỗ nào chỉ cần biết có qua được xác thực hay không."""
    return _ws_identity(api_key=api_key, token=token) is not None


def _remember_owner(task_id: str, identity: str) -> None:
    """Ghi nhận chủ của task NGAY khi tạo, trước khi trả `task_id` cho client.

    Lỗi ở đây không được làm hỏng việc tạo task — nhưng cũng không được im lặng: mất bản
    ghi nghĩa là chủ thật sẽ bị chính hệ thống từ chối ở lượt tải file (fail-closed, xem
    `src/task_owner.py::is_owner`), nên phải có log để người vận hành hiểu vì sao.
    """
    try:
        from src.task_owner import set_owner
        set_owner(task_id, identity)
    except Exception as e:
        logger.warning("Không ghi được chủ sở hữu cho task %s: %s", task_id, e)


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


#: Dung lượng file upload lớn nhất. Bản vẽ DXF của một tòa nhà lớn hiếm khi quá vài trăm
#: MB; 200 MB là rộng rãi mà vẫn chặn được kịch bản làm cạn đĩa/RAM của máy chủ.
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "200")) * 1024 * 1024

#: Đọc theo khối 1 MB. Trước đây `await file.read()` nạp TOÀN BỘ file vào RAM rồi mới ghi
#: đĩa — một file 5 GB là một lần hết RAM của cả tiến trình API.
_UPLOAD_CHUNK = 1024 * 1024


async def _save_upload_streaming(file: UploadFile, dest_path: str) -> int:
    """Ghi file upload xuống đĩa theo từng khối, chặn khi vượt `MAX_UPLOAD_BYTES`.

    Vượt hạn mức thì **xóa phần đã ghi** rồi mới báo lỗi: để lại file dở dang vừa tốn đĩa
    vừa có thể bị tool đọc nhầm thành bản vẽ hỏng ở lượt sau.
    """
    total = 0
    try:
        async with aiofiles.open(dest_path, "wb") as buffer:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(f"File vượt quá hạn mức {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
                                f"Tăng bằng biến môi trường MAX_UPLOAD_MB nếu cần."),
                    )
                await buffer.write(chunk)
    except HTTPException:
        _remove_quietly(dest_path)
        raise
    except Exception:
        _remove_quietly(dest_path)
        raise
    return total


def _remove_quietly(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        logger.warning("Không xóa được file dở dang %s: %s", path, e)


_WS_POLL_SLEEP = asyncio.sleep

#: Thời gian chờ tối đa một sự kiện Pub/Sub trước khi kiểm tra lại trạng thái task. Không
#: phải chu kỳ polling: có sự kiện thì nhận ngay lập tức, con số này chỉ là lưới an toàn
#: cho trường hợp Worker chết giữa chừng mà không kịp phát sự kiện nào.
_WS_EVENT_TIMEOUT = 5.0

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
async def upload_and_takeoff(
    file: UploadFile = File(...),
    identity: str = Depends(require_quota),
):
    safe_filename = _safe_upload_filename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    await _save_upload_streaming(file, file_path)
    task = parse_cad_to_db_task.delay(file_path, user_id=identity)
    _remember_owner(task.id, identity)
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


@app.get("/api/v1/task/{task_id}")
def get_task_status(task_id: str, identity: str = Depends(require_api_key)):
    _require_task_owner(task_id, identity)
    task_result = AsyncResult(task_id, app=celery_app)
    return _task_status_payload(task_result)


@app.websocket("/ws/task/{task_id}")
async def ws_task_status(websocket: WebSocket, task_id: str, api_key: str = "", token: str = ""):
    # WebSocket không đặt được header tùy ý khi mở từ trình duyệt, nên xác thực đi qua
    # query: `?api_key=` (khóa chung) hoặc `?token=` (JWT). Trước đây chỉ chấp nhận
    # `api_key`, nên khi hệ thống chạy chế độ JWT thì kênh WebSocket hoặc là mở toang
    # (không đặt API key) hoặc là không có cách nào vào được.
    identity = _ws_identity(api_key=api_key, token=token)
    if identity is None:
        await websocket.close(code=1008)
        return
    # Kênh đẩy trạng thái cũng là một đường đọc dữ liệu task — phải kiểm quyền sở hữu
    # y như `/api/v1/task/{id}`, nếu không thì bịt cửa trước mà để ngỏ cửa sau.
    from src.task_owner import is_owner
    if not is_owner(task_id, identity):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    task_result = AsyncResult(task_id, app=celery_app)

    from src.task_events import get_message, subscribe

    pubsub = subscribe(task_id)
    last_payload = None
    try:
        # Luôn gửi trạng thái hiện tại trước: client mở kết nối MUỘN (task đã chạy được
        # một lúc, hoặc đã xong) sẽ không nhận được sự kiện nào nữa, và nếu chỉ ngồi chờ
        # kênh Pub/Sub thì sẽ treo vô hạn dù dữ liệu đã sẵn sàng.
        last_payload = _task_status_payload(task_result)
        await websocket.send_json(last_payload)

        while last_payload["status"] not in ("success", "error"):
            if pubsub is not None:
                # Có Redis: NGỦ trong lúc chờ sự kiện, không hỏi vòng quanh. Vẫn có
                # timeout để còn phát hiện client ngắt kết nối và để không phụ thuộc
                # hoàn toàn vào việc sự kiện chắc chắn tới (Worker có thể chết giữa chừng
                # mà không kịp phát sự kiện nào).
                payload = await asyncio.to_thread(get_message, pubsub, _WS_EVENT_TIMEOUT)
                if payload is None:
                    payload = _task_status_payload(task_result)
            else:
                # Không có Redis: quay về đường polling cũ. Mất tối ưu, không mất tính năng.
                await _WS_POLL_SLEEP(1.0)
                payload = _task_status_payload(task_result)

            if payload != last_payload:
                await websocket.send_json(payload)
                last_payload = payload
    except WebSocketDisconnect:
        return
    finally:
        if pubsub is not None:
            try:
                pubsub.close()
            except Exception as e:
                logger.debug("Không đóng được kênh sự kiện task %s: %s", task_id, e)
    await websocket.close()

@app.get("/api/v1/download/{task_id}")
def download_boq(task_id: str, identity: str = Depends(require_api_key)):
    _require_task_owner(task_id, identity)
    task_result = AsyncResult(task_id, app=celery_app)
    if task_result.state == 'SUCCESS':
        excel_path = task_result.result.get("excel_path")
        if excel_path and os.path.exists(excel_path):
            return FileResponse(excel_path, filename=f"Bao_Cao_BOQ_{task_id[:8]}.xlsx")
    return {"error": "File not found"}

@app.post("/api/v1/revit/analyze")
async def analyze_revit_model(payload: RevitPayload, identity: str = Depends(require_quota)):
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

@app.post("/api/v1/autocad/analyze")
async def analyze_autocad_model(payload: AutoCADPayload, identity: str = Depends(require_quota)):
    ok, reason = _validate_cad_path(payload.file_path)
    if not ok:
        return {"status": "error", "message": reason}
    if not os.path.exists(payload.file_path):
        return {"status": "error", "message": f"Không tìm thấy file: {payload.file_path}"}
    task = parse_cad_to_db_task.delay(payload.file_path, user_id=identity)
    _remember_owner(task.id, identity)
    message = f"Dự án CAD: {payload.project_name}\n"
    message += f"Đã nhận lệnh từ AutoCAD. File: {payload.file_path}\n"
    message += f"Swarm AI đang xử lý khối lượng dưới nền. Task ID: {task.id}\n"
    message += "Vui lòng xem kết quả chi tiết trên Web!"
    return {"status": "success", "message": message, "task_id": task.id}


# Phase C: dual JWT / API-key auth + /api/v1/auth routes
import src.api_phase_c_mount  # noqa: F401
