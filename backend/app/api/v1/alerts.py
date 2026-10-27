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
from app.integrations import CLIENT_FACTORIES
from app.integrations.vmware.errors import VCenterError
from app.models.constants import ANALYSIS_PROCESSING
from app.services import (
    alert_noise_service,
    alert_service,
    analysis_service,
    notify_service,
    report_service,
    zabbix_service,
)
from app.services import config_service
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
        "host_ip": "",
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


@router.get("/noise-stats", summary="告警降噪统计")
async def noise_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """返回降噪引擎的实时统计 + 数据库内降噪指标汇总。"""
    from sqlalchemy import func, select
    from app.models.alert import Alert

    stats = alert_noise_service.get_noise_stats()

    # 数据库内汇总：被抑制总数、被去重告警数、累计去重次数
    suppressed_count = (await db.execute(
        select(func.count(Alert.id)).where(Alert.suppressed.is_(True))
    )).scalar_one() or 0
    dedup_rows = (await db.execute(
        select(func.count(Alert.id)).where(Alert.dedup_count > 0)
    )).scalar_one() or 0
    dedup_total = (await db.execute(
        select(func.coalesce(func.sum(Alert.dedup_count), 0))
    )).scalar_one() or 0

    total_in_window = stats["total_received"] or 1
    noise_rate = round(
        (stats["deduped"] + stats["suppressed"]) / total_in_window * 100, 1
    ) if total_in_window else 0.0

    return {
        # 进程级内存统计（自启动以来）
        "in_memory": {
            "total_received": stats["total_received"],
            "deduped": stats["deduped"],
            "suppressed": stats["suppressed"],
            "correlated": stats["correlated"],
            "passed": stats["passed"],
            "noise_rate": noise_rate,
        },
        # 数据库持久化统计（全量）
        "persisted": {
            "suppressed_count": suppressed_count,
            "dedup_alert_count": dedup_rows,
            "dedup_total": dedup_total,
        },
    }


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
        "host_ip": local.host_ip or "",
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


# ---------- VMware 联动分析 ----------


async def _get_vcenter_client(db: AsyncSession):
    """获取已启用的 vCenter 客户端（未配置则抛出 BizError）。"""
    rows = await config_service.list_configs(db, "vmware")
    vcenter_cfg = next((r for r in rows if r.provider == "vcenter" and r.enabled), None)
    if vcenter_cfg is None:
        raise BizError("未配置或未启用 VMware vCenter Server，请先在集成配置中添加。",
                       code="not_configured", http_status=400)
    factory = CLIENT_FACTORIES.get("vcenter")
    if factory is None:
        raise BizError("vCenter 适配器未就绪", code="adapter_missing", http_status=500)
    plain = config_service.decrypt_settings(vcenter_cfg)
    client = factory(plain)
    await client.connect()
    return client


@router.get("/{event_id}/vmware", summary="告警关联的 VMware 虚拟机信息")
async def alert_vmware(event_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """按告警主机名或 IP 匹配 VMware 虚拟机，返回虚拟机详情用于联动分析。"""
    local = await alert_service.find_alert(db, event_id)
    if local is None:
        raise BizError("告警不存在", code="not_found", http_status=404)

    host = (local.host or "").strip()
    host_ip = (local.host_ip or "").strip()
    if not host and not host_ip:
        return {"matched": False, "reason": "告警缺少主机名与 IP，无法匹配 VMware", "vm": None}

    client = await _get_vcenter_client(db)
    try:
        try:
            vms = await client.list_vms()
        except VCenterError as exc:
            raise BizError(str(exc), code=exc.code, http_status=exc.http_status)
        except Exception as exc:  # noqa: BLE001
            raise BizError(f"获取虚拟机清单失败：{exc}", code="vmware_error", http_status=502)
    finally:
        await client.disconnect()

    # 匹配规则：优先 IP 精确匹配，其次主机名（忽略大小写、去域名后缀）
    matched = None
    match_type = ""
    host_lower = host.lower()
    host_short = host_lower.split(".")[0] if "." in host_lower else host_lower
    for vm in vms:
        vm_ip = (vm.get("guest_ip") or "").strip()
        vm_hostname = (vm.get("guest_hostname") or "").strip().lower()
        vm_name = (vm.get("name") or "").strip().lower()
        if host_ip and vm_ip == host_ip:
            matched = vm
            match_type = "ip"
            break
        if host and (vm_hostname == host_lower or vm_hostname.split(".")[0] == host_short
                     or vm_name == host_lower or vm_name == host_short):
            matched = vm
            match_type = "hostname"
            break

    if matched is None:
        return {
            "matched": False,
            "reason": f"未在 VMware 中找到主机 {host or host_ip} 对应的虚拟机",
            "vm": None,
            "match_type": "",
            "search_keys": {"host": host, "host_ip": host_ip},
        }

    return {
        "matched": True,
        "match_type": match_type,
        "search_keys": {"host": host, "host_ip": host_ip},
        "vm": matched,
    }