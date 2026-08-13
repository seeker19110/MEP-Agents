"""Điểm mở rộng cho tra cứu tiêu chuẩn.

Trước đây Phase C (`vector_search_bind`) và Phase D (`agents_phase_d_patch`) nâng cấp
`search_standards` bằng cách **tráo chính đối tượng tool**: tạo tool mới rồi thay nó vào
`tools.search_standards`, `tools.tools`, `tools._COMMON_TOOLS` và từng danh sách trong
`tools.TOOLS_BY_ROLE`. Cách đó mong manh ở 3 điểm:

1. Ai giữ tham chiếu tới đối tượng tool cũ (danh sách đã sao chép, cache theo vai trò
   trong `tools_lazy`, ToolNode đã dựng xong) sẽ tiếp tục dùng bản cũ mà không có dấu
   hiệu gì — đúng lớp lỗi đã sinh ra sự cố XREF ở PR #32.
2. Thêm một chỗ chứa tool mới ở `tools.py` là phải nhớ sửa hàm `_swap` ở hai module patch.
3. Thứ tự import quyết định bản nào thắng.

Nay đối tượng tool **không bao giờ bị thay**. `tools.search_standards` giữ nguyên danh
tính và mỗi lần gọi mới hỏi module này xem đường tra cứu tốt nhất hiện có là gì. Phase
C/D chỉ cần đăng ký hàm của mình kèm mức ưu tiên.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
# name -> (priority, fn). Ưu tiên lớn hơn thắng; bằng nhau thì bản đăng ký sau thắng.
_BACKENDS: dict[str, tuple[int, object]] = {}


def register_backend(name: str, fn, priority: int = 0) -> None:
    """Đăng ký một đường tra cứu tiêu chuẩn. `fn(query: str) -> str`."""
    with _LOCK:
        _BACKENDS[name] = (priority, fn)
    logger.info("standards backend đã đăng ký: %s (ưu tiên %s)", name, priority)


def unregister_backend(name: str) -> None:
    with _LOCK:
        _BACKENDS.pop(name, None)


def clear_backends() -> None:
    with _LOCK:
        _BACKENDS.clear()


def registered_backends() -> list[str]:
    """Tên các backend, xếp từ ưu tiên cao xuống thấp."""
    with _LOCK:
        items = sorted(_BACKENDS.items(), key=lambda kv: kv[1][0], reverse=True)
    return [name for name, _ in items]


def active_backend() -> str | None:
    names = registered_backends()
    return names[0] if names else None


def run_search(query: str, fallback) -> str:
    """Chạy backend ưu tiên cao nhất; hỏng thì lùi dần xuống, cuối cùng về `fallback`.

    Backend hỏng không được làm hỏng cả lời gọi: tra cứu tiêu chuẩn luôn phải trả về
    một câu trả lời dùng được, kể cả khi không có API key hay index vector.
    """
    with _LOCK:
        ordered = sorted(_BACKENDS.items(), key=lambda kv: kv[1][0], reverse=True)
    for name, (_priority, fn) in ordered:
        try:
            result = fn(query)
        except Exception as e:
            logger.warning("standards backend '%s' lỗi (%s) — thử đường tiếp theo", name, e)
            continue
        if result:
            return result
        logger.debug("standards backend '%s' không có kết quả — thử đường tiếp theo", name)
    return fallback(query)
