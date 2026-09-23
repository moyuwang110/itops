"""分析报告持久化、Markdown 渲染与序列化。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import to_iso
from app.models.report import Report


async def get_report_by_alert(db: AsyncSession, alert_id: int) -> Report | None:
    stmt = select(Report).where(Report.alert_id == alert_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_report(db: AsyncSession, report_id: int) -> Report | None:
    return await db.get(Report, report_id)


def render_markdown(alert: dict[str, Any], result: dict[str, Any],
                    metric_ctx: dict[str, Any], log_ctx: dict[str, Any],
                    meta: dict[str, Any]) -> str:
    L: list[str] = []
    L.append(f"# 告警 AI 根因分析报告")
    L.append("")
    L.append(f"- 告警标题：{alert.get('title') or ''}")
    L.append(f"- 主机：{alert.get('host') or ''}")
    L.append(f"- 级别：{alert.get('severity') or ''}")
    L.append(f"- 状态：{'已恢复' if alert.get('status') == 'resolved' else '未恢复'}")
    L.append(f"- 发生时间：{alert.get('occurred_at') or ''}")
    L.append(f"- 分析时间：{meta.get('analyzed_at', '')}")
    L.append(f"- 模型：{meta.get('provider', '')} / {meta.get('model', '')}")
    if meta.get("degraded_from"):
        L.append(f"- 降级说明：主供应商失败，已由 {meta['degraded_from']} 降级完成")
    L.append("")

    L.append("## 一、可能根因")
    for i, item in enumerate(result.get("root_causes") or [], 1):
        if isinstance(item, dict):
            L.append(f"{i}. **[{item.get('confidence', '?')}] {item.get('cause', '')}**")
            if item.get("reason"):
                L.append(f"   - 依据：{item['reason']}")
        else:
            L.append(f"{i}. {item}")
    if not result.get("root_causes"):
        L.append("_无_")

    L.append("")
    L.append("## 二、证据链")
    for i, item in enumerate(result.get("evidence") or [], 1):
        if isinstance(item, dict):
            L.append(f"{i}. `{item.get('type', '')}` {item.get('ref', '')} — {item.get('summary', '')}")
        else:
            L.append(f"{i}. {item}")
    if not result.get("evidence"):
        L.append("_无_")

    L.append("")
    L.append("## 三、影响范围")
    L.append(result.get("impact") or "_未评估_")

    L.append("")
    L.append("## 四、处置建议")
    for i, step in enumerate(result.get("remediation") or [], 1):
        text = step if isinstance(step, str) else step.get("step", "")
        L.append(f"{i}. {text}")
    if not result.get("remediation"):
        L.append("_无_")

    L.append("")
    L.append("## 五、预防建议")
    for i, step in enumerate(result.get("prevention") or [], 1):
        text = step if isinstance(step, str) else step.get("step", "")
        L.append(f"{i}. {text}")
    if not result.get("prevention"):
        L.append("_无_")

    L.append("")
    L.append("## 六、指标上下文摘要")
    series = metric_ctx.get("series") or []
    if series:
        L.append("| 监控项 | 均值 | 峰值 | 谷值 | 末值 | 窗口变化 |")
        L.append("| --- | --- | --- | --- | --- | --- |")
        for s in series:
            st = s["stats"]
            change = "-" if st["change_pct"] is None else f"{st['change_pct']:+.1f}%"
            L.append(
                f"| {s['name']} | {st['avg']} | {st['max']} | {st['min']} | {st['last']} | {change} |"
            )
    else:
        L.append(f"_无指标证据（{metric_ctx.get('reason') or '窗口内无数据'}）_")

    L.append("")
    L.append("## 七、日志证据摘要")
    logs = log_ctx.get("logs") or []
    if logs:
        for item in logs[:50]:
            ts = item.get("timestamp") or ""
            L.append(
                f"- `{ts}` [{item.get('platform')}] [{item.get('level') or '-'}] "
                f"{(item.get('message') or '')[:300]}"
            )
    else:
        L.append("_无日志证据_")

    return "\n".join(L)


async def upsert_report(db: AsyncSession, alert_id: int, result: dict[str, Any],
                        metric_ctx: dict[str, Any], log_ctx: dict[str, Any],
                        meta: dict[str, Any], params: dict[str, Any]) -> Report:
    report = await get_report_by_alert(db, alert_id)
    markdown = render_markdown(meta["alert"], result, metric_ctx, log_ctx, meta)
    if report is None:
        report = Report(alert_id=alert_id)
        db.add(report)
    report.result = result
    report.metric_context = metric_ctx
    report.log_context = log_ctx
    report.markdown = markdown
    report.provider = meta.get("provider", "")
    report.model = meta.get("model", "")
    report.degraded_from = meta.get("degraded_from", "")
    report.duration_ms = meta.get("duration_ms", 0)
    report.params = params
    await db.commit()
    await db.refresh(report)
    return report


def serialize_report(report: Report, include_markdown: bool = True) -> dict[str, Any]:
    data = {
        "id": report.id,
        "alert_id": report.alert_id,
        "result": report.result,
        "metric_context": report.metric_context,
        "log_context": report.log_context,
        "provider": report.provider,
        "model": report.model,
        "degraded_from": report.degraded_from,
        "duration_ms": report.duration_ms,
        "params": report.params,
        "created_at": to_iso(report.created_at),
    }
    if include_markdown:
        data["markdown"] = report.markdown
    return data
