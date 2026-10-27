"""集成配置与系统设置模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, func, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class IntegrationConfig(Base, TimestampMixin):
    __tablename__ = "integration_configs"
    __table_args__ = (
        UniqueConstraint("type", "provider", name="uq_config_type_provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    # 供应商：llm -> deepseek/doubao/qwen/minimax；log -> graylog/loki/elasticsearch；
    # notify -> feishu/wecom；zabbix 固定 zabbix
    provider: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    # 含密钥的设置项由服务层加密后落库；读取时解密
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # 备用顺序（仅 llm 使用），数值越小越优先
    priority: Mapped[int] = mapped_column(Integer, default=100)

    last_test_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(String(512), nullable=True)


class SystemSetting(Base):
    """单行系统设置（id 固定为 1）。"""

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    auto_analysis: Mapped[bool] = mapped_column(Boolean, default=True)
    before_minutes: Mapped[int] = mapped_column(Integer, default=30)
    after_minutes: Mapped[int] = mapped_column(Integer, default=10)
    log_keywords: Mapped[str] = mapped_column(
        String(512),
        default="error,exception,fatal,panic,超时,失败,异常,拒绝,oom,timeout,refused,unreachable",
    )
    auto_notify_channels: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True
    )

    # ---------- 告警降噪配置 ----------
    # 智能去重：同一 host+trigger+title 在窗口内合并，只保留第一条，计数累加
    dedup_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    dedup_window_minutes: Mapped[int] = mapped_column(Integer, default=5)
    # 抑制：维护窗口、高级别告警覆盖低级别
    suppression_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 关联分析：父子关联（主机宕机抑制服务告警）、风暴检测
    correlation_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    storm_threshold: Mapped[int] = mapped_column(Integer, default=10)
    storm_window_minutes: Mapped[int] = mapped_column(Integer, default=5)

    # ---------- 自动分析条件规则 ----------
    # 规则列表，JSON 结构：[{name, enabled, severities[], hosts[], host_pattern, time_ranges[], keywords[]}]
    # 规则间为 OR 关系，单条规则内各条件为 AND 关系（空条件视为不限制）。
    # auto_analysis=True 且 rules 为空时保持兼容：所有告警自动分析。
    auto_analysis_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
