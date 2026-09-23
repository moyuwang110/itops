"""告警指标上下文聚合：相关监控项筛选 + 窗口时序统计。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.integrations.zabbix.client import ZabbixClient

logger = logging.getLogger(__name__)

# 相关监控项匹配词（小写包含匹配）
RELEVANT_KEYWORDS = (
    "cpu", "load", "memory", "mem", "vm.memory", "disk", "vfs.fs",
    "network", "net.if", "traffic", "interface", "swap", "iops", "io.",
    "磁盘", "内存", "cpu", "负载", "网络", "流量", "使用率",
)
MAX_SERIES = 10
MAX_POINTS = 500


async def resolve_host(client: ZabbixClient, host_name: str) -> dict[str, Any] | None:
    if not host_name:
        return None
    hosts = await client.search_hosts(keyword=host_name, limit=10)
    for h in hosts:
        if h.get("host") == host_name or h.get("name") == host_name:
            return h
    return hosts[0] if hosts else None


def _relevant(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    numeric = [i for i in items if i.get("value_type") in (0, 3)]
    matched = [
        i for i in numeric
        if any(k in (i.get("name", "") + i.get("key_", "")).lower()
               for k in RELEVANT_KEYWORDS)
    ]
    picked = (matched or numeric)[:MAX_SERIES]
    return picked


def _stats(points: list[dict[str, float]]) -> dict[str, Any]:
    values = [p["value"] for p in points]
    first, last = values[0], values[-1]
    mn, mx = min(values), max(values)
    avg = sum(values) / len(values)
    change_pct = ((last - first) / first * 100) if first not in (0, 0.0) else None
    max_point = max(points, key=lambda p: p["value"])
    min_point = min(points, key=lambda p: p["value"])
    return {
        "first": round(first, 4),
        "last": round(last, 4),
        "min": round(mn, 4),
        "max": round(mx, 4),
        "avg": round(avg, 4),
        "change_pct": None if change_pct is None else round(change_pct, 2),
        "max_ts": max_point["ts"],
        "min_ts": min_point["ts"],
    }


def _summary(name: str, units: str, stats: dict[str, Any]) -> str:
    bits = [
        f"均值 {stats['avg']}{units}",
        f"峰值 {stats['max']}{units}",
        f"谷值 {stats['min']}{units}",
        f"末值 {stats['last']}{units}",
    ]
    if stats["change_pct"] is not None:
        bits.append(f"窗口内变化 {stats['change_pct']:+.1f}%")
    peak_time = datetime.fromtimestamp(stats["max_ts"], tz=timezone.utc).strftime("%H:%M:%S UTC")
    bits.append(f"峰值时刻(UTC) {peak_time}")
    return f"{name}: " + "，".join(bits)


async def collect_metric_context(client: ZabbixClient | None, host_name: str,
                                 center_ts: int, before: int,
                                 after: int) -> dict[str, Any]:
    window = {"start": center_ts - before * 60, "end": center_ts + after * 60}
    base: dict[str, Any] = {
        "host": host_name, "host_id": "", "window": window,
        "available": False, "series": [],
    }
    if client is None:
        base["reason"] = "Zabbix 未配置或未启用"
        return base
    if not host_name:
        base["reason"] = "告警未携带主机信息"
        return base

    try:
        host = await resolve_host(client, host_name)
        if host is None:
            base["reason"] = f"Zabbix 中未找到主机 {host_name}"
            return base
        base["host_id"] = host["host_id"]
        items = await client.list_items(host["host_id"], limit=500)
        picked = _relevant(items)
        series: list[dict[str, Any]] = []
        for item in picked:
            points = await client.history(
                item["item_id"], item["value_type"],
                window["start"], window["end"], limit=MAX_POINTS,
            )
            if len(points) < 2:
                continue
            stats = _stats(points)
            series.append({
                "item_id": item["item_id"],
                "name": item["name"],
                "key_": item.get("key_", ""),
                "units": item.get("units", ""),
                "points": points,
                "stats": stats,
                "summary": _summary(item["name"], item.get("units", ""), stats),
            })
        base["series"] = series
        base["available"] = True
        if not series:
            base["reason"] = "窗口内未取到该主机的数值型监控历史"
        return base
    except Exception as exc:  # noqa: BLE001
        logger.warning("指标上下文聚合失败 host=%s: %s", host_name, exc)
        base["reason"] = f"指标查询失败: {exc}"
        return base
