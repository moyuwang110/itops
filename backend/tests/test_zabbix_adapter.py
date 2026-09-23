"""AC-2 / TR-6.1：Zabbix 适配器参数拼装与归一化（Mock JSON-RPC）。"""
from __future__ import annotations

import pytest

from app.core.exceptions import IntegrationError
from app.integrations.zabbix.client import ZabbixClient


@pytest.fixture
def client_zx():
    return ZabbixClient({"url": "http://zabbix.example", "api_token": "tok"})


async def test_search_hosts_normalized(client_zx, monkeypatch):
    captured = {}

    async def fake_call(method, params=None):
        captured["method"] = method
        captured["params"] = params
        return [
            {"hostid": "1", "host": "web01", "name": "Web-01", "status": "0",
             "interfaces": [{"ip": "10.0.0.1", "dns": "", "useip": "1"}]},
        ]

    monkeypatch.setattr(client_zx, "_call", fake_call)
    hosts = await client_zx.search_hosts(keyword="web", limit=5)
    assert captured["method"] == "host.get"
    assert captured["params"]["search"] == {"host": "web", "name": "web"}
    assert hosts == [{
        "host_id": "1", "host": "web01", "name": "Web-01",
        "ip": "10.0.0.1", "monitored": True,
    }]


async def test_history_sorted_ascending(client_zx, monkeypatch):
    async def fake_call(method, params=None):
        assert method == "history.get"
        assert params["history"] == 0
        assert params["time_from"] <= params["time_till"]
        return [
            {"clock": "300", "value": "3"},
            {"clock": "100", "value": "1"},
            {"clock": "200", "value": "2"},
        ]

    monkeypatch.setattr(client_zx, "_call", fake_call)
    points = await client_zx.history("123", 0, 100, 400)
    assert [p["ts"] for p in points] == [100, 200, 300]


async def test_items_and_problems(client_zx, monkeypatch):
    async def fake_call(method, params=None):
        if method == "item.get":
            return [{"itemid": "9", "name": "CPU 使用率", "key_": "cpu.util",
                     "value_type": "0", "units": "%", "lastvalue": "12",
                     "state": "0", "status": "0"}]
        if method == "problem.get":
            return [{"eventid": "77", "name": "磁盘满", "severity": "4",
                     "clock": "1700000000", "acknowledged": "0",
                     "hosts": [{"hostid": "1", "host": "db01", "name": "DB-01"}]}]
        return []

    monkeypatch.setattr(client_zx, "_call", fake_call)
    items = await client_zx.list_items("1")
    assert items[0]["item_id"] == "9"
    assert items[0]["value_type"] == 0
    problems = await client_zx.current_problems()
    assert problems[0]["event_id"] == "77"
    assert problems[0]["hosts"][0]["host"] == "db01"


async def test_rpc_error_raises_integration_error(client_zx, monkeypatch):
    class _Resp:
        status_code = 200
        text = '{"error":{}}'

        def json(self):
            return {"error": {"message": "Not authorized", "data": "no perm"}}

    class _FakeHTTP:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *x):
            return None

        async def post(self, *a, **k):
            return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeHTTP)
    with pytest.raises(IntegrationError):
        await client_zx._rpc("host.get", {}, auth="tok", retry_login=False)
