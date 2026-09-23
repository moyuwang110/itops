"""登录 / 当前用户 / 退出。"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, revoke_token
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import BizError
from app.core.security import decode_access_token
from app.schemas.auth import LoginRequest, build_login_response

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


@router.post("/login", summary="管理员登录")
async def login(body: LoginRequest) -> dict[str, object]:
    ok_user = hmac.compare_digest(body.username, settings.admin_username)
    ok_pass = hmac.compare_digest(body.password, settings.admin_password)
    if not (ok_user and ok_pass):
        raise BizError("用户名或密码错误", code="login_failed", http_status=401)
    return build_login_response(body.username).model_dump()


@router.get("/me", summary="当前登录用户")
async def me(username: str = Depends(get_current_user)) -> dict[str, str]:
    return {"username": username}


@router.post("/logout", summary="退出登录")
async def logout(
    db: AsyncSession = Depends(get_db),
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    _username: str = Depends(get_current_user),
) -> dict[str, bool]:
    if cred is not None:
        try:
            payload = decode_access_token(cred.credentials)
            await revoke_token(db, payload.get("jti", ""), payload.get("exp"))
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True}
