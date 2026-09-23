"""大模型结构化 JSON 输出解析（容错）。"""
from __future__ import annotations

import json
import re
from typing import Any


class LLMParserError(ValueError):
    pass


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _strip_fence(text: str) -> str:
    match = _FENCE_RE.search(text)
    return match.group(1).strip() if match else text.strip()


def _extract_balanced_object(text: str) -> str | None:
    """从可能包含解释文字的文本中提取第一个平衡的花括号对象。"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_structured_json(text: str) -> dict[str, Any]:
    if not text or not text.strip():
        raise LLMParserError("模型输出为空")

    candidates = [text]
    unfenced = _strip_fence(text)
    if unfenced != text.strip():
        candidates.insert(0, unfenced)

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        obj = _extract_balanced_object(candidate)
        if obj:
            try:
                data = json.loads(obj)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    raise LLMParserError("无法从模型输出中解析出合法 JSON 对象")
