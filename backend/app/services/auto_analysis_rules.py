"""自动分析条件规则评估。

规则模型（SystemSetting.auto_analysis_rules）：
    [{name, enabled, severities[], hosts[], host_pattern, time_ranges[], keywords[]}]

匹配逻辑：
- auto_analysis=False → 永不自动分析
- rules 为空 → 全部自动分析（向后兼容）
- 存在规则 → 任一 enabled 规则匹配即触发（规则间 OR，规则内各非空条件 AND）
"""
from __future__ import annotations

import fnmatch
from datetime import datetime
from typing import Any


def _in_time_range(now: datetime, ranges: list[dict[str, str]]) -> bool:
    """判断当前时间是否落在任一时间段内（HH:MM 格式）。"""
    if not ranges:
        return True
    cur = now.strftime("%H:%M")
    for r in ranges:
        start = r.get("start", "")
        end = r.get("end", "")
        if not start or not end:
            continue
        if start <= end:
            if start <= cur <= end:
                return True
        else:  # 跨天，如 22:00 - 06:00
            if cur >= start or cur <= end:
                return True
    return False


def _match_host(host: str, hosts: list[str], pattern: str) -> bool:
    """主机匹配：精确列表 或 通配符模式。"""
    if not hosts and not pattern:
        return True
    h = (host or "").strip().lower()
    if hosts and h in [x.strip().lower() for x in hosts]:
        return True
    if pattern and fnmatch.fnmatch(h, pattern.strip().lower()):
        return True
    return False


def should_auto_analyze(parsed: dict[str, Any], setting) -> tuple[bool, str]:
    """评估告警是否应触发自动分析。

    返回 (是否分析, 匹配的规则名或原因)。
    """
    if not getattr(setting, "auto_analysis", True):
        return False, "自动分析已关闭"

    rules = getattr(setting, "auto_analysis_rules", None) or []
    # 无规则时保持兼容：全部自动分析
    if not rules:
        return True, "无规则，默认自动分析"

    severity = parsed.get("severity", "")
    host = parsed.get("host", "")
    title = (parsed.get("title") or "").lower()
    now = datetime.utcnow()

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        # 严重级别
        sevs = rule.get("severities") or []
        if sevs and severity not in sevs:
            continue
        # 主机
        hosts = rule.get("hosts") or []
        pattern = rule.get("host_pattern") or ""
        if not _match_host(host, hosts, pattern):
            continue
        # 时间段
        ranges = rule.get("time_ranges") or []
        if not _in_time_range(now, ranges):
            continue
        # 关键字（标题包含任一）
        kws = [k.lower() for k in (rule.get("keywords") or []) if k]
        if kws and not any(k in title for k in kws):
            continue
        # 所有条件满足
        return True, rule.get("name") or "匹配规则"

    return False, "未匹配任何自动分析规则"
