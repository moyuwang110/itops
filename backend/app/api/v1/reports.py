"""分析报告列表、详情、Markdown 导出、手动推送。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import BizError
from app.models.alert import Alert
from app.models.report import Report
from app.services import alert_service, notify_service, report_service

router = APIRouter(prefix="/reports", tags=["reports"],
                   dependencies=[Depends(get_current_user)])


class NotifyRequest(BaseModel):
    channels: list[str] = []


def _naive_utc(dt: datetime | None) -> datetime | None:
    """查询入参的 ISO 时间统一折算为 naive UTC（库内约定）。"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _like(word: str) -> str:
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def _fetch_items(db: AsyncSession, severity: str | None, keyword: str | None,
                       start: datetime | None, end: datetime | None,
                       page: int, page_size: int):
    conditions = []
    if severity:
        conditions.append(Alert.severity == severity)
    if keyword:
        like = _like(keyword)
        conditions.append((Alert.host.like(like, escape="\\"))
                          | (Alert.title.like(like, escape="\\")))
    if start:
        conditions.append(Alert.occurred_at >= start)
    if end:
        conditions.append(Alert.occurred_at <= end)

    count_stmt = select(func.count(Report.id)).join(Alert, Alert.id == Report.alert_id)
    stmt = select(Report, Alert).join(Alert, Alert.id == Report.alert_id)
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
        stmt = stmt.where(cond)
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = (
        stmt.order_by(Report.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    return (await db.execute(stmt)).all(), total


@router.get("", summary="报告列表")
async def list_reports(
    severity: str | None = None,
    keyword: str | None = None,
    start: datetime | None = Query(default=None, description="告警发生时间起（ISO8601）"),
    end: datetime | None = Query(default=None, description="告警发生时间止（ISO8601）"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows, total = await _fetch_items(
        db, severity, keyword, _naive_utc(start), _naive_utc(end), page, page_size
    )
    items = []
    for report, alert in rows:
        item = report_service.serialize_report(report, include_markdown=False)
        item["alert"] = alert_service.serialize_alert(alert)
        items.append(item)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{report_id}", summary="报告详情")
async def report_detail(report_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    report = await report_service.get_report(db, report_id)
    if report is None:
        raise BizError("报告不存在", code="not_found", http_status=404)
    data = report_service.serialize_report(report)
    alert = await db.get(Alert, report.alert_id)
    data["alert"] = alert_service.serialize_alert(alert) if alert else None
    return data


@router.get("/{report_id}/export", summary="导出 Markdown 报告")
async def export_report(report_id: int, db: AsyncSession = Depends(get_db)) -> Response:
    report = await report_service.get_report(db, report_id)
    if report is None:
        raise BizError("报告不存在", code="not_found", http_status=404)
    alert = await db.get(Alert, report.alert_id)
    filename = f"itops-report-{report.alert_id}.md"
    return Response(
        content=report.markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{report_id}/notify", summary="手动推送报告到通知渠道")
async def notify_report(
    report_id: int,
    body: NotifyRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    report = await report_service.get_report(db, report_id)
    if report is None:
        raise BizError("报告不存在", code="not_found", http_status=404)
    results = await notify_service.push_report(
        db, report_id, body.channels or None, trigger_type="manual"
    )
    if not results:
        raise BizError("没有可用的已启用通知渠道，请先在集成配置中启用飞书/企业微信",
                       code="no_channel")
    return {"ok": True, "results": results}
