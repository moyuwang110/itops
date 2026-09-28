"""认证相关模型：用户表与登出 JWT 黑名单（落库，重启/多副本均有效）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    """系统用户（当前单管理员，预留多用户扩展）。"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 头像：URL 或 base64 data URI，空则用首字母占位
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    # JWT 的 jti
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 令牌原始过期时间；过期后记录可安全清理
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
