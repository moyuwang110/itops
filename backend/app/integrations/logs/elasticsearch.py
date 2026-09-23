"""Elasticsearch (ELK) _search API 适配。"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

import httpx

from app.integrations.logs.log_helpers import deep_get, guess_level
from app.integrations.logs.base import LogPlatformClient, LogQuery


class ElasticsearchClient(LogPlatformClient):
    platform = "elasticsearch"

    def __init__(self, conf: dict) -> None:
        super().__init__(conf)
        url = (conf.get("url") or "").rstrip("/")
        if not url:
            raise self._error("Elasticsearch 地址未配置")
        self.url = url
        self.index = conf.get("index") or conf.get("index_pattern") or "filebeat-*"
        self.host_field = conf.get("host_field") or "host.name"
        self.message_field = conf.get("message_field") or "message"
        self.ts_field = conf.get("timestamp_field") or "@timestamp"
        self.username = conf.get("username", "")
        self.password = conf.get("password", "")
        self.api_key = conf.get("api_key", "")
        self.verify_ssl = bool(conf.get("verify_ssl", True))

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"
        elif self.username:
            raw = f"{self.username}:{self.password}".encode()
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()
        return headers

    def _query_string(self, q: LogQuery) -> str:
        from app.integrations.logs.log_helpers import or_expression, split_keywords
        parts: list[str] = []
        words = q.keywords if q.keywords is not None else split_keywords(q.keyword)
        if words:
            parts.append(or_expression(words))
        elif q.keyword.strip():
            parts.append(f"({q.keyword.strip()})")
        if q.host.strip():
            parts.append(f'{self.host_field}:"{q.host.strip()}"')
        return " AND ".join(parts)

    async def query(self, q: LogQuery) -> list[dict]:
        body: dict[str, Any] = {
            "size": min(q.limit, 500),
            "sort": [{self.ts_field: {"order": "asc"}}],
            "query": {
                "bool": {
                    "filter": [
                        {"range": {self.ts_field: {
                            "gte": _es_time(q.start_ts),
                            "lte": _es_time(q.end_ts),
                        }}},
                    ],
                }
            },
        }
        qs = self._query_string(q)
        if qs:
            body["query"]["bool"]["must"] = [{"query_string": {"query": qs}}]

        try:
            async with httpx.AsyncClient(verify=self.verify_ssl,
                                        timeout=self.timeout) as http:
                resp = await http.post(
                    f"{self.url}/{self.index}/_search",
                    json=body, headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise self._error(f"请求 Elasticsearch 失败: {exc}") from exc
        if resp.status_code != 200:
            raise self._error(f"HTTP {resp.status_code}", resp.text[:300])
        try:
            data = resp.json()
        except ValueError as exc:
            raise self._error("返回非 JSON", resp.text[:300]) from exc

        rows: list[dict] = []
        for hit in data.get("hits", {}).get("hits", []):
            src = hit.get("_source", {}) or {}
            ts = _es_ts_to_epoch(deep_get(src, self.ts_field))
            host = deep_get(src, self.host_field) or src.get("host") or ""
            message = deep_get(src, self.message_field) or ""
            level = (deep_get(src, "log.level") or deep_get(src, "level")
                     or guess_level(str(message)))
            source = (deep_get(src, "log.file.path") or deep_get(src, "source")
                      or self.index)
            rows.append(self.normalize(
                ts=ts,
                host=str(host),
                source=str(source),
                level=str(level or ""),
                message=str(message),
                raw=src,
            ))
        return rows


def _es_time(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")


def _es_ts_to_epoch(value: Any) -> int | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return int(value / 1000) if value > 10_000_000_000 else int(value)
    text = str(value).replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except ValueError:
        return None
