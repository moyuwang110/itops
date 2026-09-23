"""公共依赖：JWT 鉴权；登出黑名单落库（重启/多副本均有效）。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import BizError
from app.core.security import decode_access_token
from app.models.auth import RevokedToken

bearer_scheme = HTTPBearer(auto_error=False)


async def revoke_token(db: AsyncSession, jti: str, expires_at_ts: int | float | None) -> None:
    """登记登出令牌。过期时间取 JWT exp（缺失则置为当前时间，随启动清理移除）。"""
    if not jti:
        return
    if expires_at_ts:
        expires_at = datetime.fromtimestamp(int(expires_at_ts), tz=timezone.utc).replace(tzinfo=None)
    else:
        expires_at = datetime.utcnow()
    exists = await db.get(RevokedToken, jti)
    if exists is None:
        db.add(RevokedToken(jti=jti, expires_at=expires_at))
        await db.commit()


async def is_token_revoked(db: AsyncSession, jti: str) -> bool:
    if not jti:
        return False
    return await db.get(RevokedToken, jti) is not None


async def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> str:
    if cred is None or not cred.credentials:
        raise BizError("未登录或登录已过期", code="unauthorized", http_status=401)
    token = cred.credentials
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise BizError("登录令牌无效或已过期", code="unauthorized", http_status=401)
    username = payload.get("sub")
    jti = payload.get("jti", "")
    if not username or username != settings.admin_username:
        raise BizError("非法用户", code="forbidden", http_status=403)
    if await is_token_revoked(db, jti):
        raise BizError("登录已退出，请重新登录", code="unauthorized", http_status=401)
    return username
