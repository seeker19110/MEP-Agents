"""Ai là chủ của một task nền — chốt chặn "cái này có phải của anh không".

Xác thực (`src/api.py::require_api_key`) trả lời câu "anh là ai". Câu còn lại — "tài
nguyên này có phải của anh không" — trước đây **không có chỗ nào hỏi**: ai xác thực được
là tải được file BOQ của bất kỳ `task_id` nào. `task_id` là UUID nên khó đoán, nhưng "khó
đoán" không phải là kiểm soát truy cập; UUID lộ ra trong log, trong URL chia sẻ, trong ảnh
chụp màn hình.

Lưu ở Redis (dùng chung giữa nhiều tiến trình API/Worker) và rơi về bộ nhớ tiến trình khi
không có Redis, đúng nguyên tắc graceful fallback của dự án. Bản bộ nhớ **không** dùng
được cho nhiều tiến trình — có cảnh báo log rõ ràng, xem `ownership_backend()`.
"""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

#: Bản ghi chủ sở hữu sống bao lâu. Dài hơn hẳn vòng đời một task, đủ để người dùng quay
#: lại tải file sau vài ngày, nhưng không giữ mãi.
_TTL_SECONDS = int(os.environ.get("TASK_OWNER_TTL", str(7 * 24 * 3600)))

#: Danh tính khi hệ thống chạy không xác thực (dev cục bộ). Mọi người là cùng một người,
#: nên kiểm tra quyền sở hữu không có ý nghĩa và luôn cho qua.
ANONYMOUS = "anonymous"

#: Danh tính khi xác thực bằng khóa chung `MEP_AGENTS_API_KEY`. Ai có khóa cũng là cùng
#: một chủ thể — đây là giới hạn của khóa chung, không phải lỗi. Muốn tách người dùng
#: thật thì phải dùng JWT.
SHARED_KEY_IDENTITY = "shared-api-key"

_LOCK = threading.Lock()
_MEM: dict[str, tuple[float, str]] = {}


def _redis():
    try:
        import redis
        host = os.environ.get("REDIS_HOST", "localhost")
        port = int(os.environ.get("REDIS_PORT", "6379"))
        password = os.environ.get("REDIS_PASSWORD", "") or None
        client = redis.Redis(host=host, port=port, db=0, password=password,
                             socket_connect_timeout=1)
        client.ping()
        return client
    except Exception as e:
        logger.debug("Redis không khả dụng cho task owner: %s", e)
        return None


def ownership_backend() -> str:
    """'redis' hoặc 'memory'. Dùng để cảnh báo khi triển khai nhiều tiến trình."""
    return "redis" if _redis() is not None else "memory"


def _mem_prune() -> None:
    now = time.time()
    for k, (ts, _) in list(_MEM.items()):
        if now - ts > _TTL_SECONDS:
            _MEM.pop(k, None)


def set_owner(task_id: str, owner: str) -> None:
    """Ghi nhận chủ của task. Gọi NGAY khi tạo task, trước khi trả `task_id` cho client."""
    if not task_id:
        return
    owner = owner or ANONYMOUS
    client = _redis()
    if client is not None:
        try:
            client.setex(f"mep_task_owner:{task_id}", _TTL_SECONDS, owner)
            return
        except Exception as e:
            logger.warning("Không ghi được chủ sở hữu task vào Redis (%s) — dùng bộ nhớ", e)
    with _LOCK:
        _mem_prune()
        _MEM[task_id] = (time.time(), owner)


def get_owner(task_id: str) -> str | None:
    """Chủ của task, hoặc None nếu không có bản ghi."""
    if not task_id:
        return None
    client = _redis()
    if client is not None:
        try:
            raw = client.get(f"mep_task_owner:{task_id}")
            if raw is not None:
                return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        except Exception as e:
            logger.warning("Không đọc được chủ sở hữu task từ Redis (%s) — thử bộ nhớ", e)
    with _LOCK:
        _mem_prune()
        item = _MEM.get(task_id)
    return item[1] if item else None


def is_owner(task_id: str, identity: str) -> bool:
    """Người mang danh tính `identity` có được xem/tải task này không.

    Ba luật, theo thứ tự:

    1. **Chỉ có MỘT chủ thể trong hệ thống** → cho qua. Hai trường hợp: không bật xác
       thực (`ANONYMOUS`), và xác thực bằng khóa chung (`SHARED_KEY_IDENTITY`). Khóa
       chung theo định nghĩa là *một* danh tính dùng chung — ai có khóa cũng là cùng một
       chủ thể, nên so sánh chủ sở hữu ở đây **không thêm được chút an toàn nào** mà chỉ
       thêm một đường hỏng (bản ghi mất là chặn nhầm người dùng hợp lệ).

       **Hệ quả cần biết:** muốn tách người dùng thật thì phải dùng JWT và **không** phát
       khóa chung ra ngoài. `MEP_AGENTS_API_KEY` là khóa cấp quản trị: ai cầm nó đọc được
       task của mọi người, kể cả task của người dùng JWT. Đây là giới hạn của cơ chế khóa
       chung, không phải lỗi — nhưng phải nói rõ để không ai phát nó cho từng khách hàng
       rồi tưởng đã tách được dữ liệu.
    2. **Có bản ghi chủ sở hữu** → phải khớp.
    3. **Không có bản ghi** mà đang chạy danh tính riêng (JWT) → **TỪ CHỐI**. Đây là lựa
       chọn fail-closed có chủ ý: bản ghi mất (Redis khởi động lại, task tạo từ trước khi
       có tính năng này) thì từ chối một request hợp lệ vẫn hơn là mở lại đúng lỗ hổng
       cần bịt. Người dùng chỉ cần chạy lại phân tích; còn cho qua thì không ai biết là
       đã cho qua.
    """
    if identity in (ANONYMOUS, SHARED_KEY_IDENTITY):
        return True
    owner = get_owner(task_id)
    if owner is None:
        return False
    return owner == identity
