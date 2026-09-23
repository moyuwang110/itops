"""时间工具：系统内部统一使用 naive UTC 存储，序列化时补 +00:00 偏移。"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """当前 UTC 时间（naive，与 DB 列约定一致）。"""
    return datetime.utcnow()


def utc_from_ts(ts: int | float) -> datetime:
    """Unix 秒级时间戳 → naive UTC。"""
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None)


def to_iso(dt: datetime | None) -> str | None:
    """naive datetime 视为 UTC 并补时区偏移；aware datetime 原样输出。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "+00:00"
    return dt.isoformat()


def to_epoch(dt: datetime) -> float:
    """naive datetime 视为 UTC 转 Unix 秒。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).timestamp()
    return dt.timestamp()
