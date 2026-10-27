"""IPAM 模型：VLAN、网段、IP 地址记录、变更记录。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Vlan(Base, TimestampMixin):
    """VLAN 定义。"""

    __tablename__ = "vlans"
    __table_args__ = (UniqueConstraint("vlan_id", name="uq_vlan_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    vlan_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    remark: Mapped[str] = mapped_column(String(512), default="")


class Subnet(Base, TimestampMixin):
    """网段定义与最近一次扫描统计。"""

    __tablename__ = "subnets"
    __table_args__ = (UniqueConstraint("cidr", name="uq_subnet_cidr"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    cidr: Mapped[str] = mapped_column(String(64), index=True)
    gateway: Mapped[str] = mapped_column(String(64), default="")
    purpose: Mapped[str] = mapped_column(String(128), default="")
    # 关联 VLAN 记录（vlans.id，可为空）
    vlan_ref: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    remark: Mapped[str] = mapped_column(String(512), default="")
    # 是否参与每日自动扫描
    auto_scan: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 扫描统计缓存
    total: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[int] = mapped_column(Integer, default=0)
    free: Mapped[int] = mapped_column(Integer, default=0)
    unknown: Mapped[int] = mapped_column(Integer, default=0)
    conflict: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    utilization: Mapped[float] = mapped_column(Float, default=0.0)


class IPAddress(Base, TimestampMixin):
    """单个 IP 地址的登记与扫描结果。"""

    __tablename__ = "ip_addresses"
    __table_args__ = (
        UniqueConstraint("subnet_id", "ip", name="uq_ip_subnet_ip"),
        Index("ix_ip_subnet_status", "subnet_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subnet_id: Mapped[int] = mapped_column(Integer, index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    # used / free / unknown / conflict / reserved
    status: Mapped[str] = mapped_column(String(16), default="free", index=True)
    mac: Mapped[str] = mapped_column(String(32), default="")
    hostname: Mapped[str] = mapped_column(String(255), default="")
    # 手工登记的责任人/用途
    assigned_to: Mapped[str] = mapped_column(String(128), default="")
    purpose: Mapped[str] = mapped_column(String(128), default="")
    remark: Mapped[str] = mapped_column(String(512), default="")
    # auto（扫描发现）/ manual（手工登记）
    source: Mapped[str] = mapped_column(String(16), default="auto", index=True)
    open_ports: Mapped[list[Any]] = mapped_column(JSON, default=list)
    response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 冲突原因，非空即视为冲突
    conflict_reason: Mapped[str] = mapped_column(String(255), default="")
    # 变更计数，便于页面展示活跃度
    change_count: Mapped[int] = mapped_column(Integer, default=0)


class IPChangeLog(Base, TimestampMixin):
    """IP 记录变更历史。"""

    __tablename__ = "ip_change_logs"
    __table_args__ = (Index("ix_iplog_subnet_created", "subnet_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subnet_id: Mapped[int] = mapped_column(Integer, index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    # create / assign / release / status_change / scan_update / update / delete
    action: Mapped[str] = mapped_column(String(32), default="", index=True)
    field: Mapped[str] = mapped_column(String(32), default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    operator: Mapped[str] = mapped_column(String(64), default="system")
    detail: Mapped[str] = mapped_column(Text, default="")
