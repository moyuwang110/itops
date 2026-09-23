"""AI 分析报告与通知投递记录。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), unique=True, index=True
    )

    # 结构化结论：{root_causes:[{cause,confidence,reason}], evidence:[{type,ref,summary}],
    #             impact, remediation:[...], prevention:[...]}
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # 上下文快照
    metric_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    log_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    markdown: Mapped[str] = mapped_column(Text, default="")

    provider: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    degraded_from: Mapped[str] = mapped_column(String(32), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    # 分析所用窗口与关键词等参数快照
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class NotificationRecord(Base, TimestampMixin):
    __tablename__ = "notification_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), index=True
    )
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(16), index=True)  # feishu/wecom
    trigger_type: Mapped[str] = mapped_column(String(16), default="manual")  # auto/manual/test
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    response: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
