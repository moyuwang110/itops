"""Zabbix 告警定时同步服务。

将 Zabbix 当前未恢复问题同步到本地 alerts 表：
- 新增的 problem → 本地创建 status=problem 记录
- 已存在的 problem → 更新标题/级别/主机等字段
- 本地 status=problem 但已不在 Zabbix 当前问题列表 → 标记为 resolved
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utc_from_ts, utcnow
from app.models.alert import Alert
from app.models.constants import ALERT_PROBLEM, ALERT_RESOLVED, ANALYSIS_PENDING
from app.services import zabbix_service

logger = logging.getLogger(__name__)

_SEVERITY_NUM_TO_LABEL = {
    0: "未分类", 1: "信息", 2: "警告", 3: "一般严重", 4: "严重", 5: "灾难",
}


def _problem_to_alert_data(p: dict[str, Any]) -> dict[str, Any]:
    """把 Zabbix problem.get 返回项映射为告警字段。"""
    sev = str(p.get("severity") or "")
    severity = _SEVERITY_NUM_TO_LABEL.get(int(sev), sev) if sev.isdigit() else sev
    hosts = p.get("hosts") or []
    host = hosts[0].get("host") if hosts else ""
    host_id = hosts[0].get("host_id") if hosts else ""
    clock = p.get("clock")
    occurred_at = utc_from_ts(int(clock)) if clock else utcnow()
    return {
        "event_id": str(p.get("event_id") or p.get("objectid") or ""),
        "host": host or "",
        "host_id": str(host_id or ""),
        "title": p.get("name") or "",
        "trigger_id": str(p.get("objectid") or ""),
        "severity": severity,
        "occurred_at": occurred_at,
    }


async def sync_zabbix_alerts(db: AsyncSession) -> dict[str, int]:
    """同步一次 Zabbix 当前未恢复问题到本地 alerts 表。

    返回 {created, updated, resolved}。
    Zabbix 未配置/未启用或调用失败时返回全零，不抛异常。
    """
    try:
        client = await zabbix_service.get_zabbix_client(db, require_enabled=True)
    except Exception:
        logger.debug("Zabbix 未配置或未启用，跳过告警同步")
        return {"created": 0, "updated": 0, "resolved": 0}

    try:
        problems = await client.current_problems(limit=500)
    except Exception as exc:  # noqa: BLE001
        logger.warning("同步 Zabbix 告警失败：%s", exc)
        return {"created": 0, "updated": 0, "resolved": 0}

    current_ids: set[str] = set()
    created = 0
    updated = 0

    for p in problems:
        data = _problem_to_alert_data(p)
        eid = data["event_id"]
        if not eid:
            continue
        current_ids.add(eid)

        existing = (await db.execute(
            select(Alert).where(Alert.event_id == eid)
        )).scalar_one_or_none()

        if existing is None:
            db.add(Alert(
                source="zabbix",
                event_id=eid,
                host=data["host"],
                host_id=data["host_id"],
                title=data["title"],
                trigger_id=data["trigger_id"],
                severity=data["severity"],
                status=ALERT_PROBLEM,
                occurred_at=data["occurred_at"],
                raw_payload=p,
                analysis_status=ANALYSIS_PENDING,
            ))
            created += 1
        else:
            # 已恢复的告警重新出现时，恢复为 problem 状态
            if existing.status == ALERT_RESOLVED:
                existing.status = ALERT_PROBLEM
                existing.recovered_at = None
            # 不覆盖已有分析状态与报告关联，仅更新展示字段
            if data["title"]:
                existing.title = data["title"]
            if data["severity"]:
                existing.severity = data["severity"]
            if data["host"]:
                existing.host = data["host"]
            if data["host_id"]:
                existing.host_id = data["host_id"]
            if data["occurred_at"]:
                existing.occurred_at = data["occurred_at"]
            existing.raw_payload = p
            updated += 1

    # 标记不再活跃的告警为已恢复
    if current_ids:
        result = await db.execute(
            update(Alert)
            .where(Alert.status == ALERT_PROBLEM)
            .where(~Alert.event_id.in_(current_ids))
            .values(status=ALERT_RESOLVED, recovered_at=utcnow())
        )
        resolved = result.rowcount or 0
    else:
        result = await db.execute(
            update(Alert)
            .where(Alert.status == ALERT_PROBLEM)
            .values(status=ALERT_RESOLVED, recovered_at=utcnow())
        )
        resolved = result.rowcount or 0

    await db.commit()
    logger.info("Zabbix 告警同步完成：新增 %d，更新 %d，恢复 %d", created, updated, resolved)
    return {"created": created, "updated": updated, "resolved": resolved}
