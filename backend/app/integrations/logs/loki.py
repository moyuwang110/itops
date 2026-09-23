"""Loki HTTP API / LogQL 适配。"""
from __future__ import annotations

from typing import Any

import httpx

from app.integrations.logs.base import LogPlatformClient, LogQuery


class LokiClient(LogPlatformClient):
    platform = "loki"

    def __init__(self, conf: dict) -> None:
        super().__init__(conf)
        url = (conf.get("url") or "").rstrip("/")
        if not url:
            raise self._error("Loki 地址未配置")
        self.url = url
        self.host_label = conf.get("host_label") or "host"
        self.default_selector = conf.get("default_selector") or '{job=~".+"}'
        self.username = conf.get("username", "")
        self.password = conf.get("password", "")
        self.verify_ssl = bool(conf.get("verify_ssl", True))

    def _build_logql(self, q: LogQuery) -> str:
        from app.integrations.logs.log_helpers import loki_or_filter, split_keywords
        if q.host.strip():
            escaped = q.host.strip().replace('"', '\\"')
            selector = '{%s="%s"}' % (self.host_label, escaped)
        else:
            selector = self.default_selector
        words = q.keywords if q.keywords is not None else split_keywords(q.keyword)
        if words:
            return selector + " " + loki_or_filter(words)
        if q.keyword.strip():
            kw = q.keyword.strip().replace('"', '\\"')
            return selector + ' |= "%s"' % kw
        return selector

    async def query(self, q: LogQuery) -> list[dict]:
        params = {
            "query": self._build_logql(q),
            "start": str(q.start_ts * 1_000_000_000),
            "end": str(q.end_ts * 1_000_000_000),
            "limit": str(min(q.limit, 500)),
            "direction": "forward",
        }
        auth = (self.username, self.password) if self.username else None
        try:
            async with httpx.AsyncClient(verify=self.verify_ssl,
                                        timeout=self.timeout) as http:
                resp = await http.get(
                    f"{self.url}/loki/api/v1/query_range",
                    params=params,
                    auth=auth,
                )
        except httpx.HTTPError as exc:
            raise self._error(f"请求 Loki 失败: {exc}") from exc
        if resp.status_code != 200:
            raise self._error(f"HTTP {resp.status_code}", resp.text[:300])
        try:
            data = resp.json()
        except ValueError as exc:
            raise self._error("返回非 JSON", resp.text[:300]) from exc
        if data.get("status") != "success":
            raise self._error("Loki 返回状态异常", str(data)[:300])

        rows: list[dict] = []
        for stream in data.get("data", {}).get("result", []):
            labels: dict[str, Any] = stream.get("stream", {}) or {}
            for ts_ns, line in stream.get("values", []):
                try:
                    ts = int(ts_ns) // 1_000_000_000
                except (TypeError, ValueError):
                    ts = 0
                level = labels.get("level") or guess_level(line)
                rows.append(self.normalize(
                    ts=ts,
                    host=labels.get(self.host_label) or labels.get("host") or "",
                    source=labels.get("job") or labels.get("source") or "loki",
                    level=level,
                    message=line,
                    raw={"labels": labels, "line": line},
                ))
        rows.sort(key=lambda r: r["ts"])
        return rows


def guess_level(line: str) -> str:
    low = line.lower()
    for lv in ("fatal", "error", "warn", "info", "debug", "trace"):
        if lv in low:
            return "warning" if lv == "warn" else lv
    return ""
