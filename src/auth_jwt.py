"""JWT authentication for FastAPI (Phase C).

Coexists with legacy `MEP_AGENTS_API_KEY`:
- If JWT_SECRET is set → Bearer JWT preferred; API key still accepted as fallback.
- If only API key → same as before.
- If neither → open (local dev).

Endpoints (mounted from api.py):
  POST /api/v1/auth/login  → {access_token, token_type, expires_in}
  GET  /api/v1/auth/me     → current user claims
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def _settings():
    from src.config import settings
    return settings


def jwt_enabled() -> bool:
    return bool(getattr(_settings(), "jwt_secret", "") or os.environ.get("JWT_SECRET", "").strip())


def _secret() -> str:
    s = getattr(_settings(), "jwt_secret", "") or os.environ.get("JWT_SECRET", "")
    return (s or "").strip()


def _algorithm() -> str:
    return getattr(_settings(), "jwt_algorithm", None) or os.environ.get("JWT_ALGORITHM", "HS256")


def _expire_minutes() -> int:
    try:
        return int(getattr(_settings(), "jwt_expire_minutes", 60 * 24) or 60 * 24)
    except Exception:
        return 60 * 24


def _b64url_encode(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    import base64
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _json_dumps(obj: Any) -> bytes:
    import json
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _json_loads(data: bytes) -> Any:
    import json
    return json.loads(data.decode("utf-8"))


def create_access_token(subject: str, *, extra: dict | None = None) -> str:
    """Create HS256 JWT without external dependency (PyJWT optional)."""
    secret = _secret()
    if not secret:
        raise RuntimeError("JWT_SECRET / settings.jwt_secret is not configured")

    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + _expire_minutes() * 60,
        "iss": "mep-agents",
    }
    if extra:
        payload.update(extra)

    try:
        import jwt as pyjwt  # type: ignore
        return pyjwt.encode(payload, secret, algorithm=_algorithm())
    except ImportError:
        header = _b64url_encode(_json_dumps({"alg": "HS256", "typ": "JWT"}))
        body = _b64url_encode(_json_dumps(payload))
        signing_input = f"{header}.{body}".encode("ascii")
        sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        return f"{header}.{body}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> dict[str, Any]:
    secret = _secret()
    if not secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="JWT not configured")

    try:
        import jwt as pyjwt  # type: ignore
        return pyjwt.decode(token, secret, algorithms=[_algorithm()], options={"require": ["exp", "sub"]})
    except ImportError:
        pass
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token không hợp lệ: {e}") from e

    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("JWT phải có 3 phần")
        header_b, body_b, sig_b = parts
        signing_input = f"{header_b}.{body_b}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_encode(expected), sig_b):
            raise ValueError("Chữ ký JWT sai")
        payload = _json_loads(_b64url_decode(body_b))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("Token đã hết hạn")
        if not payload.get("sub"):
            raise ValueError("Thiếu sub")
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token không hợp lệ: {e}") from e


def verify_bootstrap_user(username: str, password: str) -> bool:
    """Dev bootstrap: single user from settings/env. Not a full user DB."""
    s = _settings()
    # Biến môi trường đặt lúc chạy phải thắng giá trị nạp sẵn trong settings (từ .env
    # hoặc mặc định "admin"), nếu không thì đổi user bootstrap qua env sẽ im lặng vô tác dụng.
    u = (os.environ.get("JWT_BOOTSTRAP_USER", "") or getattr(s, "jwt_bootstrap_user", None) or "admin").strip()
    p = (os.environ.get("JWT_BOOTSTRAP_PASSWORD", "") or getattr(s, "jwt_bootstrap_password", None) or "").strip()
    if not p:
        return False
    return hmac.compare_digest(username, u) and hmac.compare_digest(password, p)


#: Vai trò gán cho tài khoản bootstrap. Nó là tài khoản duy nhất tồn tại khi CSDL còn
#: rỗng, nên phải đủ quyền tạo những người dùng đầu tiên.
BOOTSTRAP_ROLE = "admin"

#: `token_version` của tài khoản bootstrap. Cố định 0 và không bao giờ đổi — tài khoản này
#: không nằm trong CSDL nên không thu hồi token được. Đó là một lý do nữa để tạo người
#: dùng thật rồi bỏ hẳn `JWT_BOOTSTRAP_PASSWORD` khỏi cấu hình.
BOOTSTRAP_TOKEN_VERSION = 0


def authenticate(username: str, password: str) -> dict | None:
    """Xác thực theo CSDL người dùng, rơi về tài khoản bootstrap khi CSDL còn rỗng.

    Thứ tự CỐ Ý như sau:

    1. **CSDL đã có admin đang hoạt động** → chỉ CSDL nói lên sự thật. Tài khoản bootstrap
       bị bỏ qua hoàn toàn, kể cả khi biến môi trường vẫn còn đó. Nếu không, một biến môi
       trường sót lại từ thời dựng hệ thống sẽ mãi mãi là một cửa hậu quyền admin mà không
       ai thấy trong danh sách người dùng.
    2. **Chưa có admin nào** → dùng tài khoản bootstrap, để còn đường đăng nhập lần đầu mà
       tạo admin thật. Đây đúng là mục đích duy nhất của nó.

    Điều kiện là "có admin", KHÔNG phải "có người dùng" — nếu không thì tạo một `viewer`
    đầu tiên là tắt bootstrap và khóa cứng cả hệ thống. Kéo theo một hành vi khôi phục hợp
    lý: lỡ khóa/xóa hết admin thì bootstrap sống lại làm đường vào cứu hộ.

    Trả `{"username", "role", "token_version"}` hoặc None.
    """
    from src import users

    try:
        db_has_admin = users.has_admin_user()
    except Exception as e:
        # CSDL hỏng/không ghi được: KHÔNG âm thầm mở lại cửa bootstrap, vì như thế một sự
        # cố đĩa lại thành đường vào quyền admin. Từ chối và nói rõ trong log.
        logger.error("Không đọc được CSDL người dùng (%s) — từ chối đăng nhập.", e)
        return None

    # Người dùng trong CSDL luôn được thử trước, kể cả khi chưa có admin nào: một
    # `engineer` đã tạo phải đăng nhập được ngay, không phải chờ ai đó tạo admin.
    user = users.verify_password(username, password)
    if user:
        return user
    if db_has_admin:
        return None

    if verify_bootstrap_user(username, password):
        logger.warning(
            "Đăng nhập bằng tài khoản bootstrap '%s' — CSDL chưa có admin nào đang hoạt "
            "động. Hãy tạo admin thật rồi bỏ JWT_BOOTSTRAP_PASSWORD khỏi cấu hình.",
            username,
        )
        return {
            "username": username,
            "role": BOOTSTRAP_ROLE,
            "token_version": BOOTSTRAP_TOKEN_VERSION,
        }
    return None


def token_version_is_current(claims: dict[str, Any]) -> bool:
    """Token có còn hiệu lực sau các lần thu hồi không.

    Token mang `ver`; CSDL giữ `token_version` của người dùng. Thu hồi = tăng số trong
    CSDL, mọi token cũ lập tức lệch và bị từ chối.

    Ba trường hợp cho qua: người dùng không có trong CSDL (tài khoản bootstrap, hoặc CSDL
    còn rỗng), token cũ chưa có `ver` (phát trước khi có tính năng này), và số khớp.
    """
    from src import users

    subject = str(claims.get("sub") or "")
    if not subject:
        return False
    try:
        user = users.get_user(subject)
    except Exception as e:
        logger.warning("Không kiểm tra được phiên bản token của '%s': %s", subject, e)
        return True
    if user is None:
        return True
    if user.get("disabled"):
        return False
    if "ver" not in claims:
        return True
    try:
        return int(claims["ver"]) == int(user["token_version"])
    except (TypeError, ValueError):
        return False


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(BaseModel):
    sub: str
    claims: dict[str, Any]


def build_auth_router():
    """Create APIRouter with login/me endpoints."""
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.post("/login", response_model=TokenResponse)
    def login(body: LoginRequest):
        if not jwt_enabled():
            raise HTTPException(status_code=503, detail="JWT chưa bật (đặt JWT_SECRET).")

        user = authenticate(body.username, body.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Sai username/password.")
        token = create_access_token(
            user["username"],
            extra={"role": user["role"], "ver": user["token_version"]},
        )
        return TokenResponse(access_token=token, expires_in=_expire_minutes() * 60)

    @router.get("/me", response_model=MeResponse)
    def me(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
        if not credentials or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Cần Bearer token.")
        claims = decode_access_token(credentials.credentials)
        if not token_version_is_current(claims):
            raise HTTPException(status_code=401, detail="Token đã bị thu hồi. Hãy đăng nhập lại.")
        return MeResponse(sub=str(claims.get("sub")), claims=claims)

    @router.post("/change-password")
    def change_password(
        body: ChangePasswordRequest,
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ):
        """Tự đổi mật khẩu của chính mình. Thu hồi luôn token đang dùng.

        Người gọi sẽ phải đăng nhập lại ngay sau đó — kể cả trên thiết bị này. Đó là hành
        vi ĐÚNG: đổi mật khẩu vì nghi bị lộ mà phiên của kẻ kia vẫn chạy thì việc đổi
        chẳng có tác dụng gì.
        """
        from src import users

        if not credentials or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Cần Bearer token.")
        claims = decode_access_token(credentials.credentials)
        if not token_version_is_current(claims):
            raise HTTPException(status_code=401, detail="Token đã bị thu hồi. Hãy đăng nhập lại.")

        username = str(claims.get("sub") or "")
        if users.verify_password(username, body.old_password) is None:
            raise HTTPException(status_code=401, detail="Mật khẩu hiện tại không đúng.")
        try:
            users.set_password(username, body.new_password)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"status": "success",
                "message": "Đã đổi mật khẩu. Mọi phiên đăng nhập cũ đã bị thu hồi, hãy đăng nhập lại."}

    return router


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "engineer"


class UpdateUserRequest(BaseModel):
    role: str | None = None
    disabled: bool | None = None
    new_password: str | None = None


def build_admin_router(admin_dependency):
    """Router quản lý người dùng. `admin_dependency` do `src/api.py` truyền vào.

    Truyền dependency vào thay vì import ngược từ `src.api`: router này được gắn TỪ
    `api.py`, import ngược sẽ tạo vòng. Quan trọng hơn, nó khiến việc "route này cần quyền
    admin" nằm ở đúng chỗ người đọc `api.py` nhìn thấy.
    """
    from fastapi import APIRouter, Depends as FDepends

    router = APIRouter(prefix="/api/v1/admin/users", tags=["admin"])

    @router.get("")
    def list_all(_role: str = FDepends(admin_dependency)):
        from src import users
        return {"users": users.list_users()}

    @router.post("")
    def create(body: CreateUserRequest, _role: str = FDepends(admin_dependency)):
        from src import users
        try:
            return users.create_user(body.username, body.password, body.role)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.patch("/{username}")
    def update(username: str, body: UpdateUserRequest, _role: str = FDepends(admin_dependency)):
        from src import users
        try:
            if body.role is not None:
                users.set_role(username, body.role)
            if body.disabled is not None:
                users.set_disabled(username, body.disabled)
            if body.new_password is not None:
                users.set_password(username, body.new_password)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return users.get_user(username)

    @router.post("/{username}/revoke-tokens")
    def revoke(username: str, _role: str = FDepends(admin_dependency)):
        from src import users
        try:
            version = users.revoke_tokens(username)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return {"username": username, "token_version": version,
                "message": "Mọi token đã phát cho người này đã bị vô hiệu."}

    @router.delete("/{username}")
    def remove(username: str, _role: str = FDepends(admin_dependency)):
        from src import users
        try:
            users.delete_user(username)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return {"status": "success", "username": username}

    return router
