"""日志工具：嵌套字段读取、级别猜测。"""
from __future__ import annotations

from typing import Any


def deep_get(data: dict[str, Any], dotted_key: str, default: Any = "") -> Any:
    cur: Any = data
    for part in dotted_key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def split_keywords(text: str) -> list[str]:
    """多关键词切分：逗号（含中文逗号）或空白分隔，任一匹配（OR 语义）。"""
    import re as _re
    return [w.strip() for w in _re.split(r"[,\s，]+", text or "") if w.strip()]


def quote_term(word: str) -> str:
    return '"%s"' % word.replace('"', "").strip()


def or_expression(words: list[str]) -> str:
    return "(" + " OR ".join(quote_term(w) for w in words) + ")"


def loki_or_filter(words: list[str]) -> str:
    import re as _re
    escaped = [_re.escape(w) for w in words if w.strip()]
    return '|~ "(?i:%s)"' % "|".join(escaped)


def guess_level(text: str) -> str:
    low = text.lower()
    for lv in ("fatal", "panic", "error", "warn", "info", "debug", "trace"):
        if lv in low:
            if lv == "warn":
                return "warning"
            if lv == "panic":
                return "fatal"
            return lv
    return ""
