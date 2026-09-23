"""AC-5/AC-6 / TR-10：分析上下文聚合、降级、失败重试、并发保护。"""
from __future__ import annotations

import pytest

from app.core.database import AsyncSessionLocal
from app.integrations.llm import LLMChain, LLMResponse
from app.integrations.zabbix.client import ZabbixClient
from app.integrations.logs.loki import LokiClient
from app.models.alert import Alert
from app.models.constants import ANALYSIS_FAILED, ANALYSIS_SUCCESS
from app.models.report import Report
from sqlalchemy import select

GOOD_RESULT = """```json
{
  "root_causes": [
    {"cause": "异常进程占满 CPU", "confidence": "高",
     "reason": "CPU 在 10:02 达 98%，同时日志出现大量 timeout"}
  ],
  "evidence": [
    {"type": "metric", "ref": "CPU 使用率", "summary": "峰值 98% @10:02，窗口变化 +85%"},
    {"type": "log", "ref": "10:02 nginx(loki)", "summary": "upstream timeout 反复出现"}
  ],
  "impact": "Web 接口响应变慢，部分请求超时",
  "remediation": ["定位并重启异常进程", "必要时扩容计算资源"],
  "prevention": ["为该主机增加 CPU 告警阈值与进程级监控"]
}
```"""

PROBLEM = {
    "event_id": "EVT-A1", "host": "web01", "trigger": "CPU utilization > 90%",
    "severity": "严重", "status": "PROBLEM",
    "datetime": "2026-09-22 10:05:00",
}


def _zabbix_config():
    return {"type": "zabbix", "provider": "zabbix", "name": "Zabbix",
            "enabled": True, "settings": {"url": "http://zbx", "api_token": "t"}}


def _llm_config(provider="deepseek", default=True, priority=1):
    return {"type": "llm", "provider": provider, "name": provider,
            "enabled": True, "is_default": default, "priority": priority,
            "settings": {"api_key": "sk-x", "model": f"{provider}-model"}}


def _loki_config():
    return {"type": "log_platform", "provider": "loki", "name": "Loki",
            "enabled": True, "settings": {"url": "http://loki"}}


@pytest.fixture
def patch_zabbix(monkeypatch):
    async def search_hosts(self, keyword="", limit=100):
        return [{"host_id": "11", "host": "web01", "name": "web01",
                 "ip": "10.0.0.1", "monitored": True}]

    async def list_items(self, host_id, keyword="", limit=500):
        return [
            {"item_id": "i-cpu", "name": "CPU 使用率", "key_": "cpu.util",
             "value_type": 0, "units": "%", "last_value": "98", "enabled": True},
            {"item_id": "i-mem", "name": "可用内存", "key_": "vm.memory.available",
             "value_type": 0, "units": "B", "last_value": "1G", "enabled": True},
        ]

    async def history(self, item_id, value_type, time_from, time_till, limit=1000):
        return [{"ts": time_from + 60 * i, "value": 10.0 + i * 8.0}
                for i in range(10)]

    monkeypatch.setattr(ZabbixClient, "search_hosts", search_hosts)
    monkeypatch.setattr(ZabbixClient, "list_items", list_items)
    monkeypatch.setattr(ZabbixClient, "history", history)


@pytest.fixture
def patch_loki(monkeypatch):
    async def query(self, q):
        return [self.normalize(
            ts=q.start_ts + 120, host="web01", source="nginx", level="error",
            message="upstream timeout while reading response",
            raw={"line": "x"},
        )]

    monkeypatch.setattr(LokiClient, "query", query)


async def _ingest(client, token, payload):
    r = await client.post("/api/v1/webhooks/zabbix", json=payload,
                          headers={"X-Webhook-Token": token})
    assert r.status_code == 200, r.text
    return r.json()["alert_id"]


async def _disable_auto(client, auth_headers):
    await client.put("/api/v1/configs/system", json={"auto_analysis": False},
                     headers=auth_headers)


async def _analyze_and_poll(client, auth_headers, alert_id, expected="success",
                            rounds=40):
    """触发后台分析并轮询到终态。expected: success/failed。"""
    import anyio
    from app.models.constants import ANALYSIS_FAILED, ANALYSIS_SUCCESS
    target = ANALYSIS_SUCCESS if expected == "success" else ANALYSIS_FAILED
    r = await client.post(f"/api/v1/alerts/{alert_id}/analyze",
                          headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["analysis_status"] == "queued"
    detail = {}
    status = None
    for _ in range(rounds):
        await anyio.sleep(0.05)
        detail = (await client.get(f"/api/v1/alerts/{alert_id}",
                                   headers=auth_headers)).json()
        status = detail["analysis_status"]
        if status in (ANALYSIS_SUCCESS, ANALYSIS_FAILED):
            break
    assert status == target, f"期望 {target}，实际 {status}: {detail.get('analysis_error')}"
    return detail


async def test_full_analysis_with_evidence(client, auth_headers, monkeypatch,
                                           patch_zabbix, patch_loki):
    await _disable_auto(client, auth_headers)
    await client.post("/api/v1/configs", json=_zabbix_config(), headers=auth_headers)
    await client.post("/api/v1/configs", json=_llm_config(), headers=auth_headers)
    await client.post("/api/v1/configs", json=_loki_config(), headers=auth_headers)

    captured = {}

    async def fake_chat(self, messages, json_mode=False, max_tokens=None):
        captured["messages"] = messages
        captured["json_mode"] = json_mode
        return LLMResponse(content=GOOD_RESULT, provider="deepseek",
                           model="deepseek-model")

    monkeypatch.setattr(LLMChain, "chat", fake_chat)

    alert_id = await _ingest(client, "test-webhook-token", PROBLEM)
    detail = await _analyze_and_poll(client, auth_headers, alert_id)
    assert detail["analysis_status"] == ANALYSIS_SUCCESS
    report = detail["report"]
    assert report["provider"] == "deepseek"
    assert report["result"]["root_causes"][0]["cause"] == "异常进程占满 CPU"
    # 指标证据
    series = report["metric_context"]["series"]
    assert {s["name"] for s in series} == {"CPU 使用率", "可用内存"}
    assert series[0]["stats"]["max"] > 0
    # 日志证据
    assert report["log_context"]["platforms"][0]["provider"] == "loki"
    assert "timeout" in report["log_context"]["logs"][0]["message"]
    # Prompt 含两类证据段
    user_content = captured["messages"][1]["content"]
    assert "【监控指标趋势】" in user_content
    assert "【相关日志】" in user_content
    assert captured["json_mode"] is True
    # Markdown 章节
    assert "证据链" in report["markdown"] and "处置建议" in report["markdown"]


async def test_empty_evidence_marked(client, auth_headers, monkeypatch):
    await _disable_auto(client, auth_headers)
    # 不配置 Zabbix 与任何日志平台
    await client.post("/api/v1/configs", json=_llm_config(), headers=auth_headers)
    captured = {}

    async def fake_chat(self, messages, json_mode=False, max_tokens=None):
        captured["messages"] = messages
        return LLMResponse(content=GOOD_RESULT, provider="deepseek",
                           model="deepseek-model")

    monkeypatch.setattr(LLMChain, "chat", fake_chat)
    alert_id = await _ingest(client, "test-webhook-token", PROBLEM)
    detail = await _analyze_and_poll(client, auth_headers, alert_id)
    assert detail["report"]["metric_context"]["available"] is False
    assert detail["report"]["log_context"]["logs"] == []
    content = captured["messages"][1]["content"]
    assert "无指标证据" in content and "无日志证据" in content


async def test_failure_then_retry(client, auth_headers, monkeypatch):
    await _disable_auto(client, auth_headers)
    await client.post("/api/v1/configs", json=_llm_config(), headers=auth_headers)
    calls = {"n": 0}

    async def flaky_chat(self, messages, json_mode=False, max_tokens=None):
        calls["n"] += 1
        if calls["n"] == 1:
            from app.core.exceptions import IntegrationError as IE
            raise IE("deepseek", "500 服务不可用")
        return LLMResponse(content=GOOD_RESULT, provider="deepseek",
                           model="deepseek-model")

    monkeypatch.setattr(LLMChain, "chat", flaky_chat)
    alert_id = await _ingest(client, "test-webhook-token", PROBLEM)

    detail = await _analyze_and_poll(client, auth_headers, alert_id,
                                     expected="failed")
    assert detail["analysis_status"] == ANALYSIS_FAILED
    assert "deepseek" in detail["analysis_error"]

    detail2 = await _analyze_and_poll(client, auth_headers, alert_id)
    assert detail2["analysis_status"] == ANALYSIS_SUCCESS
    assert detail2["analysis_times"] >= 2


async def test_degradation_recorded(client, auth_headers, monkeypatch):
    await _disable_auto(client, auth_headers)
    await client.post("/api/v1/configs", json=_llm_config("deepseek", True, 1),
                      headers=auth_headers)
    await client.post("/api/v1/configs", json=_llm_config("doubao", False, 2),
                      headers=auth_headers)

    async def degraded_chat(self, messages, json_mode=False, max_tokens=None):
        return LLMResponse(content=GOOD_RESULT, provider="doubao",
                           model="doubao-model", degraded_from="deepseek")

    monkeypatch.setattr(LLMChain, "chat", degraded_chat)
    alert_id = await _ingest(client, "test-webhook-token", PROBLEM)
    detail = await _analyze_and_poll(client, auth_headers, alert_id)
    report = detail["report"]
    assert report["provider"] == "doubao"
    assert report["degraded_from"] == "deepseek"


async def test_concurrent_analysis_guard(client, auth_headers, monkeypatch):
    import asyncio
    from app.services import analysis_service
    await _disable_auto(client, auth_headers)
    await client.post("/api/v1/configs", json=_llm_config(), headers=auth_headers)
    alert_id = await _ingest(client, "test-webhook-token", PROBLEM)

    import anyio

    async def slow_chat(self, messages, json_mode=False, max_tokens=None):
        await anyio.sleep(0.3)
        return LLMResponse(content=GOOD_RESULT, provider="deepseek",
                           model="deepseek-model")

    monkeypatch.setattr(LLMChain, "chat", slow_chat)

    async with AsyncSessionLocal() as db:
        results = await asyncio.gather(
            analysis_service.run_analysis(alert_id),
            analysis_service.run_analysis(alert_id),
            return_exceptions=True,
        )
    assert any(isinstance(r, analysis_service.AnalysisBusyError) for r in results)
    async with AsyncSessionLocal() as db:
        count = len((await db.execute(
            select(Report).where(Report.alert_id == alert_id)
        )).scalars().all())
        assert count == 1


async def test_busy_returns_409(client, auth_headers):
    await _disable_auto(client, auth_headers)
    from app.services import analysis_service
    alert_id = await _ingest(client, "test-webhook-token", PROBLEM)
    analysis_service._running.add(alert_id)
    try:
        r = await client.post(f"/api/v1/alerts/{alert_id}/analyze",
                              headers=auth_headers)
        assert r.status_code == 409
    finally:
        analysis_service._running.discard(alert_id)


async def test_json_repair_retry(client, auth_headers, monkeypatch):
    await _disable_auto(client, auth_headers)
    await client.post("/api/v1/configs", json=_llm_config(), headers=auth_headers)
    calls = {"n": 0}

    async def chat(self, messages, json_mode=False, max_tokens=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return LLMResponse(content="我认为原因是 {坏的 json", provider="deepseek",
                               model="m")
        return LLMResponse(content=GOOD_RESULT, provider="deepseek", model="m")

    monkeypatch.setattr(LLMChain, "chat", chat)
    alert_id = await _ingest(client, "test-webhook-token", PROBLEM)
    await _analyze_and_poll(client, auth_headers, alert_id)
    assert calls["n"] == 2


async def test_auto_trigger_after_webhook(client, auth_headers, monkeypatch,
                                          patch_zabbix):
    # 保持 auto_analysis=true（默认），Webhook 后自动出报告
    await client.post("/api/v1/configs", json=_zabbix_config(), headers=auth_headers)
    await client.post("/api/v1/configs", json=_llm_config(), headers=auth_headers)

    import anyio

    async def fake_chat(self, messages, json_mode=False, max_tokens=None):
        return LLMResponse(content=GOOD_RESULT, provider="deepseek",
                           model="deepseek-model")

    monkeypatch.setattr(LLMChain, "chat", fake_chat)
    alert_id = await _ingest(client, "test-webhook-token", PROBLEM)

    # 轮询等待后台任务完成
    status = None
    for _ in range(20):
        await anyio.sleep(0.05)
        detail = (await client.get(f"/api/v1/alerts/{alert_id}",
                                   headers=auth_headers)).json()
        status = detail["analysis_status"]
        if status in (ANALYSIS_SUCCESS, ANALYSIS_FAILED):
            break
    assert status == ANALYSIS_SUCCESS
    assert detail["report"] is not None


async def test_recover_stale_processing(client, auth_headers):
    """崩溃重启场景：processing 状态告警在启动回收后回到 pending。"""
    from app.models.constants import ANALYSIS_PENDING, ANALYSIS_PROCESSING
    from app.services import analysis_service
    await _disable_auto(client, auth_headers)
    alert_id = await _ingest(client, "test-webhook-token", PROBLEM)
    async with AsyncSessionLocal() as db:
        a = await db.get(Alert, alert_id)
        a.analysis_status = ANALYSIS_PROCESSING
        await db.commit()

    reset = await analysis_service.recover_stale()
    assert reset == 1
    async with AsyncSessionLocal() as db:
        a = await db.get(Alert, alert_id)
        assert a.analysis_status == ANALYSIS_PENDING
        assert "重置" in (a.analysis_error or "")
