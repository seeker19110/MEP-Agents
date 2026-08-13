"""Điểm nối (middleware) cho supervisor — thay cho việc gán đè `agents.supervisor_node`.

Trước đây Phase B và Phase D nâng cấp điều phối bằng cách bọc rồi **gán đè** hàm
`agents.supervisor_node` lúc import. Cách đó có 3 chỗ mong manh:

1. Thứ tự import quyết định ai bọc ngoài ai — đọc code không thấy được, phải tự dựng lại
   trong đầu chuỗi import của `graph.py`.
2. Ai giữ tham chiếu hàm cũ (VD `from src.agents import supervisor_node` ở đầu file) sẽ
   dùng bản chưa bọc mà không có dấu hiệu gì. `graph.py` từng phải đọc lại
   `_agents_mod.supervisor_node` SAU các dòng import patch chỉ vì lý do này.
3. Không có cách nào biết đang có bao nhiêu lớp bọc, hay gỡ một lớp ra để kiểm thử.

Nay `agents.supervisor_node` là một hàm cố định, gọi qua chuỗi middleware đăng ký ở đây.
Mỗi middleware có dạng `fn(state, call_next) -> dict`: chặn sớm thì trả kết quả luôn,
muốn đi tiếp thì gọi `call_next(state)`. Ưu tiên **cao hơn nằm ngoài**, tức chạy trước.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
# name -> (priority, fn)
_MIDDLEWARE: dict[str, tuple[int, object]] = {}


def register_middleware(name: str, fn, priority: int = 0) -> None:
    """Đăng ký một lớp điều phối. `fn(state, call_next) -> dict`.

    Đăng ký lại cùng tên sẽ thay thế lớp cũ — nhờ vậy import module patch hai lần không
    tạo ra hai lớp chồng nhau (kiểu gán đè trước đây thì có).
    """
    with _LOCK:
        _MIDDLEWARE[name] = (priority, fn)
    logger.info("supervisor middleware đã đăng ký: %s (ưu tiên %s)", name, priority)


def unregister_middleware(name: str) -> None:
    with _LOCK:
        _MIDDLEWARE.pop(name, None)


def clear_middleware() -> None:
    with _LOCK:
        _MIDDLEWARE.clear()


def registered_middleware() -> list[str]:
    """Tên các lớp, từ ngoài vào trong — cũng chính là thứ tự chạy."""
    with _LOCK:
        items = sorted(_MIDDLEWARE.items(), key=lambda kv: kv[1][0], reverse=True)
    return [name for name, _ in items]


def run(state, core):
    """Chạy state qua chuỗi middleware rồi tới `core` (supervisor gốc).

    Middleware ném lỗi **không được làm sập cả luồng điều phối**: bỏ qua lớp đó kèm cảnh
    báo log và đi tiếp — mất một tính năng phụ vẫn hơn là treo cả phiên làm việc.
    """
    with _LOCK:
        ordered = sorted(_MIDDLEWARE.items(), key=lambda kv: kv[1][0])  # trong → ngoài

    handler = core
    for name, (_priority, fn) in ordered:
        handler = _wrap(name, fn, handler)
    return handler(state)


def _wrap(name: str, fn, call_next):
    def wrapped(state):
        try:
            return fn(state, call_next)
        except Exception as e:
            logger.warning("supervisor middleware '%s' lỗi (%s) — bỏ qua lớp này", name, e)
            return call_next(state)

    return wrapped
