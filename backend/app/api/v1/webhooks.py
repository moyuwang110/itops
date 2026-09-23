"""Zabbix 告警 Webhook 接收端点（独立 Token，不走 JWT）。"""
from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import BizError
from app.services import alert_service
from app.services.analysis_queue import submit_analysis

router = APIRouter(prefix="/webhooks", tags=["webhook"])
logger = logging.getLogger(__name__)


def _check_webhook_token(header_token: str | None, query_token: str | None) -> None:
    expected = settings.zabbix_webhook_token
    if not expected:
        return
    provided = header_token or query_token or ""
    if not hmac.compare_digest(provided, expected):
        raise BizError("Webhook Token 校验失败", code="webhook_forbidden",
                       http_status=403)


@router.post("/zabbix", summary="接收 Zabbix 告警报文")
async def receive_zabbix(
    request: Request,
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
    token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _check_webhook_token(x_webhook_token, token)

    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise BizError("请求体不是合法 JSON", code="bad_payload", http_status=400) from exc
    if not isinstance(payload, dict):
        raise BizError("告警报文必须是 JSON 对象", code="bad_payload", http_status=400)

    try:
        parsed = alert_service.parse_zabbix_payload(payload)
    except ValueError as exc:
        logger.warning("告警报文解析失败: %s; 原始报文: %s", exc, payload)
        raise BizError(str(exc), code="bad_payload", http_status=400) from exc

    alert, created = await alert_service.ingest_alert(db, parsed, payload)

    # 新建的问题类告警按系统开关自动分析（恢复消息不触发）
    auto = False
    if created and not parsed["is_recovery"]:
        from app.services.config_service import get_system_setting
        setting = await get_system_setting(db)
        auto = setting.auto_analysis
        if auto:
            submit_analysis(alert.id)

    return {
        "ok": True,
        "event_id": alert.event_id,
        "alert_id": alert.id,
        "dedup": "created" if created else "updated",
        "auto_analysis": auto,
    }
