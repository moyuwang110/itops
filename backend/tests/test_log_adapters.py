"""AC-4 / TR-9.1：Graylog/Loki/ES 参数拼装与归一化（Mock HTTP）。"""
from __future__ import annotations

import pytest

from app.core.exceptions import ConfigMissingError, IntegrationError
from app.integrations.logs.base import LogQuery
from app.integrations.logs.graylog import GraylogClient
from app.integrations.logs.loki import LokiClient
from app.integrations.logs.elasticsearch import ElasticsearchClient


class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._p


class _FakeHTTP:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *x):
        return None

    async def get(self, url, params=None, headers=None, auth=None):
        self.calls.append(("GET", url, params))
        return _Resp(self.payload)

    async def post(self, url, json=None, headers=None):
        self.calls.append(("POST", url, json))
        return _Resp(self.payload)


@pytest.fixture
def q():
    return LogQuery(start_ts=1700000000, end_ts=1700003600,
                    host="web01", limit=20,
                    keywords=["error", "timeout"])


async def test_graylog(monkeypatch, q):
    payload = {"messages": [
        {"message": {
            "timestamp": "2023-11-14T22:13:20.000Z",
            "source": "web01", "level": 3, "message": "disk I/O error",
            "gl2_source_input": "stream-a",
        }},
    ]}
    fake = _FakeHTTP(payload)
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    client = GraylogClient({"url": "http://graylog", "username": "u",
                           "password": "p"})
    rows = await client.query(q)
    assert rows[0]["host"] == "web01"
    assert rows[0]["level"] == "error"
    assert rows[0]["message"] == "disk I/O error"
    assert rows[0]["source"] == "stream-a"
    method, url, params = fake.calls[0]
    assert url.endswith("/api/search/universal/absolute")
    assert '("error" OR "timeout") AND source:"web01"' == params["query"]
    assert params["limit"] == 20


async def test_loki(monkeypatch, q):
    payload = {"status": "success", "data": {"result": [
        {"stream": {"host": "web01", "job": "nginx", "level": "error"},
         "values": [["1700000000000000000", 'upstream timeout while reading']]},
    ]}}
    fake = _FakeHTTP(payload)
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    client = LokiClient({"url": "http://loki:3100"})
    rows = await client.query(q)
    assert rows[0]["host"] == "web01"
    assert rows[0]["level"] == "error"
    assert "upstream timeout" in rows[0]["message"]
    method, url, params = fake.calls[0]
    assert "/loki/api/v1/query_range" in url
    logql = params["query"]
    assert '{host="web01"}' in logql
    assert "error" in logql and "timeout" in logql


async def test_elasticsearch(monkeypatch, q):
    payload = {"hits": {"hits": [
        {"_source": {
            "@timestamp": "2023-11-14T22:13:20.000Z",
            "host": {"name": "web01"},
            "message": "connection refused",
            "log": {"level": "error", "file": {"path": "/var/log/app.log"}},
        }},
    ]}}
    fake = _FakeHTTP(payload)
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    client = ElasticsearchClient({"url": "http://es:9200", "index": "filebeat-*",
                                  "username": "elastic", "password": "secret"})
    rows = await client.query(q)
    assert rows[0]["host"] == "web01"
    assert rows[0]["level"] == "error"
    assert rows[0]["source"] == "/var/log/app.log"
    method, url, body = fake.calls[0]
    assert url.endswith("/filebeat-*/_search")
    qs = body["query"]["bool"]["must"][0]["query_string"]["query"]
    assert '("error" OR "timeout")' in qs
    assert 'host.name:"web01"' in qs
    assert body["size"] == 20


async def test_disabled_platform_rejected(client, auth_headers):
    # 未配置任何日志平台
    resp = await client.get(
        "/api/v1/logs/query", params={"platform": "loki", "keyword": "error"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "config_missing"


async def test_http_error_wrapped(monkeypatch, q):
    class _ErrHTTP(_FakeHTTP):
        async def get(self, *a, **k):
            return _Resp({"error": "denied"}, status=401)

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _ErrHTTP(None))
    with pytest.raises(IntegrationError):
        await LokiClient({"url": "http://loki"}).query(q)


def test_split_keywords_or_semantics():
    """m7：关键词按逗号或空白切分，OR 语义，中文逗号同样支持。"""
    from app.integrations.logs.log_helpers import split_keywords
    assert split_keywords("oom timeout,panic，崩溃 error") == [
        "oom", "timeout", "panic", "崩溃", "error"
    ]
    assert split_keywords("  ") == []
