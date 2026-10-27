"""告警降噪服务：智能去重 + 抑制 + 关联分析。

降噪在告警入库前执行，决策结果：
- pass：正常入库
- dedup：与已有告警合并（更新 dedup_count，不创建新记录）
- suppress：标记 suppressed，不触发自动分析和通知
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.constants import ALERT_PROBLEM

logger = logging.getLogger(__name__)

# 严重级别排序（数值越大越严重）
_SEVERITY_RANK = {
    "未分类": 0, "信息": 1, "警告": 2, "一般严重": 3, "严重": 4, "灾难": 5,
}

# 触发"主机不可达"类告警的标题关键字（用于父子关联：主机宕机时抑制其服务告警）
_HOST_DOWN_KEYWORDS = (
    "不可达", "unreachable", "ping", "宕机", "down", "offline", "离线",
)

# 降噪统计（进程级内存，重启清零；用于可观测性展示）
_noise_stats: dict[str, int] = {
    "total_received": 0,
    "deduped": 0,
    "suppressed": 0,
    "correlated": 0,
    "passed": 0,
}


def get_noise_stats() -> dict[str, int]:
    """返回降噪统计快照。"""
    return dict(_noise_stats)


def reset_noise_stats() -> None:
    """清零降噪统计。"""
    for k in _noise_stats:
        _noise_stats[k] = 0


def compute_dedup_key(parsed: dict[str, Any]) -> str:
    """计算去重指纹：host + trigger_id + title 的 MD5。

    trigger_id 为空时退化为 host + title，保证同一主机同一告警能合并。
    """
    host = (parsed.get("host") or "").strip().lower()
    trigger = (parsed.get("trigger_id") or "").strip()
    title = (parsed.get("title") or "").strip()
    raw = f"{host}|{trigger}|{title}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity, 0)


def _is_host_down_alert(parsed: dict[str, Any]) -> bool:
    """判断是否为主机不可达类告警（用于父子关联）。"""
    title = (parsed.get("title") or "").lower()
    return any(kw.lower() in title for kw in _HOST_DOWN_KEYWORDS)


async def find_recent_alert_by_dedup_key(
    db: AsyncSession, dedup_key: str, window_minutes: int
) -> Alert | None:
    """查找时间窗口内相同去重指纹的未恢复告警。"""
    since = datetime.utcnow() - timedelta(minutes=window_minutes)
    stmt = (
        select(Alert)
        .where(
            Alert.dedup_key == dedup_key,
            Alert.status == ALERT_PROBLEM,
            Alert.occurred_at >= since,
        )
        .order_by(Alert.occurred_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def count_recent_alerts_by_host(
    db: AsyncSession, host: str, window_minutes: int
) -> int:
    """统计时间窗口内同一主机的未恢复告警数（用于风暴检测）。"""
    since = datetime.utcnow() - timedelta(minutes=window_minutes)
    stmt = select(func.count(Alert.id)).where(
        Alert.host == host,
        Alert.status == ALERT_PROBLEM,
        Alert.occurred_at >= since,
    )
    return (await db.execute(stmt)).scalar_one() or 0


async def find_host_down_alert(
    db: AsyncSession, host: str, window_minutes: int
) -> Alert | None:
    """查找该主机在窗口内是否有"不可达"类告警（用于父子关联抑制）。"""
    since = datetime.utcnow() - timedelta(minutes=window_minutes)
    # 无法用 SQL LIKE 匹配所有关键字，先取窗口内告警再在 Python 中过滤
    stmt = (
        select(Alert)
        .where(
            Alert.host == host,
            Alert.status == ALERT_PROBLEM,
            Alert.occurred_at >= since,
        )
        .order_by(Alert.occurred_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    for r in rows:
        title = (r.title or "").lower()
        if any(kw.lower() in title for kw in _HOST_DOWN_KEYWORDS):
            return r
    return None


def compute_correlation_group_id(host: str, window_minutes: int) -> str:
    """计算关联分组 ID：按主机 + 时间窗口（5 分钟粒度）分组。"""
    now = datetime.utcnow()
    bucket = int(now.timestamp() // (window_minutes * 60))
    raw = f"{host.lower()}|{bucket}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


async def evaluate_noise_reduction(
    db: AsyncSession, parsed: dict[str, Any], settings
) -> dict[str, Any]:
    """评估降噪决策，返回处理结果。

    返回:
        {
            "action": "pass" | "dedup" | "suppress",
            "dedup_alert": Alert | None,     # action=dedup 时为被合并的已有告警
            "dedup_key": str,
            "suppress_reason": str,
            "correlation_group_id": str,
            "storm": bool,
        }
    """
    _noise_stats["total_received"] += 1

    result: dict[str, Any] = {
        "action": "pass",
        "dedup_alert": None,
        "dedup_key": "",
        "suppress_reason": "",
        "correlation_group_id": "",
        "storm": False,
    }

    # 恢复消息不做降噪，直接透传
    if parsed.get("is_recovery"):
        _noise_stats["passed"] += 1
        return result

    dedup_key = compute_dedup_key(parsed)
    result["dedup_key"] = dedup_key

    # ---- 1. 智能去重 ----
    if settings.dedup_enabled:
        existing = await find_recent_alert_by_dedup_key(
            db, dedup_key, settings.dedup_window_minutes
        )
        if existing is not None:
            existing.dedup_count += 1
            _noise_stats["deduped"] += 1
            result["action"] = "dedup"
            result["dedup_alert"] = existing
            logger.info(
                "告警去重: event_id=%s host=%s title=%s -> 合并到已有告警 id=%s (累计 %d 次)",
                parsed.get("event_id"), parsed.get("host"), parsed.get("title"),
                existing.id, existing.dedup_count,
            )
            return result

    # ---- 2. 关联分析：父子关联 + 风暴检测 ----
    host = parsed.get("host") or ""
    storm = False
    if settings.correlation_enabled and host:
        group_id = compute_correlation_group_id(host, settings.storm_window_minutes)
        result["correlation_group_id"] = group_id

        # 父子关联：若该主机已有"不可达"告警，抑制当前服务级告警
        if not _is_host_down_alert(parsed):
            host_down = await find_host_down_alert(db, host, settings.storm_window_minutes)
            if host_down is not None and settings.suppression_enabled:
                _noise_stats["suppressed"] += 1
                _noise_stats["correlated"] += 1
                result["action"] = "suppress"
                result["suppress_reason"] = f"主机不可达，关联抑制（根因: {host_down.title[:50]}）"
                logger.info(
                    "关联抑制: host=%s title=%s 因主机不可达被抑制",
                    host, parsed.get("title"),
                )
                return result

        # 风暴检测：窗口内同主机告警数超过阈值
        count = await count_recent_alerts_by_host(db, host, settings.storm_window_minutes)
        if count >= settings.storm_threshold:
            storm = True
            result["storm"] = True
            # 风暴不直接抑制，而是标记供前端展示，但高级别告警仍通过
            if settings.suppression_enabled and _severity_rank(parsed.get("severity", "")) <= 2:
                _noise_stats["suppressed"] += 1
                result["action"] = "suppress"
                result["suppress_reason"] = f"告警风暴（{count} 条/{settings.storm_window_minutes}分钟），低级别告警抑制"
                logger.info(
                    "风暴抑制: host=%s 窗口内 %d 条告警，抑制低级别告警: %s",
                    host, count, parsed.get("title"),
                )
                return result

    # ---- 3. 抑制：维护窗口（通过 host 名前缀或专用标记）----
    # 简单实现：标题包含 [维护] 或 host 包含 maintenance 时抑制
    if settings.suppression_enabled:
        title = (parsed.get("title") or "").lower()
        host_lower = host.lower()
        if "[维护]" in title or "maintenance" in host_lower or "maintenance" in title:
            _noise_stats["suppressed"] += 1
            result["action"] = "suppress"
            result["suppress_reason"] = "维护窗口"
            logger.info("维护抑制: host=%s title=%s", host, parsed.get("title"))
            return result

    _noise_stats["passed"] += 1
    return result
