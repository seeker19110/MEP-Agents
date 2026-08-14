"""Gắn router đăng nhập JWT (Phase C) vào `src/api.py`.

`src/api.py` kết thúc bằng: `import src.api_phase_c_mount  # noqa: F401`

LỊCH SỬ — đọc trước khi định thêm việc cho file này:
module này TỪNG gán đè `api.require_api_key` bằng một bản có kiểm tra JWT. Việc đó
**không có tác dụng**: FastAPI đọc `Depends(require_api_key)` và chốt tham chiếu hàm vào
route ngay lúc định nghĩa route (lúc `src/api.py` chạy tới dòng `@app.post(...)`), tức là
TRƯỚC khi module này chạy. Gán lại thuộc tính module sau đó chỉ đổi cái tên, không đổi
route nào. Hậu quả thật: bật JWT mà không đặt `MEP_AGENTS_API_KEY` thì mọi endpoint mở
toang cho khách nặc danh, còn người đọc code lại thấy "đã có xác thực JWT".

Nay luật xác thực kép nằm thẳng trong `src/api.py::require_api_key`, module này chỉ còn
đúng một việc mà nó thật sự làm được: gắn thêm router `/api/v1/auth`. Đó cũng là ranh
giới nên giữ — thêm route thì được, đổi hành vi của route đã có thì phải sửa ngay trong
`src/api.py`.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_api_phase_c() -> None:
    import src.api as api_mod

    if getattr(api_mod, "_phase_c_auth_patched", False):
        return

    try:
        from src.auth_jwt import build_admin_router, build_auth_router
        api_mod.app.include_router(build_auth_router())
        # Router quản lý người dùng nhận dependency kiểm quyền admin từ `src/api.py`.
        # Truyền vào thay vì để `auth_jwt` import ngược `src.api` (vòng import), và để
        # người đọc `api.py` thấy được chính chỗ khai quyền.
        api_mod.app.include_router(build_admin_router(api_mod.require_admin))
        logger.info("Phase C JWT + admin router mounted")
    except Exception as e:
        logger.warning("JWT router not mounted: %s", e)

    api_mod._phase_c_auth_patched = True


apply_api_phase_c()
