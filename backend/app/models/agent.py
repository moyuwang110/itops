"""用户自配置的 AI 分析 Agent（人设 + 模型绑定）。"""
from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Agent(Base, TimestampMixin):
    """用户 Agent：归属某个用户，自定义系统提示词并绑定大模型供应商。"""
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 当前用户名（与 users.username 对齐；多用户预留外键）
    user: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # 大模型供应商（deepseek/doubao/qwen/minimax）
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # 该供应商下的具体模型名；为空时用默认
    model: Mapped[str] = mapped_column(String(128), default="")
    # 角色/人设（系统提示词）
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    # 是否为该用户的默认 Agent
    is_default: Mapped[bool] = mapped_column(default=False)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )