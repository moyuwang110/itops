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


async def query_problems(db: AsyncSession, limit: int, host: str | None = None,
                         severities: list[int] | None = None) -> list[dict[str, Any]]:
    client = await get_zabbix_client(db)
    return await client.current_problems(limit, host=host, severities=severities)


async def query_hosts_overview(db: AsyncSession, keyword: str = "",
                               limit: int = 500) -> list[dict[str, Any]]:
    """主机概览：主机名/IP/主机组/可用性 + CPU/内存/磁盘使用率。"""
    client = await get_zabbix_client(db)
    hosts = await client.list_hosts_overview(keyword=keyword or "", limit=limit)
    try:
        usage = await client.host_usage_map()
    except Exception:  # noqa: BLE001  资源项查询失败不应影响主机清单
        usage = {}
    for h in hosts:
        u = usage.get(str(h.get("host_id") or ""), {})
        h["cpu_usage"] = u.get("cpu")
        h["memory_usage"] = u.get("memory")
        h["disk_usage"] = u.get("disk")
    return hosts


async def query_usage_top(db: AsyncSession, top: int = 5) -> dict[str, Any]:
    """仪表盘：CPU/内存/磁盘使用率 TOP N 主机 + 可用性统计。"""
    client = await get_zabbix_client(db)
    hosts = await client.list_hosts_overview(limit=1000)
    usage = await client.host_usage_map()

    rows: list[dict[str, Any]] = []
    availability = {"available": 0, "unavailable": 0, "unknown": 0}
    for h in hosts:
        u = usage.get(str(h.get("host_id") or ""), {})
        rows.append({
            "host_id": h.get("host_id"),
            "host": h.get("host"),
            "name": h.get("name"),
            "ip": h.get("ip") or "",
            "cpu": u.get("cpu"),
            "memory": u.get("memory"),
            "disk": u.get("disk"),
        })
        avail = str(h.get("available") or "0")
        if avail == "1":
            availability["available"] += 1
        elif avail == "2":
            availability["unavailable"] += 1
        else:
            availability["unknown"] += 1

    def _top(field: str) -> list[dict[str, Any]]:
        picked = [r for r in rows if r.get(field) is not None]
        picked.sort(key=lambda r: r[field], reverse=True)
        return picked[:top]

    return {
        "host_total": len(rows),
        "availability": availability,
        "cpu_top": _top("cpu"),
        "memory_top": _top("memory"),
        "disk_top": _top("disk"),
    }
