"""Zabbix 配置加载与查询服务。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConfigMissingError
from app.integrations.zabbix.client import ZabbixClient
from app.models.constants import CFG_ZABBIX
from app.services.config_service import decrypt_settings, get_config_by_provider


async def get_zabbix_client(db: AsyncSession, require_enabled: bool = True) -> ZabbixClient:
    row = await get_config_by_provider(db, CFG_ZABBIX, "zabbix")
    if row is None or not (row.enabled or not require_enabled):
        raise ConfigMissingError("Zabbix")
    if require_enabled and not row.enabled:
        raise ConfigMissingError("Zabbix")
    return ZabbixClient(decrypt_settings(row))


def parse_time(value: str | int | None) -> int | None:
    """支持秒级时间戳或 ISO 8601 字符串。"""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except ValueError as exc:
        raise ValueError(f"无法解析时间: {value}（支持秒级时间戳或 ISO 8601）") from exc


async def query_hosts(db: AsyncSession, keyword: str, limit: int) -> list[dict[str, Any]]:
    client = await get_zabbix_client(db)
    return await client.search_hosts(keyword=keyword or "", limit=limit)


async def query_items(db: AsyncSession, host_id: str, keyword: str,
                      limit: int) -> list[dict[str, Any]]:
    client = await get_zabbix_client(db)
    return await client.list_items(host_id=host_id, keyword=keyword or "", limit=limit)


async def query_history(db: AsyncSession, item_id: str, value_type: int,
                        start: int, end: int, limit: int) -> list[dict[str, Any]]:
    client = await get_zabbix_client(db)
    return await client.history(item_id, value_type, start, end, limit)


async def query_trend(db: AsyncSession, item_id: str, value_type: int,
                      start: int, end: int, limit: int) -> list[dict[str, Any]]:
    """Zabbix 趋势聚合（小时级 min/avg/max），适合长窗口回溯。"""
    client = await get_zabbix_client(db)
    return await client.trend(item_id, value_type, start, end, limit)


async def query_problems(db: AsyncSession, limit: int) -> list[dict[str, Any]]:
    client = await get_zabbix_client(db)
    return await client.current_problems(limit)
