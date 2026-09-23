"""通知投递服务：报告视图构建、渠道发送、投递记录。"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.timeutil import to_iso, utcnow
from app.integrations.notify import build_channel
from app.integrations.notify.render import build_notify_view
from app.models.alert import Alert
from app.models.constants import CFG_NOTIFY_CHANNEL
from app.models.report import NotificationRecord
from app.services.config_service import decrypt_settings, list_configs
from app.services.report_service import get_report

logger = logging.getLogger(__name__)


def alert_dict(alert: Alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "title": alert.title,
        "host": alert.host,
        "severity": alert.severity,
        "status": alert.status,
        "occurred_at": to_iso(alert.occurred_at) or "",
    }


def build_link(alert_id: int) -> str:
    # 前端为 hash 路由，必须包含 /#/ 前缀，否则链接打不开详情页
    return f"{settings.public_base_url.rstrip('/')}/#/alerts/{alert_id}"


async def list_records(db: AsyncSession, alert_id: int) -> list[dict[str, Any]]:
    stmt = (
        select(NotificationRecord)
        .where(NotificationRecord.alert_id == alert_id)
        .order_by(NotificationRecord.id.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "channel": r.channel,
            "trigger_type": r.trigger_type,
            "success": r.success,
            "response": r.response,
            "sent_at": to_iso(r.sent_at),
        }
        for r in rows
    ]


async def _channel_rows(db: AsyncSession, channels: list[str]):
    rows = [r for r in await list_configs(db, CFG_NOTIFY_CHANNEL) if r.enabled]
    if channels:
        rows = [r for r in rows if r.provider in channels]
    return rows


async def push_report(db: AsyncSession, report_id: int,
                      channels: list[str] | None,
                      trigger_type: str = "manual") -> list[dict[str, Any]]:
    report = await get_report(db, report_id)
    if report is None:
        raise ValueError("报告不存在")
    alert = await db.get(Alert, report.alert_id)
    view = build_notify_view(
        alert_dict(alert), report.result, build_link(report.alert_id)
    )

    results: list[dict[str, Any]] = []
    for row in await _channel_rows(db, channels or []):
        record = NotificationRecord(
            alert_id=report.alert_id,
            report_id=report.id,
            channel=row.provider,
            trigger_type=trigger_type,
        )
        try:
            channel = build_channel(row.provider, decrypt_settings(row))
            await channel.send_report(view)
            record.success = True
            record.response = "发送成功"
            results.append(
                {"channel": row.provider, "success": True, "message": "发送成功"}
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("通知投递失败 channel=%s: %s", row.provider, exc)
            record.success = False
            record.response = str(exc)[:1000]
            results.append(
                {"channel": row.provider, "success": False, "message": str(exc)}
            )
        record.sent_at = utcnow()
        db.add(record)
    await db.commit()
    return results
