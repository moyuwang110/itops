"""大模型供应商客户端与降级链。

四家供应商均提供 OpenAI 兼容 Chat Completions：
- DeepSeek:   https://api.deepseek.com
- 豆包(方舟): https://ark.cn-beijing.volces.com/api/v3
- 通义千问:   https://dashscope.aliyuncs.com/compatible-mode/v1
- MiniMax:    https://api.minimax.cn/v1
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError

logger = logging.getLogger(__name__)

# 推理模型（如 MiniMax-M1/M3）会在正文中输出 <think>...</think> 推理过程，需剥离
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
# 处理被 max_tokens 截断、未闭合的 <think>
_UNCLOSED_THINK_RE = re.compile(r"<think>.*$", re.DOTALL | re.IGNORECASE)

PROVIDER_META: dict[str, dict[str, str]] = {
    "deepseek": {
        "label": "DeepSeek",
        "default_base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "json_mode": "response_format",
    },
    "doubao": {
        "label": "豆包（火山方舟）",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-seed-1-6-250615",
        "json_mode": "response_format",
    },
    "qwen": {
        "label": "通义千问（DashScope）",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "json_mode": "response_format",
    },
    "minimax": {
        "label": "MiniMax",
        "default_base_url": "https://api.minimax.cn/v1",
        "default_model": "MiniMax-M1",
        "json_mode": "prompt",
    },
}


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    degraded_from: str = ""


class LLMClient:
    def __init__(self, provider: str, conf: dict[str, Any]) -> None:
        meta = PROVIDER_META.get(provider)
        if meta is None:
            raise IntegrationError("llm", f"不支持的大模型供应商: {provider}")
        self.provider = provider
        self.meta = meta
        self.base_url = (conf.get("base_url") or meta["default_base_url"]).rstrip("/")
        self.api_key = conf.get("api_key", "")
        self.model = conf.get("model") or meta["default_model"]
        self.temperature = float(conf.get("temperature", 0.2))
        self.timeout = float(conf.get("timeout") or settings.http_timeout)
        if not self.api_key:
            raise IntegrationError(provider, "API Key 未配置")

    def _endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    async def chat(self, messages: list[dict[str, str]],
                   json_mode: bool = False,
                   max_tokens: int | None = None) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if json_mode and self.meta["json_mode"] == "response_format":
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                resp = await http.post(self._endpoint(), json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise IntegrationError(self.provider, f"请求失败: {exc}") from exc

        if resp.status_code != 200:
            raise IntegrationError(
                self.provider,
                f"HTTP {resp.status_code}",
                detail=resp.text[:500],
            )
        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise IntegrationError(
                self.provider, "响应结构异常，无法解析 choices[0].message.content",
                detail=resp.text[:500],
            ) from exc
        if not content:
            raise IntegrationError(self.provider, "模型返回为空")
        # 剥离推理模型的 <think> 标签内容，避免干扰 JSON 解析与报告展示
        content = _THINK_RE.sub("", content)
        content = _UNCLOSED_THINK_RE.sub("", content).strip()
        logger.info("LLM 调用成功 provider=%s model=%s chars=%d",
                    self.provider, self.model, len(content))
        return content


class LLMChain:
    """按顺序尝试多个供应商，首个成功即返回；记录降级来源。"""

    def __init__(self, clients: list[LLMClient]) -> None:
        if not clients:
            raise IntegrationError("llm", "未配置可用的大模型供应商")
        self.clients = clients

    async def chat(self, messages: list[dict[str, str]],
                   json_mode: bool = False,
                   max_tokens: int | None = None) -> LLMResponse:
        errors: list[str] = []
        first = self.clients[0].provider
        for idx, client in enumerate(self.clients):
            try:
                content = await client.chat(messages, json_mode=json_mode,
                                            max_tokens=max_tokens)
                return LLMResponse(
                    content=content,
                    provider=client.provider,
                    model=client.model,
                    degraded_from="" if idx == 0 else first,
                )
            except IntegrationError as exc:
                logger.warning("LLM 供应商失败 provider=%s: %s",
                               client.provider, exc.message)
                errors.append(f"{client.provider}: {exc.message}")
        raise IntegrationError(
            "llm",
            "全部大模型供应商调用失败：" + " | ".join(errors),
        )


def build_chain(items: list[tuple[str, dict[str, Any]]]) -> LLMChain:
    """items: [(provider, settings), ...] 已按默认/优先级排序。"""
    clients = [LLMClient(provider, conf) for provider, conf in items]
    return LLMChain(clients)


async def provider_tester(conf: dict[str, Any]) -> tuple[bool, str]:
    provider = conf.get("_provider", "")
    if provider not in PROVIDER_META:
        return False, f"未知供应商: {provider}"
    try:
        client = LLMClient(provider, conf)
        content = await client.chat(
            [{"role": "user", "content": "ping，请仅回复 pong"}],
            max_tokens=16,
        )
        return True, f"连接成功，模型 {client.model} 应答: {content[:40]}"
    except IntegrationError as exc:
        return False, exc.message
