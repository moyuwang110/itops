"""多供应商大模型适配（OpenAI 兼容协议）。"""
from app.integrations.llm.client import (
    PROVIDER_META,
    LLMClient,
    LLMResponse,
    LLMChain,
    provider_tester,
    build_chain,
)
from app.integrations.llm.parser import LLMParserError, parse_structured_json

PROVIDER_TESTERS = {
    name: (lambda conf, n=name: provider_tester({**conf, "_provider": n}))
    for name in PROVIDER_META
}

__all__ = [
    "PROVIDER_META",
    "LLMClient",
    "LLMResponse",
    "LLMChain",
    "provider_tester",
    "build_chain",
    "parse_structured_json",
    "LLMParserError",
    "PROVIDER_TESTERS",
]
