"""Zabbix 告警报文解析、去重与状态流转。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import to_iso, utc_from_ts, utcnow
from app.models.alert import Alert
from app.models.constants import ALERT_PROBLEM, ALERT_RESOLVED, ANALYSIS_PENDING

logger = logging.getLogger(__name__)

_SEVERITY_MAP = {
    "0": "未分类", "1": "信息", "2": "警告", "3": "一般严重",
    "4": "严重", "5": "灾难",
}
_RECOVERY_TOKENS = {"ok", "resolved", "recovered", "恢复", "已恢复", "0"}


def _first(data: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for k in keys:
        if k in data and data[k] not in (None, ""):
            return data[k]
    return default


def _parse_time(data: dict[str, Any]) -> datetime | None:
    # 1) 秒级时间戳（统一按 UTC 解析）
    for key in ("clock", "timestamp", "ts", "time", "event_time"):
        val = data.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return utc_from_ts(int(val))
        if isinstance(val, str) and val.isdigit() and len(val) >= 10:
            return utc_from_ts(int(val[:10]))
    # 2) 显式 ISO
    for key in ("datetime", "date_time", "occurred_at"):
        val = data.get(key)
        if isinstance(val, str) and val:
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S",
                        "%Y/%m/%d %H:%M:%S", "%Y.%m.%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(val.split("+")[0].strip()
                                           if "%z" not in fmt else val, fmt)
                    return dt
                except ValueError:
                    continue
    # 3) Zabbix 宏拼接 EVENT.DATE(YYYY.MM.DD) + EVENT.TIME(HH:MM:SS)
    date_part = data.get("event_date") or data.get("date")
    time_part = data.get("event_time") or data.get("event_clock")
    if isinstance(date_part, str) and isinstance(time_part, str):
        for sep in (".", "-", "/"):
            try:
                return datetime.strptime(
                    f"{date_part.strip()} {time_part.strip()}", f"%Y{sep}%m{sep}%d %H:%M:%S"
                )
            except ValueError:
                continue
    return None


def _is_recovery(data: dict[str, Any]) -> bool:
    for key in ("status", "value", "state", "event_status"):
        val = data.get(key)
        if val is None:
            continue
        if isinstance(val, bool):
            continue
        if str(val).strip().lower() in _RECOVERY_TOKENS:
            return True
    if str(data.get("recovery", "")).lower() in {"true", "1", "yes"}:
        return True
    return False


def parse_zabbix_payload(data: dict[str, Any]) -> dict[str, Any]:
    """将各版本 Webhook 载荷归一化；event_id 缺失时抛 KeyError 交由上层 400。"""
    event_id = str(_first(data, "event_id", "eventid", "event_id_str",
                          "event.id", "eventid_str", default="")).strip()
    if not event_id:
        # 问题 ID 兜底
        eid = data.get("event")
        if isinstance(eid, dict):
            event_id = str(eid.get("id") or eid.get("eventid") or "").strip()
    if not event_id:
        raise ValueError("缺少事件标识 event_id/eventid")

    host = str(_first(data, "host", "hostname", "host_name",
                      "host.name", default="")).strip()
    if not host and isinstance(data.get("hosts"), list) and data["hosts"]:
        first_host = data["hosts"][0]
        host = str(first_host.get("name") or first_host.get("host") or "")
    host_id = str(_first(data, "host_id", "hostid", default="")).strip()

    title = str(_first(data, "trigger", "trigger_name", "name", "title",
                       "subject", "message", "alert_message", default="")).strip()
    trigger_id = str(_first(data, "trigger_id", "triggerid", default="")).strip()
    severity_raw = str(_first(data, "severity", "trigger_severity",
                              default="")).strip()
    severity = _SEVERITY_MAP.get(severity_raw, severity_raw)
    detail = str(_first(data, "details", "detail", "description", "text",
                        default="")).strip()
    is_recovery = _is_recovery(data)

    return {
        "event_id": event_id,
        "host": host,
        "host_id": host_id,
        "title": title,
        "trigger_id": trigger_id,
        "severity": severity,
        "is_recovery": is_recovery,
        "occurred_at": _parse_time(data) or utcnow(),
        "detail_text": detail,
    }


async def get_alert(db: AsyncSession, alert_id: int) -> Alert | None:
    return await db.get(Alert, alert_id)


async def get_alert_by_event(db: AsyncSession, event_id: str) -> Alert | None:
    stmt = select(Alert).where(Alert.event_id == event_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_alerts(db: AsyncSession, *, status: str | None = None,
                      analysis_status: str | None = None,
                      severity: str | None = None, keyword: str | None = None,
                      page: int = 1, page_size: int = 20) -> dict[str, Any]:
    from sqlalchemy import func, or_

    conditions = []
    if status:
        conditions.append(Alert.status == status)
    if analysis_status:
        conditions.append(Alert.analysis_status == analysis_status)
    if severity:
        conditions.append(Alert.severity == severity)
    if keyword:
        # 转义 LIKE 通配符，避免用户输入的 %/_ 被当模式字符
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        conditions.append(or_(Alert.host.like(like, escape="\\"),
                              Alert.title.like(like, escape="\\"),
                              Alert.event_id.like(like, escape="\\")))

    count_stmt = select(func.count(Alert.id))
    list_stmt = select(Alert)
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
        list_stmt = list_stmt.where(cond)
    total = (await db.execute(count_stmt)).scalar_one()
    list_stmt = (
        list_stmt.order_by(Alert.occurred_at.desc().nullslast(), Alert.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    rows = (await db.execute(list_stmt)).scalars().all()
    return {
        "items": [serialize_alert(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def serialize_alert(alert: Alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "source": alert.source,
        "event_id": alert.event_id,
        "host": alert.host,
        "title": alert.title,
        "severity": alert.severity,
        "status": alert.status,
        "analysis_status": alert.analysis_status,
        "analysis_error": alert.analysis_error,
        "analysis_times": alert.analysis_times,
        "occurred_at": to_iso(alert.occurred_at),
        "recovered_at": to_iso(alert.recovered_at),
        "created_at": to_iso(alert.created_at),
    }


def _apply_update(existing: Alert, parsed: dict[str, Any], raw: dict[str, Any]) -> None:
    """将报文合并到已存在的告警（恢复消息不覆盖 problem 原始报文）。"""
    if parsed["title"]:
        existing.title = parsed["title"]
    if parsed["severity"]:
        existing.severity = parsed["severity"]
    if parsed["host"] and not existing.host:
        existing.host = parsed["host"]
    if parsed["is_recovery"]:
        existing.recovery_raw_payload = raw
        if existing.status == ALERT_PROBLEM:
            existing.status = ALERT_RESOLVED
            existing.recovered_at = utcnow()
    else:
        existing.raw_payload = raw


async def ingest_alert(db: AsyncSession, parsed: dict[str, Any],
                       raw: dict[str, Any]) -> tuple[Alert, bool]:
    """按 event_id 幂等入库。返回 (alert, created)。

    并发提交同一 event_id 时，第二个请求的唯一约束 commit 会失败，
    此时回滚并重查走更新分支，保证 Webhook 幂等（不返回 500）。
    """
    existing = await get_alert_by_event(db, parsed["event_id"])
    if existing is not None:
        _apply_update(existing, parsed, raw)
        await db.commit()
        await db.refresh(existing)
        return existing, False

    alert = Alert(
        source="zabbix",
        event_id=parsed["event_id"],
        host=parsed["host"],
        host_id=parsed["host_id"],
        title=parsed["title"],
        trigger_id=parsed["trigger_id"],
        severity=parsed["severity"],
        status=ALERT_RESOLVED if parsed["is_recovery"] else ALERT_PROBLEM,
        occurred_at=parsed["occurred_at"],
        recovered_at=utcnow() if parsed["is_recovery"] else None,
        detail_text=parsed["detail_text"],
        raw_payload={} if parsed["is_recovery"] else raw,
        recovery_raw_payload=raw if parsed["is_recovery"] else None,
        analysis_status=ANALYSIS_PENDING,
    )
    db.add(alert)
    try:
        await db.commit()
    except IntegrityError:
        # 并发重复提交：回滚后按已存在记录处理
        await db.rollback()
        existing = await get_alert_by_event(db, parsed["event_id"])
        if existing is None:  # 理论不可达，保持防御
            raise
        _apply_update(existing, parsed, raw)
        await db.commit()
        await db.refresh(existing)
        return existing, False
    await db.refresh(alert)
    logger.info("收到新告警 event_id=%s host=%s title=%s",
                alert.event_id, alert.host, alert.title)
    return alert, True
