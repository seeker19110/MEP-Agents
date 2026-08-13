"""Giới hạn tần suất gọi API theo danh tính người gọi.

Vì sao cần: mỗi lần gọi endpoint phân tích là một task nền đọc bản vẽ nặng **và** một
chuỗi lượt gọi LLM — tức là tốn CPU thật và tiền thật. Không có giới hạn nào thì một
script lặp (hoặc một plugin lỗi gọi trong vòng lặp) đủ để làm cạn cả hàng đợi Worker lẫn
hạn mức API của nhà cung cấp LLM, mà hóa đơn chỉ lộ ra vào cuối tháng.

Thuật toán: cửa sổ trượt đếm theo dấu thời gian, giữ trong bộ nhớ tiến trình.

**Giới hạn phải nói rõ:** bộ đếm nằm trong RAM của từng tiến trình. Chạy nhiều worker
uvicorn thì mỗi worker đếm riêng, nên hạn mức thực tế là `giới hạn × số worker`. Đây là
chốt chặn chống lạm dụng vô ý và chống script ngây thơ, **không phải** phòng thủ trước
tấn công từ chối dịch vụ có chủ đích — thứ đó cần bộ đếm dùng chung (Redis) hoặc chặn ở
tầng reverse proxy. Ghi rõ ở đây để không ai nhầm mức bảo vệ mình đang có.
"""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


def _limit() -> int:
    """Số request tối đa trong một cửa sổ. 0 hoặc âm = tắt hẳn."""
    try:
        return int(os.environ.get("RATE_LIMIT_REQUESTS", "60"))
    except ValueError:
        return 60


def _window() -> float:
    try:
        return float(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
    except ValueError:
        return 60.0


_LOCK = threading.Lock()
_HITS: dict[str, list[float]] = {}


def reset() -> None:
    """Xóa toàn bộ bộ đếm (dùng trong test)."""
    with _LOCK:
        _HITS.clear()


def check(identity: str, *, scope: str = "default") -> tuple[bool, int]:
    """Ghi nhận một lượt gọi. Trả `(được_phép, số_giây_chờ_nếu_bị_chặn)`.

    Đếm theo `identity` chứ không theo địa chỉ IP: nhiều người dùng có thể chung một IP
    (văn phòng sau NAT), và ngược lại một người có thể đổi IP. Danh tính là thứ hệ thống
    thật sự biết.
    """
    limit = _limit()
    if limit <= 0:
        return True, 0

    window = _window()
    key = f"{scope}:{identity}"
    now = time.monotonic()
    with _LOCK:
        hits = [t for t in _HITS.get(key, []) if now - t < window]
        if len(hits) >= limit:
            retry_after = max(1, int(window - (now - hits[0])) + 1)
            _HITS[key] = hits
            return False, retry_after
        hits.append(now)
        _HITS[key] = hits
        # Dọn các khóa đã nguội để bộ nhớ không phình theo số danh tính từng gặp.
        if len(_HITS) > 4096:
            for k in [k for k, v in _HITS.items() if not v or now - v[-1] > window]:
                _HITS.pop(k, None)
    return True, 0
