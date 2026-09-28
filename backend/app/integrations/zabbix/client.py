"""Zabbix JSON-RPC 客户端（兼容 6.0 / 7.0）。"""
from __future__ import annotations

import itertools
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError

logger = logging.getLogger(__name__)

# 共享 httpx 客户端池：按 verify_ssl 分组复用，避免每次 RPC 重新建连/TLS 握手。
# httpx 不支持 per-request verify，因此按配置分组维护客户端。
_shared_clients: dict[bool, httpx.AsyncClient] = {}


def _get_http_client(verify_ssl: bool) -> httpx.AsyncClient:
    client = _shared_clients.get(verify_ssl)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(verify=verify_ssl)
        _shared_clients[verify_ssl] = client
    return client


async def close_shared_clients() -> None:
    """关闭所有共享 httpx 客户端（应用停止时调用）。"""
    for client in _shared_clients.values():
        if not client.is_closed:
            await client.aclose()
    _shared_clients.clear()


class ZabbixClient:
    def __init__(self, conf: dict[str, Any]) -> None:
        url = (conf.get("url") or "").rstrip("/")
        if not url:
            raise IntegrationError("zabbix", "Zabbix URL 未配置")
        self.base_url = url
        if not self.base_url.endswith("api_jsonrpc.php"):
            self.base_url = f"{self.base_url}/api_jsonrpc.php"
        self.username = conf.get("username", "")
        self.password = conf.get("password", "")
        self.api_token = conf.get("api_token", "")
        self.verify_ssl = bool(conf.get("verify_ssl", True))
        self._token: str | None = self.api_token or None
        self._ids = itertools.count(1)

    # ---------- 底层 ----------

    async def _rpc(self, method: str, params: dict[str, Any] | None = None,
                   auth: str | None = None, retry_login: bool = True) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": next(self._ids),
        }
        if auth:
            payload["auth"] = auth
        headers = {"Content-Type": "application/json-rpc"}
        http = _get_http_client(self.verify_ssl)
        try:
            resp = await http.post(
                self.base_url, json=payload, headers=headers,
                timeout=settings.http_timeout,
            )
        except httpx.HTTPError as exc:
            raise IntegrationError("zabbix", f"请求 Zabbix 失败: {exc}") from exc

        if resp.status_code != 200:
            raise IntegrationError(
                "zabbix",
                f"Zabbix HTTP {resp.status_code}",
                detail=resp.text[:500],
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise IntegrationError("zabbix", "Zabbix 返回非 JSON 内容",
                                   detail=resp.text[:500]) from exc
        if "error" in data:
            err = data["error"]
            msg = f"{err.get('message', '')}: {err.get('data', '')}"
            # token 过期时尝试重新登录一次
            if (retry_login and not self.api_token and auth
                    and ("re-login" in msg or "session" in msg.lower()
                         or "not authorized" in msg.lower())):
                self._token = None
                return await self._rpc(method, params, auth=await self._login(),
                                       retry_login=False)
            raise IntegrationError("zabbix", f"Zabbix API 错误: {msg}")
        return data.get("result")

    async def _login(self) -> str:
        if self._token:
            return self._token
        if self.api_token:
            self._token = self.api_token
            return self._token
        if not (self.username and self.password):
            raise IntegrationError("zabbix", "需配置 API Token 或用户名/密码")
        result = await self._rpc(
            "user.login",
            {"username": self.username, "password": self.password},
        )
        if not isinstance(result, str) or not result:
            raise IntegrationError("zabbix", "Zabbix 登录失败：未返回 token")
        self._token = result
        return result

    async def _call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        return await self._rpc(method, params, auth=await self._login())

    # ---------- 连通性 ----------

    async def test_connection(self) -> tuple[bool, str]:
        try:
            hosts = await self.search_hosts(limit=1)
            return True, f"连接成功，可访问主机 {len(hosts)} 台（采样正常）"
        except IntegrationError as exc:
            return False, exc.message

    # ---------- 业务查询 ----------

    async def search_hosts(self, keyword: str = "", limit: int = 100) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "output": ["hostid", "host", "name", "status"],
            "selectInterfaces": ["ip", "dns", "useip"],
            "limit": limit,
        }
        if keyword:
            params["search"] = {"host": keyword, "name": keyword}
            params["searchByAny"] = True
        rows = await self._call("host.get", params)
        return [self._norm_host(r) for r in (rows or [])]

    @staticmethod
    def _norm_host(row: dict[str, Any]) -> dict[str, Any]:
        interfaces = row.get("interfaces") or []
        ip = ""
        if interfaces:
            itf = interfaces[0]
            ip = itf.get("ip") if itf.get("useip") == "1" else itf.get("dns")
        return {
            "host_id": row.get("hostid"),
            "host": row.get("host"),
            "name": row.get("name"),
            "ip": ip or "",
            "monitored": str(row.get("status")) == "0",
        }

    async def list_items(self, host_id: str, keyword: str = "",
                         limit: int = 500) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "hostids": host_id,
            "output": ["itemid", "name", "key_", "value_type", "units",
                       "lastvalue", "state", "status"],
            "sortfield": "name",
            "limit": limit,
        }
        if keyword:
            params["search"] = {"name": keyword}
        rows = await self._call("item.get", params)
        out = []
        for r in rows or []:
            out.append({
                "item_id": r.get("itemid"),
                "name": r.get("name"),
                "key_": r.get("key_"),
                "value_type": int(r.get("value_type", 0)),
                "units": r.get("units", ""),
                "last_value": r.get("lastvalue", ""),
                "enabled": str(r.get("status")) == "0",
            })
        return out

    async def history(self, item_id: str, value_type: int,
                      time_from: int, time_till: int,
                      limit: int = 1000) -> list[dict[str, Any]]:
        """返回升序时间序列 [{ts, value}]，ts 为秒级 Unix 时间戳。"""
        params = {
            "history": value_type,
            "itemids": item_id,
            "time_from": int(time_from),
            "time_till": int(time_till),
            "output": "extend",
            "sortfield": "clock",
            "sortorder": "ASC",
            "limit": limit,
        }
        rows = await self._call("history.get", params)
        points: list[dict[str, Any]] = []
        for r in rows or []:
            try:
                value = float(r.get("value", 0))
            except (TypeError, ValueError):
                continue
            points.append({"ts": int(r["clock"]), "value": value})
        points.sort(key=lambda p: p["ts"])
        return points

    async def trend(self, item_id: str, value_type: int,
                    time_from: int, time_till: int,
                    limit: int = 1000) -> list[dict[str, Any]]:
        history_type = 0 if int(value_type) == 0 else 3
        params = {
            "itemids": item_id,
            "time_from": int(time_from),
            "time_till": int(time_till),
            "output": ["clock", "num", "value_min", "value_avg", "value_max"],
            "limit": limit,
        }
        rows = await self._call(f"trend{history_type}.get", params)
        points = []
        for r in rows or []:
            points.append({
                "ts": int(r["clock"]),
                "value_min": float(r.get("value_min", 0)),
                "value_avg": float(r.get("value_avg", 0)),
                "value_max": float(r.get("value_max", 0)),
            })
        points.sort(key=lambda p: p["ts"])
        return points

    async def current_problems(self, limit: int = 50, host: str | None = None,
                               severities: list[int] | None = None) -> list[dict[str, Any]]:
        params = {
            "output": "extend",
            "recent": True,
            "sortfield": "eventid",
            "sortorder": "DESC",
            "limit": limit,
        }
        # 级别筛选：problem.get 原生支持 severities
        if severities:
            params["severities"] = severities
        # 主机筛选：先按主机名解析 hostid，再传入 hostids
        if host:
            host_rows = await self._call("host.get", {
                "output": ["hostid"],
                "search": {"host": host, "name": host},
                "searchByAny": True,
                "limit": 100,
            })
            host_ids = [h["hostid"] for h in (host_rows or [])]
            if not host_ids:
                return []
            params["hostids"] = host_ids
        rows = await self._call("problem.get", params)
        out: list[dict[str, Any]] = []
        trigger_ids: set[str] = set()
        for r in rows or []:
            obj_id = r.get("objectid")
            if obj_id:
                trigger_ids.add(str(obj_id))
            out.append({
                "event_id": r.get("eventid") or r.get("objectid"),
                "name": r.get("name"),
                "severity": r.get("severity"),
                "clock": int(r.get("clock", 0)),
                "acknowledged": str(r.get("acknowledged")) == "1",
                # 若 problem.get 已返回 hosts（部分版本支持 selectHosts）直接保留，
                # 否则通过下方 trigger.get 补全
                "hosts": r.get("hosts"),
                "_trigger_id": str(obj_id) if obj_id else None,
            })

        # problem.get 不支持 selectHosts 时，用 trigger.get 关联主机
        need_lookup = any(p["hosts"] is None for p in out)
        if need_lookup and trigger_ids:
            triggers = await self._call("trigger.get", {
                "triggerids": list(trigger_ids),
                "selectHosts": ["hostid", "host", "name"],
                "output": ["triggerid"],
            })
            host_map: dict[str, list[dict[str, Any]]] = {}
            for t in triggers or []:
                host_map[str(t.get("triggerid"))] = t.get("hosts") or []
            for p in out:
                if p["hosts"] is None and p["_trigger_id"]:
                    p["hosts"] = host_map.get(p["_trigger_id"], [])

        result = []
        for p in out:
            p.pop("_trigger_id", None)
            p["hosts"] = [
                {"host_id": h.get("hostid"), "host": h.get("host"),
                 "name": h.get("name")}
                for h in (p.get("hosts") or [])
            ]
            result.append(p)
        return result


async def zabbix_tester(conf: dict[str, Any]) -> tuple[bool, str]:
    return await ZabbixClient(conf).test_connection()
