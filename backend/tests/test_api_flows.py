"""接口链路补充：Zabbix 查询 API、报告列表/导出/时间筛选、仪表盘、手动推送、日志查询 API。"""
from __future__ import annotations

import anyio

from app.integrations.llm import LLMChain, LLMResponse
from app.integrations.logs.loki import LokiClient
from app.integrations.zabbix.client import ZabbixClient

from tests.test_analysis import (
    GOOD_RESULT, PROBLEM, _analyze_and_poll, _disable_auto,
    _llm_config, _loki_config, _zabbix_config,
)


async def test_zabbix_query_api(client, auth_headers, monkeypatch):
    await client.post("/api/v1/configs", json=_zabbix_config(), headers=auth_headers)

    async def search_hosts(self, keyword="", limit=100):
        return [{"host_id": "1", "host": "web01", "name": "web01",
                 "ip": "10.0.0.1", "monitored": True}]

    async def history(self, item_id, value_type, t1, t2, limit=1000):
        return [{"ts": t1, "value": 1.0}, {"ts": t1 + 60, "value": 2.0}]

    async def trend(self, item_id, value_type, t1, t2, limit=1000):
        return [{"ts": t1, "value_min": 0.5, "value_avg": 1.2, "value_max": 2.1}]

    monkeypatch.setattr(ZabbixClient, "search_hosts", search_hosts)
    monkeypatch.setattr(ZabbixClient, "history", history)
    monkeypatch.setattr(ZabbixClient, "trend", trend)

    hosts = await client.get("/api/v1/zabbix/hosts?keyword=web",
                             headers=auth_headers)
    assert hosts.status_code == 200
    assert hosts.json()[0]["host"] == "web01"

    hist = await client.get(
        "/api/v1/zabbix/history?item_id=i1&value_type=0&start=1700000000&end=1700000600",
        headers=auth_headers,
    )
    assert hist.status_code == 200
    assert [p["value"] for p in hist.json()["points"]] == [1.0, 2.0]

    tr = await client.get(
        "/api/v1/zabbix/trend?item_id=i1&value_type=0&start=1700000000&end=1700000600",
        headers=auth_headers,
    )
    assert tr.status_code == 200
    assert tr.json()["points"][0]["value_avg"] == 1.2


async def _make_report(client, auth_headers, monkeypatch, with_zabbix=False,
                       with_loki=False):
    await _disable_auto(client, auth_headers)
    if with_zabbix:
        await client.post("/api/v1/configs", json=_zabbix_config(),
                          headers=auth_headers)

        async def search_hosts(self, keyword="", limit=100):
            return [{"host_id": "1", "host": "web01", "name": "web01",
                     "ip": "", "monitored": True}]

        async def list_items(self, host_id, keyword="", limit=500):
            return [{"item_id": "i1", "name": "CPU 使用率", "key_": "cpu",
                     "value_type": 0, "units": "%", "last_value": "90",
                     "enabled": True}]

        async def history(self, item_id, vt, t1, t2, limit=1000):
            return [{"ts": t1 + 60 * i, "value": float(10 + i * 9)}
                    for i in range(8)]

        monkeypatch.setattr(ZabbixClient, "search_hosts", search_hosts)
        monkeypatch.setattr(ZabbixClient, "list_items", list_items)
        monkeypatch.setattr(ZabbixClient, "history", history)

    if with_loki:
        await client.post("/api/v1/configs", json=_loki_config(),
                          headers=auth_headers)

        async def lquery(self, q):
            return [self.normalize(q.start_ts, "web01", "nginx", "error",
                                   "upstream timeout", {})]

        monkeypatch.setattr(LokiClient, "query", lquery)

    await client.post("/api/v1/configs", json=_llm_config(), headers=auth_headers)

    async def fake_chat(self, messages, json_mode=False, max_tokens=None):
        return LLMResponse(content=GOOD_RESULT, provider="deepseek",
                           model="deepseek-model")

    monkeypatch.setattr(LLMChain, "chat", fake_chat)

    r = await client.post("/api/v1/webhooks/zabbix", json=PROBLEM,
                          headers={"X-Webhook-Token": "test-webhook-token"})
    alert_id = r.json()["alert_id"]
    detail = await _analyze_and_poll(client, auth_headers, alert_id)
    return alert_id, detail["report"]["id"]


async def test_report_list_export_and_dashboard(client, auth_headers, monkeypatch):
    alert_id, report_id = await _make_report(
        client, auth_headers, monkeypatch, with_zabbix=True
    )

    listed = await client.get("/api/v1/reports", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["alert"]["host"] == "web01"

    export = await client.get(f"/api/v1/reports/{report_id}/export",
                              headers=auth_headers)
    assert export.status_code == 200
    md = export.text
    for section in ("可能根因", "证据链", "影响范围", "处置建议", "预防建议",
                    "指标上下文摘要", "日志证据摘要"):
        assert section in md
    assert "attachment" in export.headers["content-disposition"]

    dash = await client.get("/api/v1/dashboard/summary", headers=auth_headers)
    body = dash.json()
    assert body["total_24h"] == 1
    assert body["analysis"]["success"] == 1
    assert body["analysis"]["success_rate"] == 100.0
    kinds = {i["type"] for i in body["integrations"]}
    assert {"zabbix", "llm"} <= kinds
    assert len(body["latest_alerts"]) == 1


async def test_report_list_time_filter(client, auth_headers, monkeypatch):
    await _make_report(client, auth_headers, monkeypatch)
    # PROBLEM 发生于 2026-09-22 10:05 UTC（naive 输入按 UTC 存储）
    in_range = await client.get(
        "/api/v1/reports",
        params={"start": "2026-09-22T00:00:00", "end": "2026-09-23T00:00:00"},
        headers=auth_headers,
    )
    assert in_range.json()["total"] == 1
    out_range = await client.get(
        "/api/v1/reports", params={"start": "2026-09-23T00:00:00"},
        headers=auth_headers,
    )
    assert out_range.json()["total"] == 0
    # 带时区偏移的入参同样折算为 UTC
    tz_param = await client.get(
        "/api/v1/reports",
        params={"start": "2026-09-22T18:10:00+08:00",
                "end": "2026-09-22T18:10:00+08:00"},
        headers=auth_headers,
    )
    assert tz_param.json()["total"] == 0


async def test_logs_query_api(client, auth_headers, monkeypatch):
    await client.post("/api/v1/configs", json=_loki_config(), headers=auth_headers)

    async def lquery(self, q):
        return [self.normalize(q.start_ts, "web01", "nginx", "error",
                               "boom", {})]

    monkeypatch.setattr(LokiClient, "query", lquery)
    platforms = await client.get("/api/v1/logs/platforms", headers=auth_headers)
    assert platforms.json()[0]["provider"] == "loki"

    resp = await client.get(
        "/api/v1/logs/query",
        params={"platform": "loki", "keyword": "error", "host": "web01",
                "start": "2026-09-22T09:00:00", "end": "2026-09-22T11:00:00"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["logs"][0]["message"] == "boom"


async def test_manual_notify_push(client, auth_headers, monkeypatch):
    from app.integrations.notify import feishu as feishu_mod

    _, report_id = await _make_report(client, auth_headers, monkeypatch)
    await client.post("/api/v1/configs", json={
        "type": "notify_channel", "provider": "feishu", "name": "飞书",
        "enabled": True,
        "settings": {"webhook_url": "http://feishu/hook/123"},
    }, headers=auth_headers)

    sent = {}

    async def fake_send_report(self, view):
        sent["view"] = view

    monkeypatch.setattr(feishu_mod.FeishuChannel, "send_report", fake_send_report)

    r = await client.post(f"/api/v1/reports/{report_id}/notify",
                          json={"channels": ["feishu"]}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["channel"] == "feishu"
    assert sent["view"]["host"] == "web01"

    # 无启用渠道时的提示
    r2 = await client.post(f"/api/v1/reports/{report_id}/notify",
                           json={"channels": ["wecom"]}, headers=auth_headers)
    assert r2.status_code == 400
    assert r2.json()["code"] == "no_channel"
