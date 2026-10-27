"""集成配置与系统设置 Schema。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.constants import (
    CMDB_PROVIDERS,
    CONFIG_TYPES,
    LLM_PROVIDERS,
    LOG_PROVIDERS,
    NOTIFY_PROVIDERS,
    VMWARE_PROVIDERS,
)


class ConfigUpsert(BaseModel):
    type: str
    provider: str
    name: str = Field("", max_length=128)
    settings: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False
    is_default: bool = False
    priority: int = 100

    @field_validator("type")
    @classmethod
    def _type_valid(cls, v: str) -> str:
        if v not in CONFIG_TYPES:
            raise ValueError(f"非法配置类型: {v}")
        return v

    @field_validator("provider")
    @classmethod
    def _provider_valid(cls, v: str) -> str:
        allowed = {"zabbix"} | LLM_PROVIDERS | LOG_PROVIDERS | NOTIFY_PROVIDERS | VMWARE_PROVIDERS | CMDB_PROVIDERS
        if v not in allowed:
            raise ValueError(f"非法供应商: {v}")
        return v


class ConfigOut(BaseModel):
    id: int
    type: str
    provider: str
    name: str
    settings: dict[str, Any]
    enabled: bool
    is_default: bool
    priority: int
    last_test_at: datetime | None = None
    last_test_ok: bool | None = None
    last_test_message: str | None = None

    model_config = {"from_attributes": True}


class TestResult(BaseModel):
    ok: bool
    message: str


class AutoAnalysisRule(BaseModel):
    """单条自动分析条件规则。各条件为空表示不限制，规则内 AND，规则间 OR。"""
    name: str = Field("", max_length=64)
    enabled: bool = True
    severities: list[str] = Field(default_factory=list)
    hosts: list[str] = Field(default_factory=list)
    host_pattern: str = Field("", max_length=128, description="主机名通配符，如 prod-*")
    time_ranges: list[dict[str, str]] = Field(default_factory=list, description='[{"start":"09:00","end":"18:00"}]')
    keywords: list[str] = Field(default_factory=list, description="标题需包含其中任一关键字")


class SystemSettingIn(BaseModel):
    auto_analysis: bool | None = None
    before_minutes: int | None = Field(default=None, ge=1, le=1440)
    after_minutes: int | None = Field(default=None, ge=0, le=720)
    log_keywords: str | None = Field(default=None, max_length=512)
    auto_notify_channels: list[str] | None = None
    # 降噪配置
    dedup_enabled: bool | None = None
    dedup_window_minutes: int | None = Field(default=None, ge=1, le=1440)
    suppression_enabled: bool | None = None
    correlation_enabled: bool | None = None
    storm_threshold: int | None = Field(default=None, ge=1, le=10000)
    storm_window_minutes: int | None = Field(default=None, ge=1, le=1440)
    # 自动分析条件规则
    auto_analysis_rules: list[AutoAnalysisRule] | None = None


class SystemSettingOut(BaseModel):
    auto_analysis: bool
    before_minutes: int
    after_minutes: int
    log_keywords: str
    auto_notify_channels: list[str]
    # 降噪配置
    dedup_enabled: bool
    dedup_window_minutes: int
    suppression_enabled: bool
    correlation_enabled: bool
    storm_threshold: int
    storm_window_minutes: int
    auto_analysis_rules: list[dict[str, Any]]
