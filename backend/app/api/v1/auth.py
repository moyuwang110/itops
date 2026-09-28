"""登录 / 当前用户 / 退出 / 资料与密码修改。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TOKEN_COOKIE, get_current_user, revoke_token
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import BizError
from app.core.rate_limit import login_limiter
from app.core.security import decode_access_token
from app.schemas.auth import LoginRequest, build_login_response
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", summary="管理员登录")
async def login(body: LoginRequest, request: Request, response: Response,
                db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    ip = _client_ip(request)
    allowed, _ = login_limiter.is_allowed(ip)
    if not allowed:
        raise BizError("登录尝试过于频繁，请稍后再试", code="rate_limited",
                       http_status=429)
    user = await auth_service.verify_user_credentials(db, body.username, body.password)
    if user is None:
        raise BizError("用户名或密码错误", code="login_failed", http_status=401)
    result = build_login_response(user.username, user.avatar)
    response.set_cookie(
        key=TOKEN_COOKIE,
        value=result.access_token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return result.model_dump()


@router.get("/me", summary="当前登录用户")
async def me(username: str = Depends(get_current_user),
             db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    user = await auth_service.get_user_by_username(db, username)
    if user is None:
        raise BizError("用户不存在", code="not_found", http_status=404)
    return {"id": user.id, "username": user.username, "avatar": user.avatar}


class ProfileUpdate(BaseModel):
    username: str | None = Field(None, min_length=1, max_length=64)
    avatar: str | None = None


@router.put("/profile", summary="修改用户名/头像")
async def update_profile(
    body: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    username: str = Depends(get_current_user),
) -> dict[str, object]:
    user = await auth_service.get_user_by_username(db, username)
    if user is None:
        raise BizError("用户不存在", code="not_found", http_status=404)
    try:
        user = await auth_service.update_profile(db, user, body.username, body.avatar)
    except ValueError as exc:
        raise BizError(str(exc), code="invalid", http_status=400) from exc
    return {"id": user.id, "username": user.username, "avatar": user.avatar}


class PasswordChange(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


@router.put("/password", summary="修改密码")
async def change_password(
    body: PasswordChange,
    db: AsyncSession = Depends(get_db),
    username: str = Depends(get_current_user),
) -> dict[str, bool]:
    user = await auth_service.get_user_by_username(db, username)
    if user is None:
        raise BizError("用户不存在", code="not_found", http_status=404)
    try:
        await auth_service.change_password(db, user, body.old_password, body.new_password)
    except ValueError as exc:
        raise BizError(str(exc), code="invalid", http_status=400) from exc
    return {"ok": True}


@router.post("/logout", summary="退出登录")
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    _username: str = Depends(get_current_user),
) -> dict[str, bool]:
    token = request.cookies.get(TOKEN_COOKIE) or (cred.credentials if cred else None)
    if token:
        try:
            payload = decode_access_token(token)
            await revoke_token(db, payload.get("jti", ""), payload.get("exp"))
        except Exception:  # noqa: BLE001
            pass
    response.delete_cookie(
        key=TOKEN_COOKIE, path="/",
        secure=settings.cookie_secure, httponly=True, samesite="lax",
    )
    return {"ok": True}
