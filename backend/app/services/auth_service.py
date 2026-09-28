"""用户与认证服务：凭据校验、初始管理员播种、资料更新。"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.auth import User

logger = logging.getLogger(__name__)


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def verify_user_credentials(db: AsyncSession, username: str,
                                  password: str) -> User | None:
    """校验用户名/密码，返回用户对象或 None。"""
    user = await get_user_by_username(db, username)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def seed_admin_user(db: AsyncSession) -> bool:
    """启动时若 users 表为空，用配置的管理员账号/密码播种。返回是否新建。"""
    existing = await db.execute(select(User).limit(1))
    if existing.scalar_one_or_none() is not None:
        return False
    user = User(
        username=settings.admin_username,
        password_hash=hash_password(settings.admin_password),
        avatar=None,
    )
    db.add(user)
    await db.commit()
    logger.info("已播种初始管理员账号: %s", settings.admin_username)
    return True


async def update_profile(db: AsyncSession, user: User, username: str | None,
                         avatar: str | None) -> User:
    if username is not None and username != user.username:
        # 唯一性校验
        dup = await get_user_by_username(db, username)
        if dup is not None and dup.id != user.id:
            raise ValueError("用户名已存在")
        user.username = username
    if avatar is not None:
        user.avatar = avatar or None
    await db.commit()
    await db.refresh(user)
    return user


async def change_password(db: AsyncSession, user: User, old_password: str,
                          new_password: str) -> None:
    if not verify_password(old_password, user.password_hash):
        raise ValueError("原密码不正确")
    user.password_hash = hash_password(new_password)
    await db.commit()
