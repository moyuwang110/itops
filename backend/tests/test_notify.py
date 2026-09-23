"""AC-8 / TR-11.1：飞书/企微签名、消息结构、错误透传、超长截断。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.exceptions import IntegrationError
from app.integrations.notify.feishu import FeishuChannel
from app.integrations.notify.wecom import WeComChannel
from app.integrations.notify.render import build_notify_view, render_markdown

VIEW = {
    "title": "CPU utilization > 90%",
    "severity": "严重",
    "host": "web01",
    "status": "problem",
    "time": "2026-09-22 10:00:00",
    "root_causes": ["CPU 饱和（置信度 高）"],
    "evidence": ["[metric] CPU 使用率 峰值 98% @10:02"],
    "remediation": ["扩容或迁移热点进程", "检查异常进程"],
    "impact": "接口响应变慢",
    "link": "http://itops/alerts/1",
}


def test_feishu_signature(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1700000000)
    ch = FeishuChannel({
        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        "secret": "AAA",
    })
    url = ch._signed_url()
    q = parse_qs(urlparse(url).query)
    assert q["timestamp"][0] == "1700000000"
    sign = q["sign"][0]
    string_to_sign = "1700000000\nAAA".encode()
    expect = base64.b64encode(
        hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
    ).decode()
    assert sign == expect


def test_wecom_signature(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1700000000)
    ch = WeComChannel({
        "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=k",
        "secret": "SEC123",
    })
    url = ch._signed_url()
    q = parse_qs(urlparse(url).query)
    sign = q["sign"][0]
    expect_raw = hmac.new(
        "SEC123".encode(), "1700000000\nSEC123".encode(), hashlib.sha256
    ).digest()
    # parse_qs 已把 %3D 解码回 '='，直接比对 base64 摘要
    assert sign == base64.b64encode(expect_raw).decode()


async def test_feishu_card_structure(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200
        text = "{}"

        def json(self):
            return {"errcode": 0}

    class _HTTP:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *x):
            return None

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _HTTP)
    monkeypatch.setattr(time, "time", lambda: 1700000000)
    ch = FeishuChannel({"webhook_url": "http://feishu/hook", "secret": "s"})
    await ch.send_report(VIEW)
    payload = captured["json"]
    assert payload["msg_type"] == "interactive"
    card = payload["card"]
    assert card["header"]["template"] == "red"
    md = card["elements"][0]["text"]["content"]
    assert "CPU 饱和" in md and "web01" in md
    assert any(a.get("url") == "http://itops/alerts/1"
               for a in card["elements"][-1]["actions"])


async def test_wecom_payload_and_error(monkeypatch):
    captured = {}

    class _Resp:
        def __init__(self, code):
            self.status_code = 200
            self.text = "{}"
            self._code = code

        def json(self):
            return {"errcode": self._code, "errmsg": "invalid webhook"}

    class _HTTP:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *x):
            return None

        async def post(self, url, json=None):
            captured["json"] = json
            return _Resp(99993)

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _HTTP)
    ch = WeComChannel({"webhook_url": "http://wecom/hook"})
    with pytest.raises(IntegrationError):
        await ch.send_report(VIEW)
    assert captured["json"]["msgtype"] == "markdown"
    assert "处置建议" in captured["json"]["markdown"]["content"]


def test_truncation():
    view = {**VIEW, "remediation": ["x" * 5000]}
    md = render_markdown(view, max_len=1000)
    assert len(md) <= 1050
    assert "截断" in md


def test_notify_link_uses_hash_route():
    """M5：前端为 hash 路由，卡片链接必须包含 /#/ 前缀。"""
    from app.services.notify_service import build_link
    link = build_link(42)
    assert link.endswith("/#/alerts/42")
    assert "/alerts/42" not in link.replace("/#/alerts/42", "")


def test_view_build_from_result():
    result = {
        "root_causes": [{"cause": "磁盘满", "confidence": "高", "reason": "r"}],
        "evidence": [{"type": "log", "ref": "10:00 graylog", "summary": "No space"}],
        "remediation": [{"step": "清理日志"}],
        "impact": "写入失败",
    }
    view = build_notify_view(
        {"title": "disk full", "host": "db01", "severity": "灾难",
         "status": "problem", "occurred_at": "t"},
        result, "http://x/1",
    )
    assert view["root_causes"] == ["磁盘满（置信度 高）"]
    assert view["evidence"] == ["[log] No space"]
    assert view["remediation"] == ["清理日志"]
