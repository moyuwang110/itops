"""认证相关模型：登出 JWT 黑名单（落库，重启/多副本均有效）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    # JWT 的 jti
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 令牌原始过期时间；过期后记录可安全清理
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
