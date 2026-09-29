"""Zabbix 告警报文解析、去重与状态流转。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
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
    # 统一约定：返回 naive UTC（与数据库列类型一致，避免 PG asyncpg 报错）。
    # 1) 秒级时间戳
    for key in ("clock", "timestamp", "ts", "time", "event_time"):
        val = data.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return utc_from_ts(int(val))
        if isinstance(val, str) and val.isdigit() and len(val) >= 10:
            return utc_from_ts(int(val[:10]))
    # 2) 显式 ISO（含时区）
    for key in ("datetime", "date_time", "occurred_at"):
        val = data.get(key)
        if isinstance(val, str) and val:
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S",
                        "%Y/%m/%d %H:%M:%S", "%Y.%m.%d %H:%M:%S"):
                try:
                    raw = val.split("+")[0].strip() if "%z" not in fmt else val
                    dt = datetime.strptime(raw, fmt)
                    # aware datetime → 转 UTC 再去 tzinfo；naive 原样返回
                    if dt.tzinfo is not None:
                        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
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


async def find_alert(db: AsyncSession, key: str) -> Alert | None:
    """按本地主键（纯数字）或 Zabbix event_id 解析告警。"""
    if key.isdigit():
        a = await get_alert(db, int(key))
        if a is not None:
            return a
    return await get_alert_by_event(db, key)


async def list_alerts(db: AsyncSession, *, status: str | None = None,
                      analysis_status: str | None = None,
                      severities: list[str] | None = None,
                      keyword: str | None = None,
                      sort_by: str | None = None,
                      include_acknowledged: bool = False,
                      page: int = 1, page_size: int = 20) -> dict[str, Any]:
    from sqlalchemy import case, func, or_

    conditions = []
    if status:
        conditions.append(Alert.status == status)
    if analysis_status:
        conditions.append(Alert.analysis_status == analysis_status)
    if severities:
        conditions.append(Alert.severity.in_(severities))
    if not include_acknowledged:
        # 默认排除已确认（忽略）的告警
        conditions.append(Alert.acknowledged.is_(False))
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

    # 按严重级别排序：灾难(5) > 严重(4) > ... > 未分类(0)
    severity_order = case(
        (Alert.severity == "灾难", 5),
        (Alert.severity == "严重", 4),
        (Alert.severity == "一般严重", 3),
        (Alert.severity == "警告", 2),
        (Alert.severity == "信息", 1),
        (Alert.severity == "未分类", 0),
        else_=0,
    )
    if sort_by == "severity":
        list_stmt = list_stmt.order_by(
            severity_order.desc(),
            Alert.occurred_at.desc().nullslast(),
            Alert.id.desc(),
        )
    else:
        list_stmt = list_stmt.order_by(
            Alert.occurred_at.desc().nullslast(), Alert.id.desc()
        )
    list_stmt = list_stmt.offset((page - 1) * page_size).limit(page_size)
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
        "acknowledged": bool(alert.acknowledged),
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


async def acknowledge_alert(db: AsyncSession, key: str) -> Alert:
    """确认（忽略）一条告警，将 acknowledged 置为 True。"""
    alert = await find_alert(db, key)
    if alert is None:
        raise KeyError(key)
    alert.acknowledged = True
    await db.commit()
    await db.refresh(alert)
    return alert


async def acknowledge_alerts_batch(db: AsyncSession, event_ids: list[str]) -> dict[str, Any]:
    """批量确认（忽略）告警，返回成功数量与未找到的 event_id 列表。"""
    from sqlalchemy import update

    keys = [str(eid) for eid in event_ids if eid]
    if not keys:
        return {"acknowledged": 0, "not_found": []}

    # 先查出存在的告警
    existing = (await db.execute(
        select(Alert.event_id).where(Alert.event_id.in_(keys))
    )).scalars().all()
    existing_set = set(existing)
    not_found = [k for k in keys if k not in existing_set]

    # 批量更新 acknowledged=True（只更新当前为 False 的，避免重复写入）
    result = await db.execute(
        update(Alert)
        .where(Alert.event_id.in_(existing_set), Alert.acknowledged.is_(False))
        .values(acknowledged=True)
    )
    await db.commit()
    return {"acknowledged": result.rowcount, "not_found": not_found}
