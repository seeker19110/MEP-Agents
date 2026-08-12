"""Mount Phase C JWT dual-auth into src.api.

`src/api.py` ends with: import src.api_phase_c_mount  # noqa: F401
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_api_phase_c() -> None:
    import src.api as api_mod
    from fastapi import Header, HTTPException

    if getattr(api_mod, "_phase_c_auth_patched", False):
        return

    _API_KEY = api_mod._API_KEY

    def require_api_key(
        x_api_key: str = Header(default=""),
        api_key: str = "",
        authorization: str = Header(default=""),
    ):
        if authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
            try:
                from src.auth_jwt import jwt_enabled, decode_access_token
                if jwt_enabled():
                    decode_access_token(token)
                    return
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=401, detail=f"JWT không hợp lệ: {e}") from e

        if _API_KEY:
            if x_api_key == _API_KEY or api_key == _API_KEY:
                return
            raise HTTPException(
                status_code=401,
                detail="Thiếu hoặc sai xác thực (Bearer JWT hoặc X-API-Key / ?api_key=).",
            )

        try:
            from src.auth_jwt import jwt_enabled
            if jwt_enabled() and not authorization:
                raise HTTPException(
                    status_code=401,
                    detail="Cần Authorization: Bearer <token> (hoặc X-API-Key).",
                )
        except HTTPException:
            raise
        except Exception:
            pass

    api_mod.require_api_key = require_api_key

    try:
        from src.auth_jwt import build_auth_router
        api_mod.app.include_router(build_auth_router())
        logger.info("Phase C JWT router mounted")
    except Exception as e:
        logger.warning("JWT router not mounted: %s", e)

    api_mod._phase_c_auth_patched = True


apply_api_phase_c()
