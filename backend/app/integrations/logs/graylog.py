"""Graylog REST API 适配。"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

import httpx

from app.integrations.logs.base import LogPlatformClient, LogQuery


class GraylogClient(LogPlatformClient):
    platform = "graylog"

    def __init__(self, conf: dict) -> None:
        super().__init__(conf)
        url = (conf.get("url") or "").rstrip("/")
        if not url:
            raise self._error("Graylog 地址未配置")
        self.url = url
        self.username = conf.get("username", "")
        self.password = conf.get("password", "")
        self.token = conf.get("api_token", "")
        self.host_field = conf.get("host_field") or "source"
        self.verify_ssl = bool(conf.get("verify_ssl", True))

    def _headers(self) -> dict[str, str]:
        if self.token:
            # Graylog API token 以 token:token 形式 Basic 认证
            raw = f"{self.token}:token".encode()
            auth = base64.b64encode(raw).decode()
        else:
            raw = f"{self.username}:{self.password}".encode()
            auth = base64.b64encode(raw).decode()
        return {
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "X-Requested-By": "itops",
        }

    def _build_query(self, q: LogQuery) -> str:
        from app.integrations.logs.log_helpers import or_expression, split_keywords
        parts: list[str] = []
        words = q.keywords if q.keywords is not None else split_keywords(q.keyword)
        if words:
            parts.append(or_expression(words))
        elif q.keyword.strip():
            parts.append(f"({q.keyword.strip()})")
        if q.host.strip():
            parts.append(f'{self.host_field}:"{q.host.strip()}"')
        return " AND ".join(parts) or "*"

    async def query(self, q: LogQuery) -> list[dict]:
        frm = datetime.fromtimestamp(q.start_ts, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        to = datetime.fromtimestamp(q.end_ts, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        params = {
            "query": self._build_query(q),
            "from": frm,
            "to": to,
            "limit": min(q.limit, 500),
            "sort": "timestamp:asc",
            "decorate": "false",
        }
        try:
            async with httpx.AsyncClient(verify=self.verify_ssl,
                                        timeout=self.timeout) as http:
                resp = await http.get(
                    f"{self.url}/api/search/universal/absolute",
                    params=params, headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise self._error(f"请求 Graylog 失败: {exc}") from exc
        if resp.status_code != 200:
            raise self._error(f"HTTP {resp.status_code}", resp.text[:300])
        try:
            data = resp.json()
        except ValueError as exc:
            raise self._error("返回非 JSON", resp.text[:300]) from exc

        rows: list[dict] = []
        for item in data.get("messages", []):
            msg: dict[str, Any] = item.get("message", {}) or {}
            ts = _gray_ts(msg.get("timestamp"))
            rows.append(self.normalize(
                ts=ts,
                host=str(msg.get(self.host_field) or msg.get("source") or ""),
                source=str(msg.get("gl2_source_input") or msg.get("facility") or "graylog"),
                level=_syslog_level(msg.get("level")),
                message=str(msg.get("message") or ""),
                raw=msg,
            ))
        return rows


def _gray_ts(value: Any) -> int | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        # 毫秒
        return int(value / 1000) if value > 10_000_000_000 else int(value)
    text = str(value).replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except ValueError:
        return None


_SYSLOG = {0: "emergency", 1: "alert", 2: "critical", 3: "error",
           4: "warning", 5: "notice", 6: "informational", 7: "debug"}


def _syslog_level(value: Any) -> str:
    try:
        return _SYSLOG.get(int(value), str(value or ""))
    except (TypeError, ValueError):
        return str(value or "")
