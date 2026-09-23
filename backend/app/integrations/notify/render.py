"""报告 → 精简通知内容渲染。"""
from __future__ import annotations

from typing import Any

_SEVERITY_COLOR = {
    "灾难": "red", "严重": "red", "一般严重": "orange",
    "警告": "orange", "信息": "blue", "未分类": "grey",
}


def severity_color(severity: str) -> str:
    return _SEVERITY_COLOR.get(severity or "", "orange")


def truncate(text: str, limit: int = 1200) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " …（内容已截断，详情见报告链接）"


def _pick(result: dict[str, Any], key: str) -> list[Any]:
    value = result.get(key) or []
    return value if isinstance(value, list) else []


def build_notify_view(alert_dict: dict[str, Any], result: dict[str, Any],
                      link: str) -> dict[str, Any]:
    root_causes: list[str] = []
    for item in _pick(result, "root_causes")[:3]:
        if isinstance(item, dict):
            cause = str(item.get("cause") or item.get("root_cause") or "").strip()
            conf = item.get("confidence")
            if cause:
                root_causes.append(f"{cause}（置信度 {conf}）" if conf else cause)
        elif item:
            root_causes.append(str(item))

    evidence: list[str] = []
    for item in _pick(result, "evidence")[:4]:
        if isinstance(item, dict):
            summary = str(item.get("summary") or item.get("ref") or "").strip()
            etype = item.get("type") or ""
            if summary:
                evidence.append(f"[{etype or '证据'}] {summary}")
        elif item:
            evidence.append(str(item))

    remediation: list[str] = []
    for item in _pick(result, "remediation")[:5]:
        text = str(item).strip() if not isinstance(item, dict) else str(
            item.get("step") or item.get("action") or ""
        ).strip()
        if text:
            remediation.append(text)

    return {
        "title": alert_dict.get("title") or "Zabbix 告警",
        "severity": alert_dict.get("severity") or "",
        "host": alert_dict.get("host") or "",
        "status": alert_dict.get("status") or "problem",
        "time": alert_dict.get("occurred_at") or "",
        "root_causes": root_causes,
        "evidence": evidence,
        "remediation": remediation,
        "impact": str(result.get("impact") or "").strip(),
        "link": link,
    }


def render_markdown(view: dict[str, Any], max_len: int = 3600) -> str:
    status_text = "✅ 已恢复" if view["status"] == "resolved" else "🚨 告警分析"
    lines = [
        f"### {status_text}：{view['title']}",
        f"> 主机：{view['host']}　级别：{view['severity']}　时间：{view['time']}",
    ]
    if view["root_causes"]:
        lines.append("**可能根因：**")
        for i, c in enumerate(view["root_causes"], 1):
            lines.append(f"> {i}. {c}")
    if view["evidence"]:
        lines.append("**关键证据：**")
        for e in view["evidence"]:
            lines.append(f"> - {e}")
    if view["remediation"]:
        lines.append("**处置建议：**")
        for i, s in enumerate(view["remediation"], 1):
            lines.append(f"> {i}. {s}")
    if view.get("link"):
        lines.append(f"[查看完整分析报告]({view['link']})")
    text = "\n".join(lines)
    return truncate(text, max_len)
