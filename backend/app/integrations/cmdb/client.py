"""OneOps CMDB 异步客户端。

设计目标：
1. 全异步 httpx，避免阻塞 FastAPI 事件循环
2. 透传 OneOps 的 `page / page_size` 给原生搜索接口
3. 关键字搜索改为字段化匹配（unique_key 字段 + 业务常见 IP/名称字段），
   不再做 json.dumps 全字段字符串过滤，避免误匹配
4. token 缓存 + 401 重登，避免每次接口调用都重新登录
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Iterable

import httpx

logger = logging.getLogger(__name__)


class CMDBError(RuntimeError):
    """CMDB 业务错误基类，message 是直接展示给用户的友好文本。"""

    def __init__(self, message: str, *, code: str = "cmdb_error", http_status: int = 502):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class CMDBClient:
    """OneOps CMDB 异步客户端。

    接口命名遵循 OneOps 原生：/acl/login、/ci_types、/ci_types/{id}/attributes、
    /ci/search。调用方只需提供 base_url / username / password。
    """

    # 关键字搜索涉及的常见字段，按顺序尝试。
    # 仅包含 OneOps 实际存在的字段，避免 "Attribute xxx does not exist" 400 错误
    SEARCH_FIELDS: tuple[str, ...] = (
        "private_ip",
        "ilo_ip",
        "vserver_ip",
        "ip",
        "sn",
        "manufacturer",
        "vserver_name",
        "server_name",
        "bu",
        "department",
        "op_duty",
    )

    def __init__(
        self,
        settings: dict,
        *,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
    ) -> None:
        base_url = (settings.get("base_url") or "").rstrip("/")
        if not base_url:
            raise CMDBError("CMDB 地址未配置", code="not_configured", http_status=400)
        self._base_url = base_url
        self._username = settings.get("username") or ""
        self._password = settings.get("password") or ""
        verify = settings.get("verify_ssl", False)
        # False 时显式禁用校验，避免 httpx 默认对自签证书抛 SSL 错误
        self._verify = False if verify in (False, 0, "false", "False") else True
        self._timeouts = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=read_timeout, pool=connect_timeout)
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
        self._token_lock = asyncio.Lock()

    # ---- 生命周期 ----
    async def __aenter__(self) -> "CMDBClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeouts,
            verify=self._verify,
        )

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                logger.warning("CMDB 关闭连接失败", exc_info=True)
            self._client = None
            self._token = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise CMDBError("CMDB 客户端未初始化", code="not_initialized", http_status=500)
        return self._client

    # ---- 鉴权 ----
    async def login(self) -> dict:
        """登录并缓存 token，返回 token 解码 payload 或登录响应。"""
        async with self._token_lock:
            try:
                resp = await self.client.post(
                    "/api/v1/acl/login",
                    json={"username": self._username, "password": self._password},
                )
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError, OSError) as exc:
                raise CMDBError(f"无法连接到 CMDB：{exc}", code="connection_failed", http_status=502) from exc
            if resp.status_code == 401:
                raise CMDBError("CMDB 登录失败：用户名或密码错误", code="auth_failed", http_status=400)
            if resp.status_code >= 400:
                raise CMDBError(f"CMDB 登录失败：HTTP {resp.status_code}", code="cmdb_error", http_status=502)
            data = resp.json()
            token = self._extract_token(data)
            if not token:
                raise CMDBError("CMDB 登录成功但未返回 token", code="cmdb_error", http_status=502)
            self._token = token
            self.client.headers["Access-Token"] = token
            return data

    @staticmethod
    def _extract_token(data: dict | list | Any) -> str | None:
        """兼容多种登录响应形态。"""
        if isinstance(data, str):
            return data or None
        if not isinstance(data, dict):
            return None
        for key in ("access_token", "token", "accessToken", "Token", "ticket"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
        # 嵌套形态：data.token
        nested = data.get("data")
        if isinstance(nested, dict):
            return CMDBClient._extract_token(nested)
        return None

    async def _ensure_token(self) -> None:
        if self._token is None:
            await self.login()

    async def _request_json(self, method: str, url: str, **kwargs) -> dict | list:
        """带自动重登的请求。"""
        await self._ensure_token()
        try:
            resp = await self.client.request(method, url, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError, OSError) as exc:
            raise CMDBError(f"无法连接到 CMDB：{exc}", code="connection_failed", http_status=502) from exc
        if resp.status_code == 401:
            # token 失效：清空再登录后重试一次
            self._token = None
            try:
                del self.client.headers["Access-Token"]
            except KeyError:
                pass
            await self.login()
            try:
                resp = await self.client.request(method, url, **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError, OSError) as exc:
                raise CMDBError(f"无法连接到 CMDB：{exc}", code="connection_failed", http_status=502) from exc
        if resp.status_code == 404:
            raise CMDBError(f"CMDB 资源不存在：{url}", code="not_found", http_status=404)
        if resp.status_code >= 400:
            raise CMDBError(f"CMDB 请求失败：HTTP {resp.status_code} {resp.text[:200]}", code="cmdb_error", http_status=502)
        try:
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise CMDBError(f"CMDB 响应非 JSON：{exc}", code="cmdb_error", http_status=502) from exc

    # ---- 业务接口 ----
    async def test(self) -> dict:
        """连通性测试：登录 + 至少访问一次下游接口。"""
        data = await self.login()
        # 真实探活一次：CI 类型列表是最轻量的接口
        await self.list_ci_types(limit=1)
        user = ""
        if isinstance(data, dict):
            nested = data.get("data")
            if isinstance(nested, dict):
                user = str(nested.get("username") or nested.get("user") or nested.get("name") or "")
            else:
                user = str(data.get("username") or data.get("user") or data.get("name") or "")
        return {"user": user}

    async def list_ci_types(self, *, limit: int | None = None) -> list[dict]:
        """列出 CMDB 中所有 CI 类型。"""
        data = await self._request_json("GET", "/api/v0.1/ci_types")
        items = self._extract_list(data, ("ci_types", "items", "results", "data"))
        if limit is not None and limit > 0:
            items = items[:limit]
        return items

    async def list_relation_types(self) -> list[dict]:
        """列出所有关系类型。"""
        data = await self._request_json("GET", "/api/v0.1/relation_types")
        return self._extract_list(data, ("relation_types", "items", "results", "data"))

    async def get_statistics(self) -> dict:
        """CMDB 顶层统计信息。"""
        try:
            return await self._request_json("GET", "/api/v0.1/statistics")
        except CMDBError:
            # 统计接口在不同 OneOps 版本中可能不可用，降级返回，不阻断上层
            logger.warning("CMDB statistics 接口不可用，降级返回空统计", exc_info=True)
            return {}

    async def list_attributes(self, *, ci_type: str | None = None) -> list[dict]:
        """列出指定 CI 类型的属性定义（含中文 alias）。"""
        if not ci_type:
            return []
        # 列表端点：GET /api/v0.1/ci_types/{id}/attributes
        data = await self._request_json("GET", f"/api/v0.1/ci_types/{ci_type}/attributes")
        items = self._extract_list(data, ("attributes", "items", "results", "data"))
        return items

    async def list_cis(
        self,
        *,
        ci_type: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """拉取 CI 实例。

        透传 OneOps 原生分页；关键字搜索改为字段化匹配，避免 json.dumps 全字段匹配。
        CMDB 搜索接口为 POST /api/v0.1/ci/search，body 字段：page/page_size/q/ci_type
        """
        payload: dict[str, Any] = {"page": page, "page_size": page_size}
        # OneOps search 接口必须传 q，否则返回空；无筛选时用 *:*
        payload["q"] = self._build_q(keyword or "", ci_type)
        if ci_type:
            payload["ci_type"] = ci_type
        data = await self._request_json("POST", "/api/v0.1/ci/search", json=payload)
        total = data.get("numfound") or data.get("total") or 0
        items = data.get("result") or data.get("items") or data.get("data") or []
        return {
            "total": int(total) if isinstance(total, (int, float, str)) else 0,
            "page": page,
            "page_size": page_size,
            "items": items if isinstance(items, list) else [],
        }

    # ---- 工具 ----
    @staticmethod
    def _extract_list(data: Any, candidates: Iterable[str]) -> list[dict]:
        """从响应里按候选键抽取 list；都不匹配返回空列表而非把整个 dict 当单元素。"""
        if isinstance(data, list):
            return [it for it in data if isinstance(it, dict)]
        if not isinstance(data, dict):
            return []
        for key in candidates:
            val = data.get(key)
            if isinstance(val, list):
                return [it for it in val if isinstance(it, dict)]
        return []

    def _build_q(self, keyword: str, ci_type: str | None) -> str:
        """构造 Lucene 查询串（OneOps 验证过的有效语法）。

        - ci_type 实际是该类型的 unique_key 字段名（如 server_name），
          用 ``<unique_key>:*`` 过滤该类型的全部实例
        - 关键字用 ``*<keyword>*`` 全字段模糊匹配
        - 两者同时指定时，将 keyword 嵌入类型字段：``<unique_key>:*<keyword>*``
          （OneOps lucene 不支持 ``field:* AND *keyword*`` 组合）
        """
        kw = re.sub(r"[\s\u3000]+", " ", keyword or "").strip()
        safe = re.sub(r"([+\-!(){}\[\]^~\":/])", r"\\\1", kw)

        if ci_type and safe:
            return f"{ci_type}:*{safe}*"
        if ci_type:
            return f"{ci_type}:*"
        if safe:
            return f"*{safe}*"
        return "*:*"


# 兼容历史代码的 OneOpsClient 别名（保持向后兼容）
OneOpsClient = CMDBClient


__all__ = ["CMDBClient", "OneOpsClient", "CMDBError"]