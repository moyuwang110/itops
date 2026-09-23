"""AI 根因分析编排：上下文聚合 → 大模型 → 结构化报告 → 自动通知。"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.exceptions import IntegrationError
from app.core.timeutil import to_epoch, to_iso, utcnow
from app.integrations.llm import LLMParserError, parse_structured_json
from app.models.alert import Alert
from app.models.constants import (
    ANALYSIS_FAILED,
    ANALYSIS_PENDING,
    ANALYSIS_PROCESSING,
    ANALYSIS_SUCCESS,
)
from app.services import llm_service, log_service, metric_service, report_service
from app.services.config_service import get_system_setting
from app.integrations.logs.log_helpers import split_keywords
from app.services.prompt_builder import build_analysis_messages, repair_messages
from app.services.zabbix_service import get_zabbix_client

logger = logging.getLogger(__name__)

# 进程内分析锁，防止同一告警并发重复分析
_running: set[int] = set()


class AnalysisBusyError(Exception):
    pass


async def recover_stale() -> int:
    """启动回收：上次进程崩溃时停留在 processing 的告警重置为 pending。

    返回重置条数。
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(Alert)
            .where(Alert.analysis_status == ANALYSIS_PROCESSING)
            .values(analysis_status=ANALYSIS_PENDING,
                    analysis_error="服务重启，任务中断，已重置为待分析")
        )
        await db.commit()
        return result.rowcount or 0


async def run_analysis(alert_id: int) -> dict[str, Any]:
    if alert_id in _running:
        logger.info("告警 %s 正在分析中，跳过重复触发", alert_id)
        raise AnalysisBusyError(f"告警 {alert_id} 正在分析中")
    _running.add(alert_id)
    start = time.time()
    try:
        async with AsyncSessionLocal() as db:
            return await _run_with_session(db, alert_id, start)
    finally:
        _running.discard(alert_id)


async def _set_status(db: AsyncSession, alert: Alert, status: str,
                      error: str | None = None) -> None:
    alert.analysis_status = status
    alert.analysis_error = error
    await db.commit()


async def _run_with_session(db: AsyncSession, alert_id: int,
                            start: float) -> dict[str, Any]:
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise ValueError(f"告警不存在: {alert_id}")
    if alert.analysis_status == ANALYSIS_PROCESSING:
        raise AnalysisBusyError(f"告警 {alert_id} 正在分析中")

    alert.analysis_status = ANALYSIS_PROCESSING
    alert.analysis_error = None
    alert.analysis_times += 1
    await db.commit()

    try:
        setting = await get_system_setting(db)
        before = setting.before_minutes
        after = setting.after_minutes
        keywords = split_keywords(setting.log_keywords)

        center_ts = int(to_epoch(alert.occurred_at)) if alert.occurred_at else int(time.time())

        # 1) 指标上下文（Zabbix 不可用时降级为空证据）
        zabbix_client = None
        try:
            zabbix_client = await get_zabbix_client(db, require_enabled=True)
        except Exception as zex:  # noqa: BLE001
            logger.info("Zabbix 不可用，分析将缺少指标证据: %s", zex)
        metric_ctx = await metric_service.collect_metric_context(
            zabbix_client, alert.host, center_ts, before, after
        )

        # 2) 日志上下文（跨平台，逐平台容错）
        log_ctx = await log_service.collect_alert_logs(
            db,
            host=alert.host,
            start_ts=center_ts - before * 60,
            end_ts=center_ts + after * 60,
            keywords=keywords,
        )

        # 3) 大模型分析（默认供应商 + 备用降级）
        chain = await llm_service.get_llm_chain(db)
        alert_view = {
            "host": alert.host,
            "title": alert.title,
            "severity": alert.severity,
            "occurred_at": to_iso(alert.occurred_at) or "",
            "detail_text": alert.detail_text,
        }
        messages = build_analysis_messages(alert_view, metric_ctx, log_ctx)

        llm_resp = await chain.chat(messages, json_mode=True, max_tokens=8192)
        raw_content = llm_resp.content
        try:
            result = parse_structured_json(raw_content)
        except LLMParserError as parse_err:
            # 一次修复重试
            logger.warning("结构化解析失败，发起修复重试: %s", parse_err)
            llm_resp = await chain.chat(
                repair_messages(str(parse_err), raw_content),
                json_mode=True, max_tokens=8192,
            )
            result = parse_structured_json(llm_resp.content)

        _validate_result_shape(result)
        duration_ms = int((time.time() - start) * 1000)
        meta = {
            "alert": alert_view,
            "analyzed_at": utcnow().isoformat(timespec="seconds") + "+00:00",
            "provider": llm_resp.provider,
            "model": llm_resp.model,
            "degraded_from": llm_resp.degraded_from,
            "duration_ms": duration_ms,
        }
        params = {
            "before_minutes": before,
            "after_minutes": after,
            "log_keywords": keywords,
        }

        # 4) 报告落库
        report = await report_service.upsert_report(
            db, alert.id, result, metric_ctx, log_ctx, meta, params
        )
        await _set_status(db, alert, ANALYSIS_SUCCESS)
        logger.info("告警 %s 分析成功 report=%s provider=%s 耗时=%dms",
                    alert.id, report.id, llm_resp.provider, duration_ms)

        # 5) 自动通知
        notify_results: list[dict[str, Any]] = []
        channels = setting.auto_notify_channels or []
        if channels:
            try:
                from app.services import notify_service
                notify_results = await notify_service.push_report(
                    db, report.id, channels, trigger_type="auto"
                )
            except Exception:  # noqa: BLE001
                logger.exception("自动通知失败 alert_id=%s", alert.id)

        return {
            "ok": True,
            "alert_id": alert.id,
            "report_id": report.id,
            "provider": llm_resp.provider,
            "degraded_from": llm_resp.degraded_from,
            "duration_ms": duration_ms,
            "notify_results": notify_results,
        }

    except AnalysisBusyError:
        # 并发重复触发：状态由持锁方维护，不覆盖为 failed
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("告警 %s 分析失败", alert_id)
        # 刷新会话中可能失效的对象
        alert = await db.get(Alert, alert_id)
        if alert is not None:
            alert.analysis_status = ANALYSIS_FAILED
            alert.analysis_error = str(exc)[:2000]
            await db.commit()
        raise


_REQUIRED_KEYS = {"root_causes", "evidence", "impact", "remediation", "prevention"}


def _validate_result_shape(result: dict[str, Any]) -> None:
    missing = _REQUIRED_KEYS - set(result.keys())
    if missing:
        raise LLMParserError(f"模型 JSON 缺少字段: {', '.join(sorted(missing))}")
    for key in ("root_causes", "remediation", "prevention", "evidence"):
        if not isinstance(result.get(key), list):
            raise LLMParserError(f"字段 {key} 必须是数组")
