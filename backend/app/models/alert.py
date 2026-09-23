"""Zabbix 告警报文模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.constants import ALERT_PROBLEM, ANALYSIS_PENDING


class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_occurred_status", "occurred_at", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 来源平台（本期固定 zabbix，预留扩展）
    source: Mapped[str] = mapped_column(String(32), default="zabbix", index=True)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    host: Mapped[str] = mapped_column(String(256), default="", index=True)
    host_id: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    trigger_id: Mapped[str] = mapped_column(String(64), default="")
    # 原始级别（Zabbix: Not classified/Information/Warning/Average/High/Disaster 或数字）
    severity: Mapped[str] = mapped_column(String(32), default="", index=True)
    status: Mapped[str] = mapped_column(String(16), default=ALERT_PROBLEM, index=True)

    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 分析状态机 pending/processing/success/failed
    analysis_status: Mapped[str] = mapped_column(
        String(16), default=ANALYSIS_PENDING, index=True
    )
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_times: Mapped[int] = mapped_column(Integer, default=0)

    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # 恢复报文单独保存，避免覆盖 problem 原始报文
    recovery_raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    detail_text: Mapped[str] = mapped_column(Text, default="")
