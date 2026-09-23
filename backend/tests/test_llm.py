"""AC-3/AC-6 / TR-8：LLM 请求拼装、降级链、JSON 容错解析。"""
from __future__ import annotations

import pytest

from app.core.exceptions import IntegrationError
from app.integrations.llm import LLMChain, LLMClient, parse_structured_json
from app.integrations.llm.parser import LLMParserError


# ---------- JSON 解析容错 ----------

def test_parse_plain_json():
    out = parse_structured_json('{"a": 1, "b": [2]}')
    assert out == {"a": 1, "b": [2]}


def test_parse_fenced_json():
    text = '好的，结果如下：\n```json\n{"root_causes": [], "impact": "x"}\n```\n以上'
    out = parse_structured_json(text)
    assert out["impact"] == "x"


def test_parse_text_with_json_inside():
    text = '前缀说明 {"evidence": [1,2], "ok": true} 后缀'
    out = parse_structured_json(text)
    assert out == {"evidence": [1, 2], "ok": True}


def test_parse_broken_raises():
    with pytest.raises(LLMParserError):
        parse_structured_json("这不是 JSON {a: b}")


# ---------- 请求拼装 ----------

class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._p


class _FakeHTTP:
    captured: dict = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *x):
        return None

    async def post(self, url, json=None, headers=None):
        _FakeHTTP.captured = {"url": url, "json": json, "headers": headers}
        return _Resp({
            "choices": [{"message": {"content": "pong"}}],
            "model": json["model"],
        })


async def test_request_assembly(monkeypatch):
    import httpx
    _FakeHTTP.captured = {}
    monkeypatch.setattr(httpx, "AsyncClient", _FakeHTTP)
    client = LLMClient("deepseek", {
        "base_url": "https://api.deepseek.com",
        "api_key": "sk-x", "model": "deepseek-chat", "temperature": 0.1,
    })
    out = await client.chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert out == "pong"
    cap = _FakeHTTP.captured
    assert cap["url"] == "https://api.deepseek.com/chat/completions"
    assert cap["headers"]["Authorization"] == "Bearer sk-x"
    assert cap["json"]["response_format"] == {"type": "json_object"}
    assert cap["json"]["model"] == "deepseek-chat"


async def test_minimax_no_response_format(monkeypatch):
    import httpx
    _FakeHTTP.captured = {}
    monkeypatch.setattr(httpx, "AsyncClient", _FakeHTTP)
    client = LLMClient("minimax", {"api_key": "mm", "model": "MiniMax-M1"})
    await client.chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert "response_format" not in _FakeHTTP.captured["json"]
    assert "minimax.io" in _FakeHTTP.captured["url"]


# ---------- 降级链 ----------

async def test_chain_fallback():
    calls = []

    class FakeClient:
        def __init__(self, provider, fail):
            self.provider = provider
            self.model = provider + "-model"
            self._fail = fail

        async def chat(self, messages, json_mode=False, max_tokens=None):
            calls.append(self.provider)
            if self._fail:
                raise IntegrationError(self.provider, "timeout")
            return "OK"

    chain = LLMChain([
        FakeClient("deepseek", True),
        FakeClient("doubao", False),
    ])
    resp = await chain.chat([])
    assert calls == ["deepseek", "doubao"]
    assert resp.provider == "doubao"
    assert resp.degraded_from == "deepseek"


async def test_chain_all_failed():
    class FakeClient:
        provider = "x"
        model = "m"

        async def chat(self, *a, **k):
            raise IntegrationError("x", "boom")

    chain = LLMChain([FakeClient(), FakeClient()])
    with pytest.raises(IntegrationError):
        await chain.chat([])
