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
    u = (getattr(s, "jwt_bootstrap_user", None) or os.environ.get("JWT_BOOTSTRAP_USER", "admin") or "admin").strip()
    p = (getattr(s, "jwt_bootstrap_password", None) or os.environ.get("JWT_BOOTSTRAP_PASSWORD", "") or "").strip()
    if not p:
        return False
    return hmac.compare_digest(username, u) and hmac.compare_digest(password, p)


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
        if not verify_bootstrap_user(body.username, body.password):
            raise HTTPException(status_code=401, detail="Sai username/password.")
        token = create_access_token(body.username, extra={"role": "admin"})
        return TokenResponse(access_token=token, expires_in=_expire_minutes() * 60)

    @router.get("/me", response_model=MeResponse)
    def me(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
        if not credentials or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Cần Bearer token.")
        claims = decode_access_token(credentials.credentials)
        return MeResponse(sub=str(claims.get("sub")), claims=claims)

    return router
