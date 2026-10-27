"""Zabbix 告警报文模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
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
    # 主机 IP（Zabbix 接口 IP，同步时填充；用于列表展示与 VMware 联动匹配）
    host_ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    trigger_id: Mapped[str] = mapped_column(String(64), default="")
    # 原始级别（Zabbix: Not classified/Information/Warning/Average/High/Disaster 或数字）
    severity: Mapped[str] = mapped_column(String(32), default="", index=True)
    status: Mapped[str] = mapped_column(String(16), default=ALERT_PROBLEM, index=True)
    # 用户确认/忽略标记：True 表示已确认，默认告警列表不展示
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

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

    # ---------- 降噪字段 ----------
    # 去重指纹：host + trigger_id + title 的哈希，同一指纹在时间窗口内视为重复
    dedup_key: Mapped[str] = mapped_column(String(64), default="", index=True)
    # 去重计数：该指纹已被合并的重复告警数（不含本条）
    dedup_count: Mapped[int] = mapped_column(Integer, default=0)
    # 是否被抑制（维护窗口、高级别告警覆盖等）
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    suppress_reason: Mapped[str] = mapped_column(String(128), default="")
    # 关联分组 ID：同一主机在时间窗口内的告警归入同一组，便于父子关联与风暴识别
    correlation_group_id: Mapped[str] = mapped_column(String(64), default="", index=True)
