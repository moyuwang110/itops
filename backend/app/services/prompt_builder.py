"""根因分析 Prompt 构建。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SYSTEM_PROMPT = """你是一名资深 SRE 运维专家。请基于用户提供的【告警信息】【监控指标趋势】【相关日志】进行告警溯源与根因分析。

硬性要求：
1. 只能依据提供的证据进行分析，严禁编造不存在的指标数据或日志条目；某类数据缺失时必须在结论中明确标注“无指标证据”或“无日志证据”。
2. 证据链中的每一条 evidence 必须能回溯到输入中的具体监控项名称（含时间点/数值）或日志条目（含时间、来源、内容摘要）。
3. 根因按可能性从高到低给出，并给出置信度（只能是“高/中/低”）与判断理由。
4. 处置建议必须具体、可执行、按步骤排列；预防建议面向中长期。
5. 输出必须且只能是一个合法 JSON 对象（不要输出 markdown 代码围栏、不要输出多余解释文字），结构严格如下：
{
  "root_causes": [{"cause": "根因描述", "confidence": "高", "reason": "支撑该判断的证据与推理"}],
  "evidence": [{"type": "metric 或 log", "ref": "监控项名称/日志时间与来源", "summary": "证据摘要（含关键数值或日志片段）"}],
  "impact": "影响范围评估",
  "remediation": ["处置步骤1", "处置步骤2"],
  "prevention": ["预防建议1"]
}"""


def _fmt_ts(ts: int) -> str:
    # 统一 UTC，与告警时间（+00:00）、平台日志时间保持同一时区
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def build_analysis_messages(alert: dict[str, Any], metric_ctx: dict[str, Any],
                            log_ctx: dict[str, Any]) -> list[dict[str, str]]:
    lines: list[str] = ["【告警信息】"]
    lines.append(f"- 主机：{alert.get('host') or '未知'}")
    lines.append(f"- 告警标题：{alert.get('title') or ''}")
    lines.append(f"- 级别：{alert.get('severity') or '未知'}")
    occurred = alert.get("occurred_at")
    lines.append(f"- 发生时间：{occurred or '未知'}")
    if alert.get("detail_text"):
        lines.append(f"- 告警详情：{alert['detail_text'][:1000]}")

    lines.append("\n【监控指标趋势】")
    window = metric_ctx.get("window") or {}
    if window:
        lines.append(
            f"统计窗口：{_fmt_ts(window['start'])} ~ {_fmt_ts(window['end'])}"
        )
    series = metric_ctx.get("series") or []
    if series:
        for idx, s in enumerate(series, 1):
            lines.append(f"{idx}. {s['summary']}")
            points = s.get("points") or []
            tail = points[-10:]
            lines.append("   最近采样：" + ", ".join(
                f"{_fmt_ts(p['ts'])}={p['value']}" for p in tail
            ))
    else:
        lines.append(f"无指标证据（{metric_ctx.get('reason') or '窗口内无数据'}）。")

    lines.append("\n【相关日志】")
    platforms = log_ctx.get("platforms") or []
    if platforms:
        lines.append("已检索平台：" + "、".join(
            f"{p['name']}({p['count']} 条)" for p in platforms
        ))
    logs = log_ctx.get("logs") or []
    if logs:
        for idx, item in enumerate(logs[:50], 1):
            ts = item.get("timestamp") or _fmt_ts(item.get("ts", 0))
            lines.append(
                f"{idx}. [{ts}] [{item.get('platform')}] "
                f"[{item.get('level') or '-'}] {item.get('host')} "
                f"{(item.get('message') or '')[:300]}"
            )
    else:
        reason = "未检索到匹配日志"
        if log_ctx.get("errors"):
            reason += "；部分平台检索异常：" + "; ".join(
                e["message"] for e in log_ctx["errors"][:3]
            )
        lines.append(f"无日志证据（{reason}）。")

    lines.append(
        "\n请按系统消息约定的 JSON 结构输出根因分析结果。"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]


REPAIR_PROMPT = (
    "你上一次的输出无法被解析为合法 JSON，错误：{error}。"
    "请仅输出一个合法 JSON 对象，严格包含 root_causes/evidence/impact/"
    "remediation/prevention 字段，不要输出代码围栏或任何解释文字。"
    "上一次输出如下：\n{previous}"
)


def repair_messages(error: str, previous: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": REPAIR_PROMPT.format(
            error=str(error)[:200], previous=previous[:6000]
        )},
    ]


def dumps_context(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)
