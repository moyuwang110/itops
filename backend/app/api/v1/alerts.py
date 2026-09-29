"""告警列表/详情/分析接口。

数据源：本地 alerts 表（由后台定时任务从 Zabbix 同步）。
- 告警列表默认展示 status=problem（未恢复）
- 已恢复告警通过 status=resolved 查询
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import BizError
from app.models.constants import ANALYSIS_PROCESSING
from app.services import (
    alert_service,
    analysis_service,
    notify_service,
    report_service,
    zabbix_service,
)
from app.services.analysis_queue import submit_analysis

router = APIRouter(prefix="/alerts", tags=["alerts"],
                   dependencies=[Depends(get_current_user)])


_SEVERITY_NUM_TO_LABEL = {
    0: "未分类", 1: "信息", 2: "警告", 3: "一般严重", 4: "严重", 5: "灾难",
}


def _problem_to_row(p: dict[str, Any]) -> dict[str, Any]:
    """把 Zabbix problem.get 返回项映射为告警列表行结构（详情直查兜底用）。"""
    sev = str(p.get("severity") or "")
    return {
        "id": p.get("event_id") or p.get("objectid"),
        "event_id": p.get("event_id") or p.get("objectid"),
        "source": "zabbix",
        "host": (p.get("hosts") or [{}])[0].get("host") or "",
        "host_id": (p.get("hosts") or [{}])[0].get("host_id") or "",
        "title": p.get("name") or "",
        "severity": _SEVERITY_NUM_TO_LABEL.get(int(sev), "-") if sev.isdigit() else (sev or "-"),
        "status": "problem",
        "occurred_at": int(p.get("clock") or 0) * 1000,
        "hosts": p.get("hosts") or [],
    }


@router.get("", summary="告警列表（本地同步数据）")
async def list_alerts(
    host: str | None = Query(default=None, description="主机名关键字"),
    severities: list[int] | None = Query(default=None, description="按告警级别 0-5 筛选，可多选"),
    status: str = Query(default="problem", description="告警状态：problem/resolved"),
    sort: str | None = Query(default=None, description="排序：severity=按严重级别倒序"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    sev_labels: list[str] | None = None
    if severities:
        sev_labels = [_SEVERITY_NUM_TO_LABEL[s] for s in severities if 0 <= s <= 5]
        if not sev_labels:
            sev_labels = None
    result = await alert_service.list_alerts(
        db, status=status, severities=sev_labels, keyword=host,
        sort_by=sort, page=page, page_size=page_size,
    )
    return result


@router.get("/{event_id}", summary="告警详情（含报告与通知记录）")
async def alert_detail(event_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    # 优先尝试本地告警；本地有则直接返回（避免对 Zabbix 的强依赖与覆盖 mock 测试）
    local = await alert_service.find_alert(db, event_id)
    if local is not None:
        return _local_to_detail(local, await report_service.get_report_by_alert(db, local.id),
                                await notify_service.list_records(db, local.id))
    # 本地无记录：尝试从 Zabbix 拉取（一般仅 webhook 未入库 + 详情直查场景）
    problem = None
    try:
        client = await zabbix_service.get_zabbix_client(db, require_enabled=True)
        problems = await client.current_problems(limit=200)
        for p in problems:
            if str(p.get("event_id") or p.get("objectid")) == str(event_id):
                problem = p
                break
    except BizError:
        problem = None
    if problem is None:
        raise BizError("告警不存在或已恢复", code="not_found", http_status=404)
    row = _problem_to_row(problem)
    row["detail_text"] = ""
    row["raw_payload"] = problem
    row["analysis_status"] = "pending"
    row["analysis_error"] = None
    row["analysis_times"] = 0
    row["recovered_at"] = None
    row["local_alert_id"] = None
    row["report"] = None
    row["notifications"] = []
    return row


def _local_to_detail(local: Any, report: Any, notifications: list) -> dict:
    return {
        "id": local.id,
        "event_id": local.event_id,
        "source": local.source,
        "host": local.host,
        "host_id": local.host_id,
        "title": local.title,
        "severity": local.severity,
        "status": local.status,
        "acknowledged": bool(local.acknowledged),
        "occurred_at": local.occurred_at.isoformat() + "+00:00" if local.occurred_at else None,
        "recovered_at": local.recovered_at.isoformat() + "+00:00" if local.recovered_at else None,
        "detail_text": local.detail_text or "",
        "raw_payload": local.raw_payload,
        "analysis_status": local.analysis_status,
        "analysis_error": local.analysis_error,
        "analysis_times": local.analysis_times,
        "local_alert_id": local.id,
        "report": report_service.serialize_report(report) if report else None,
        "notifications": notifications,
        "hosts": [],  # 本地记录没有 hosts 字段，前端按需使用
    }


@router.post("/{event_id}/analyze", summary="基于 Zabbix eventid 触发 AI 分析")
async def analyze(event_id: str,
                  agent_id: int | None = Query(default=None, description="指定 Agent id"),
                  db: AsyncSession = Depends(get_db)) -> dict:
    # 先查找本地告警，不存在则按 eventid 创建一条以便绑定报告
    local = await alert_service.find_alert(db, event_id)
    if local is None:
        # 从 Zabbix 拉取该 event 构造记录
        client = await zabbix_service.get_zabbix_client(db, require_enabled=True)
        problems = await client.current_problems(limit=200)
        problem = next(
            (p for p in problems
             if str(p.get("event_id") or p.get("objectid")) == str(event_id)),
            None,
        )
        if problem is None:
            raise BizError("告警不存在或已恢复", code="not_found", http_status=404)
        # 复用 webhook 的解析+入库链路，传入原始 payload
        fake_payload = {
            "event_id": str(problem.get("event_id") or problem.get("objectid")),
            "host": (problem.get("hosts") or [{}])[0].get("host") or "",
            "host_id": (problem.get("hosts") or [{}])[0].get("host_id") or "",
            "title": problem.get("name") or "",
            "severity": str(problem.get("severity") or ""),
            "trigger_id": str(problem.get("objectid") or ""),
            "status": "PROBLEM",
            "clock": problem.get("clock"),
            "detail_text": "",
        }
        from app.services.alert_service import parse_zabbix_payload, ingest_alert
        parsed = parse_zabbix_payload(fake_payload)
        local, _ = await ingest_alert(db, parsed, fake_payload)
    if local.analysis_status == ANALYSIS_PROCESSING or local.id in analysis_service._running:
        raise BizError(f"告警 {local.id} 正在分析中", code="analysis_busy",
                       http_status=409)
    ok = submit_analysis(local.id, agent_id=agent_id)
    if not ok:
        raise BizError("分析任务提交失败：服务未就绪", code="submit_failed", http_status=503)
    return {"ok": True, "alert_id": local.id, "analysis_status": "queued"}


@router.post("/{event_id}/acknowledge", summary="确认（忽略）告警")
async def acknowledge(event_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        alert = await alert_service.acknowledge_alert(db, event_id)
    except KeyError:
        raise BizError("告警不存在", code="not_found", http_status=404)
    return {"ok": True, "event_id": alert.event_id, "acknowledged": True}


class BatchAcknowledgeIn(BaseModel):
    event_ids: list[str]


@router.post("/acknowledge-batch", summary="批量确认（忽略）告警")
async def acknowledge_batch(payload: BatchAcknowledgeIn, db: AsyncSession = Depends(get_db)) -> dict:
    if not payload.event_ids:
        raise BizError("event_ids 不能为空", code="bad_request", http_status=400)
    result = await alert_service.acknowledge_alerts_batch(db, payload.event_ids)
    return {"ok": True, "acknowledged": result["acknowledged"], "not_found": result["not_found"]}