"""日志统一查询服务（多平台聚合，单平台失败不影响其他平台）。"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConfigMissingError
from app.core.timeutil import to_iso
from app.integrations.logs import build_platform_client
from app.integrations.logs.base import LogQuery
from app.models.constants import CFG_LOG_PLATFORM
from app.services.config_service import decrypt_settings, list_configs

logger = logging.getLogger(__name__)


async def _enabled_platform_rows(db: AsyncSession):
    rows = await list_configs(db, CFG_LOG_PLATFORM)
    return [r for r in rows if r.enabled]


async def enabled_platforms(db: AsyncSession) -> list[dict[str, Any]]:
    return [
        {"provider": r.provider, "name": r.name,
         "last_test_ok": r.last_test_ok,
         "last_test_at": to_iso(r.last_test_at)}
        for r in await _enabled_platform_rows(db)
    ]


async def query_logs(db: AsyncSession, platform: str, start_ts: int, end_ts: int,
                     keyword: str, host: str, limit: int,
                     keywords: list[str] | None = None) -> dict[str, Any]:
    rows = await _enabled_platform_rows(db)
    target = next((r for r in rows if r.provider == platform), None)
    if target is None:
        raise ConfigMissingError(f"日志平台 {platform}（未配置或未启用）")

    client = build_platform_client(target.provider, decrypt_settings(target))
    q = LogQuery(start_ts=start_ts, end_ts=end_ts, keyword=keyword or "",
                 host=host or "", limit=limit, keywords=keywords)
    logs = await client.query(q)
    return {
        "platform": platform,
        "name": target.name,
        "total": len(logs),
        "start": start_ts,
        "end": end_ts,
        "logs": logs,
    }


async def collect_alert_logs(db: AsyncSession, host: str, start_ts: int,
                             end_ts: int, keywords: list[str],
                             per_platform_limit: int = 50) -> dict[str, Any]:
    """分析引擎用：跨全部已启用平台收集相关日志。"""
    result: dict[str, Any] = {"platforms": [], "logs": [], "errors": []}
    for row in await _enabled_platform_rows(db):
        try:
            client = build_platform_client(row.provider, decrypt_settings(row))
            q = LogQuery(start_ts=start_ts, end_ts=end_ts, host=host,
                         limit=per_platform_limit, keywords=keywords)
            logs = await client.query(q)
            result["platforms"].append({"provider": row.provider, "name": row.name,
                                        "count": len(logs)})
            for item in logs:
                item["platform"] = row.provider
            result["logs"].extend(logs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("平台 %s 日志收集失败: %s", row.provider, exc)
            result["errors"].append({"provider": row.provider, "message": str(exc)})
    result["logs"].sort(key=lambda x: x.get("ts", 0))
    return result
