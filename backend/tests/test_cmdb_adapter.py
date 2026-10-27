"""CMDB 适配器（OneOps）单元测试。

覆盖：
1. 登录成功 / 401 失败
2. token 自动重登（首次 401，第二次 200）
3. CI 类型列表解析（多种响应形态）
4. 关键字搜索字段化（_build_q 转义 Lucene 关键字）
5. 分页透传
6. 401 重试无回归
7. 注册到 CONNECTION_TESTERS / CLIENT_FACTORIES
8. tester 在 None 地址时返回 False
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations import CLIENT_FACTORIES, CONNECTION_TESTERS
from app.integrations.cmdb import cmdb_tester
from app.integrations.cmdb.client import CMDBClient, CMDBError


# ---------- 工具 ----------

def _make_response(status_code: int = 200, json_data: Any = None, text: str | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text or ""
    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)
    else:
        resp.json = MagicMock(side_effect=ValueError("no json"))
    return resp


def _make_client(settings: dict | None = None) -> CMDBClient:
    return CMDBClient(settings or {"base_url": "http://cmdb.test", "username": "u", "password": "p"})


# ---------- 登录 ----------

class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self) -> None:
        client = _make_client()
        async_client_mock = MagicMock()
        async_client_mock.post = AsyncMock(return_value=_make_response(200, {"token": "T-1"}))
        # 使用普通 dict 模拟 headers，避免 AsyncMock 拦截属性访问
        async_client_mock.headers = {}
        client._client = async_client_mock
        data = await client.login()
        assert client._token == "T-1"
        assert async_client_mock.headers["Access-Token"] == "T-1"
        assert data == {"token": "T-1"}

    @pytest.mark.asyncio
    async def test_login_401_raises_auth_failed(self) -> None:
        client = _make_client()
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=_make_response(401, {"msg": "no"}))
        with pytest.raises(CMDBError) as ei:
            await client.login()
        assert ei.value.code == "auth_failed"
        assert ei.value.http_status == 400

    @pytest.mark.asyncio
    async def test_login_connect_error_raises_connection_failed(self) -> None:
        client = _make_client()
        client._client = AsyncMock()
        client._client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(CMDBError) as ei:
            await client.login()
        assert ei.value.code == "connection_failed"

    def test_extract_token_top_level(self) -> None:
        assert CMDBClient._extract_token({"access_token": "T"}) == "T"
        assert CMDBClient._extract_token({"token": "T"}) == "T"
        assert CMDBClient._extract_token({"ticket": "T"}) == "T"

    def test_extract_token_nested(self) -> None:
        assert CMDBClient._extract_token({"data": {"token": "T"}}) == "T"
        assert CMDBClient._extract_token({"data": {"accessToken": "T"}}) == "T"

    def test_extract_token_invalid(self) -> None:
        assert CMDBClient._extract_token({}) is None
        assert CMDBClient._extract_token({"other": "x"}) is None
        assert CMDBClient._extract_token([]) is None


# ---------- 自动重登 ----------

class TestAutoRelogin:
    @pytest.mark.asyncio
    async def test_401_triggers_relogin_and_retry(self) -> None:
        client = _make_client()
        client._client = AsyncMock()
        # 第一次 401，第二次 200
        client._client.request = AsyncMock(side_effect=[
            _make_response(401, {}),
            _make_response(200, {"ci_types": []}),
        ])
        # 登录响应
        client._client.post = AsyncMock(return_value=_make_response(200, {"token": "T-2"}))
        data = await client._request_json("GET", "/api/v0.1/ci_types")
        assert data == {"ci_types": []}
        # 重登后 token 被刷新
        assert client._token == "T-2"
        # 调用顺序：先 login，再 request 401，再 request 200
        assert client._client.request.await_count == 2

    @pytest.mark.asyncio
    async def test_404_raises_not_found(self) -> None:
        client = _make_client()
        client._client = AsyncMock()
        client._client.request = AsyncMock(return_value=_make_response(404, {}))
        client._client.post = AsyncMock(return_value=_make_response(200, {"token": "T"}))
        with pytest.raises(CMDBError) as ei:
            await client._request_json("GET", "/api/v0.1/missing")
        assert ei.value.code == "not_found"


# ---------- 响应解析 ----------

class TestExtractList:
    def test_extract_from_top_level_list(self) -> None:
        items = CMDBClient._extract_list([{"a": 1}, {"a": 2}], ())
        assert items == [{"a": 1}, {"a": 2}]

    def test_extract_from_named_key(self) -> None:
        items = CMDBClient._extract_list({"ci_types": [{"k": "v"}]}, ("ci_types",))
        assert items == [{"k": "v"}]

    def test_extract_empty_when_no_key_matches(self) -> None:
        # 兜底改为返回空列表而非把整个 dict 当单元素
        items = CMDBClient._extract_list({"unexpected": "shape"}, ("ci_types", "items"))
        assert items == []

    def test_extract_skips_non_dict_items(self) -> None:
        items = CMDBClient._extract_list({"ci_types": [{"a": 1}, "string", None]}, ("ci_types",))
        assert items == [{"a": 1}]


# ---------- 关键字搜索 ----------

class TestBuildQ:
    def _client(self) -> CMDBClient:
        return _make_client()

    def test_empty_keyword_returns_all(self) -> None:
        assert self._client()._build_q("", None) == "*:*"

    def test_keyword_escapes_lucene_specials(self) -> None:
        q = self._client()._build_q("H3C+", None)
        # + 必须转义为 \+
        assert q == "*H3C\\+*"

    def test_keyword_with_ci_type_filter(self) -> None:
        q = self._client()._build_q("H3C", "server_name")
        # keyword 嵌入类型字段（OneOps 不支持 AND 组合）
        assert q == "server_name:*H3C*"

    def test_ci_type_only(self) -> None:
        q = self._client()._build_q("", "server_name")
        assert q == "server_name:*"

    def test_keyword_strips_whitespace(self) -> None:
        q = self._client()._build_q("  H3C  ", None)
        assert "  " not in q
        assert "H3C" in q


# ---------- 分页透传 ----------

class TestListCis:
    @pytest.mark.asyncio
    async def test_pagination_passed_to_remote(self) -> None:
        client = _make_client()
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=_make_response(200, {"token": "T"}))
        # 捕获 ci/search 请求体
        request_kwargs: dict[str, Any] = {}

        async def fake_request(method: str, url: str, **kwargs):
            request_kwargs.setdefault("calls", []).append((method, url, kwargs))
            return _make_response(200, {"numfound": 0, "result": [], "page": 2, "page_size": 25})

        client._client.request = AsyncMock(side_effect=fake_request)
        result = await client.list_cis(ci_type="server", keyword="H3C", page=2, page_size=25)
        assert result == {"total": 0, "page": 2, "page_size": 25, "items": []}
        # 确认透传
        post_kwargs = request_kwargs["calls"][0][2]
        assert post_kwargs["json"]["page"] == 2
        assert post_kwargs["json"]["page_size"] == 25
        assert post_kwargs["json"]["ci_type"] == "server"
        assert post_kwargs["json"]["q"] == "server:*H3C*"

    @pytest.mark.asyncio
    async def test_no_keyword_uses_all_query(self) -> None:
        client = _make_client()
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=_make_response(200, {"token": "T"}))
        captured: dict[str, Any] = {}

        async def fake_req(method: str, url: str, **kwargs):
            captured.update(kwargs)
            return _make_response(200, {"numfound": 1, "result": [{"a": 1}], "page": 1, "page_size": 50})

        client._client.request = AsyncMock(side_effect=fake_req)
        await client.list_cis()
        # 无筛选时必须传 q=*:*，否则 OneOps 返回空
        assert captured["json"]["q"] == "*:*"
        assert captured["json"]["page"] == 1
        assert captured["json"]["page_size"] == 50


# ---------- 属性端点 ----------

class TestListAttributes:
    @pytest.mark.asyncio
    async def test_returns_items_with_aliases(self) -> None:
        client = _make_client()
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=_make_response(200, {"token": "T"}))
        client._client.request = AsyncMock(return_value=_make_response(200, {
            "attributes": [
                {"name": "vserver_name", "alias": "虚拟机名"},
                {"name": "ip", "alias": "IP地址"},
            ]
        }))
        rows = await client.list_attributes(ci_type="yewu_vserver")
        assert len(rows) == 2
        assert rows[0]["alias"] == "虚拟机名"

    @pytest.mark.asyncio
    async def test_empty_when_no_ci_type(self) -> None:
        client = _make_client()
        rows = await client.list_attributes(ci_type=None)
        assert rows == []


# ---------- 注册 & tester ----------

class TestRegistration:
    def test_client_factory_registered(self) -> None:
        assert "oneops" in CLIENT_FACTORIES
        client = CLIENT_FACTORIES["oneops"]({"base_url": "http://x", "username": "u", "password": "p"})
        assert isinstance(client, CMDBClient)

    def test_tester_registered(self) -> None:
        assert "oneops" in CONNECTION_TESTERS
        assert CONNECTION_TESTERS["oneops"] is cmdb_tester


class TestTester:
    @pytest.mark.asyncio
    async def test_empty_url_returns_false(self) -> None:
        ok, msg = await cmdb_tester({"base_url": "", "username": "u", "password": "p"})
        assert ok is False
        assert "地址未配置" in msg

    @pytest.mark.asyncio
    async def test_connection_failure_returns_false(self) -> None:
        with patch("app.integrations.cmdb.client.httpx.AsyncClient") as MockClient:
            instance = MagicMock()
            instance.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            instance.aclose = AsyncMock()
            MockClient.return_value = instance
            ok, msg = await cmdb_tester({"base_url": "http://127.0.0.1:1", "username": "u", "password": "p"})
        assert ok is False
        assert "无法连接" in msg or "refused" in msg or "Connection" in msg or "测试异常" in msg


# ---------- 构造校验 ----------

class TestConstructor:
    def test_empty_base_url_raises(self) -> None:
        with pytest.raises(CMDBError) as ei:
            CMDBClient({})
        assert ei.value.code == "not_configured"

    def test_verify_ssl_truthy(self) -> None:
        c = CMDBClient({"base_url": "http://x", "verify_ssl": True})
        assert c._verify is True

    def test_verify_ssl_falsy(self) -> None:
        c = CMDBClient({"base_url": "http://x"})
        assert c._verify is False