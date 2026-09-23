"""告警列表、详情与手动分析接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import BizError
from app.models.constants import ANALYSIS_PROCESSING
from app.services import alert_service, analysis_service, notify_service, report_service
from app.services.analysis_queue import submit_analysis

router = APIRouter(prefix="/alerts", tags=["alerts"],
                   dependencies=[Depends(get_current_user)])


@router.get("", summary="告警列表（筛选/分页）")
async def list_alerts(
    status: str | None = None,
    analysis_status: str | None = None,
    severity: str | None = None,
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await alert_service.list_alerts(
        db, status=status, analysis_status=analysis_status, severity=severity,
        keyword=keyword, page=page, page_size=page_size,
    )


@router.get("/{alert_id}", summary="告警详情（含报告与通知记录）")
async def alert_detail(alert_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    alert = await alert_service.get_alert(db, alert_id)
    if alert is None:
        raise BizError("告警不存在", code="not_found", http_status=404)
    data = alert_service.serialize_alert(alert)
    data["raw_payload"] = alert.raw_payload
    data["detail_text"] = alert.detail_text
    report = await report_service.get_report_by_alert(db, alert_id)
    data["report"] = report_service.serialize_report(report) if report else None
    data["notifications"] = await notify_service.list_records(db, alert_id)
    return data


@router.post("/{alert_id}/analyze", summary="手动触发/重新分析（后台异步执行）")
async def analyze(alert_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    alert = await alert_service.get_alert(db, alert_id)
    if alert is None:
        raise BizError("告警不存在", code="not_found", http_status=404)
    if alert.analysis_status == ANALYSIS_PROCESSING \
            or alert_id in analysis_service._running:
        raise BizError(f"告警 {alert_id} 正在分析中", code="analysis_busy",
                       http_status=409)
    # 后台执行，避免大模型长耗时阻塞 HTTP（nginx/axios 超时）；前端轮询详情
    ok = submit_analysis(alert_id)
    if not ok:
        raise BizError("分析任务提交失败：服务未就绪", code="submit_failed",
                       http_status=503)
    return {"ok": True, "alert_id": alert_id, "analysis_status": "queued"}
