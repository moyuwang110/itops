"""总览仪表盘汇总接口。"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.timeutil import to_iso, utcnow
from app.models.alert import Alert
from app.models.constants import (
    ANALYSIS_FAILED,
    ANALYSIS_PENDING,
    ANALYSIS_PROCESSING,
    ANALYSIS_SUCCESS,
)
from app.services import alert_service
from app.services.config_service import list_configs

router = APIRouter(prefix="/dashboard", tags=["dashboard"],
                   dependencies=[Depends(get_current_user)])


@router.get("/summary", summary="总览：告警统计/分析成功率/最新告警/集成状态")
async def summary(db: AsyncSession = Depends(get_db)) -> dict:
    since = utcnow() - timedelta(hours=24)

    base = select(Alert).where(Alert.occurred_at >= since)
    alerts_24h = (await db.execute(base)).scalars().all()

    severity_dist: dict[str, int] = {}
    status_dist = {"problem": 0, "resolved": 0}
    for alert in alerts_24h:
        severity_dist[alert.severity or "未分级"] = (
            severity_dist.get(alert.severity or "未分级", 0) + 1
        )
        status_dist[alert.status] = status_dist.get(alert.status, 0) + 1

    analyzed = [a for a in alerts_24h
                if a.analysis_status in (ANALYSIS_SUCCESS, ANALYSIS_FAILED)]
    success = sum(1 for a in analyzed if a.analysis_status == ANALYSIS_SUCCESS)
    success_rate = round(success / len(analyzed) * 100, 1) if analyzed else None

    latest = await alert_service.list_alerts(db, page=1, page_size=10)

    integrations: list[dict] = []
    labels = {
        "zabbix": "Zabbix", "llm": "大模型",
        "log_platform": "日志平台", "notify_channel": "通知渠道",
    }
    for cfg in await list_configs(db):
        integrations.append({
            "type": cfg.type,
            "type_label": labels.get(cfg.type, cfg.type),
            "provider": cfg.provider,
            "name": cfg.name,
            "enabled": cfg.enabled,
            "is_default": cfg.is_default,
            "last_test_ok": cfg.last_test_ok,
            "last_test_at": to_iso(cfg.last_test_at),
            "last_test_message": cfg.last_test_message,
        })

    return {
        "window": "24h",
        "total_24h": len(alerts_24h),
        "severity_dist": severity_dist,
        "status_dist": status_dist,
        "analysis": {
            "success": sum(1 for a in alerts_24h if a.analysis_status == ANALYSIS_SUCCESS),
            "failed": sum(1 for a in alerts_24h if a.analysis_status == ANALYSIS_FAILED),
            "processing": sum(1 for a in alerts_24h if a.analysis_status == ANALYSIS_PROCESSING),
            "pending": sum(1 for a in alerts_24h if a.analysis_status == ANALYSIS_PENDING),
            "success_rate": success_rate,
        },
        "latest_alerts": latest["items"],
        "integrations": integrations,
    }
