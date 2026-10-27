"""VMware vCenter 适配器单元测试。

覆盖：
1. 构造校验（host/user/pass 缺失）
3. asyncio.to_thread 包装验证（不会阻塞事件循环）
4. test/list_vms 字段映射
6. VCenterError 类型转换
7. 注册到 CONNECTION_TESTERS / CLIENT_FACTORIES
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations import CLIENT_FACTORIES, CONNECTION_TESTERS
from app.integrations.vmware import vcenter_tester
from app.integrations.vmware.client import VCenterClient
from app.integrations.vmware.errors import VCenterError


# ---------- 工具 ----------

def _make_si(about: dict | None = None, vms: list | None = None) -> MagicMock:
    si = MagicMock()
    si.content.about.name = (about or {}).get("name", "VMware vCenter")
    si.content.about.version = (about or {}).get("version", "7.0")
    si.content.about.build = (about or {}).get("build", "")
    si.content.about.apiType = (about or {}).get("api_type", "VirtualCenter")
    si.content.about.apiVersion = (about or {}).get("api_version", "7.0")
    si.content.about.fullName = (about or {}).get("full_name", "VMware vCenter 7.0")
    # viewManager 用于 list_vms
    vm_list = vms or []

    class FakeVM:
        def __init__(self, name: str):
            self.name = name
            self._moId = f"vm-{name}"

        @property
        def summary(self):
            m = MagicMock()
            m.config.guestFullName = "CentOS 7"
            m.config.numCpu = 2
            m.config.memorySizeMB = 4096
            m.config.numEthernetCards = 1
            m.config.numVirtualDisks = 1
            m.config.annotation = ""
            m.guest.hostName = self.name
            m.guest.ipAddress = "10.0.0.1"
            m.guest.toolsRunningStatus = "guestToolsRunning"
            m.runtime.powerState = "poweredOn"
            m.overallStatus = "green"
            return m

        @property
        def resourcePool(self):
            m = MagicMock()
            m.name = "Resources"
            return m

    container = MagicMock()
    container.view = [FakeVM(v["name"]) for v in vm_list] if vm_list else []
    si.content.viewManager.CreateContainerView = MagicMock(return_value=container)
    return si


# ---------- 构造校验 ----------

class TestConstructor:
    def test_missing_host_raises(self) -> None:
        client = VCenterClient({})
        with pytest.raises(VCenterError) as ei:
            asyncio.run(client.connect())
        assert ei.value.code == "not_configured"

    def test_missing_credentials_raises(self) -> None:
        client = VCenterClient({"host": "vcenter.test"})
        with pytest.raises(VCenterError) as ei:
            asyncio.run(client.connect())
        assert ei.value.code == "not_configured"

    def test_host_stripped(self) -> None:
        c = VCenterClient({"host": "https://vcenter.test/", "username": "u", "password": "p"})
        assert c.host == "vcenter.test"


# ---------- 测试接口 ----------

class TestAsyncInterface:
    @pytest.mark.asyncio
    async def test_returns_about_info(self) -> None:
        client = VCenterClient({"host": "vcenter.test", "username": "u", "password": "p"})
        client._si = _make_si()
        info = await client.test()
        assert info["name"] == "VMware vCenter"
        assert info["version"] == "7.0"
        assert info["full_name"] == "VMware vCenter 7.0"

    @pytest.mark.asyncio
    async def test_list_vms_maps_fields(self) -> None:
        client = VCenterClient({"host": "vcenter.test", "username": "u", "password": "p"})
        client._si = _make_si(vms=[{"name": "vm-1"}, {"name": "vm-2"}])
        vms = await client.list_vms()
        assert len(vms) == 2
        assert vms[0]["name"] == "vm-1"
        assert vms[0]["power_state"] == "poweredOn"
        assert vms[0]["guest_os"] == "CentOS 7"
        assert vms[0]["resource_pool"] == "Resources"
        assert vms[0]["num_cpu"] == 2
        assert vms[0]["memory_mb"] == 4096

    @pytest.mark.asyncio
    async def test_does_not_block_event_loop(self) -> None:
        """通过 to_thread 在线程池中执行同步 pyvmomi 调用，主协程不被阻塞。"""
        client = VCenterClient({"host": "vcenter.test", "username": "u", "password": "p"})

        # 把 to_thread 的 target 替换为慢操作
        original_to_thread = asyncio.to_thread

        async def slow_to_thread(func, *args, **kwargs):
            await asyncio.sleep(0.05)  # 模拟 pyvmomi 阻塞
            return await original_to_thread(func, *args, **kwargs)

        with patch("app.integrations.vmware.client.asyncio.to_thread", side_effect=slow_to_thread):
            si = _make_si()
            client._si = si
            # 同时让另一个协程跑，证明事件循环未被阻塞
            start = asyncio.get_event_loop().time()
            await asyncio.gather(
                client.test(),
                asyncio.sleep(0.01),
            )
            elapsed = asyncio.get_event_loop().time() - start
            # 如果阻塞事件循环，第二个 sleep 会等待 50ms+
            assert elapsed < 0.1, f"疑似阻塞事件循环：elapsed={elapsed}"


# ---------- 测试器 ----------

class TestTester:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        client_mock = AsyncMock()
        client_mock.test = AsyncMock(return_value={"full_name": "VMware vCenter 8.0", "version": "8.0"})
        client_mock.disconnect = AsyncMock()
        with patch("app.integrations.vmware.VCenterClient", return_value=client_mock):
            ok, msg = await vcenter_tester({"host": "vcenter.test", "username": "u", "password": "p"})
        assert ok is True
        assert "连接成功" in msg
        assert "8.0" in msg
        client_mock.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failure(self) -> None:
        client_mock = AsyncMock()
        client_mock.test = AsyncMock(side_effect=VCenterError("vCenter 不可达", code="connection_failed"))
        client_mock.disconnect = AsyncMock()
        with patch("app.integrations.vmware.VCenterClient", return_value=client_mock):
            ok, msg = await vcenter_tester({"host": "vcenter.test", "username": "u", "password": "p"})
        assert ok is False
        assert "vCenter 不可达" in msg
        client_mock.disconnect.assert_awaited_once()


# ---------- 注册 ----------

class TestRegistration:
    def test_factory_registered(self) -> None:
        assert "vcenter" in CLIENT_FACTORIES
        client = CLIENT_FACTORIES["vcenter"]({"host": "vcenter.test", "username": "u", "password": "p"})
        assert isinstance(client, VCenterClient)

    def test_tester_registered(self) -> None:
        assert "vcenter" in CONNECTION_TESTERS
        assert CONNECTION_TESTERS["vcenter"] is vcenter_tester


# ---------- 错误类型 ----------

class TestErrorType:
    def test_vcenter_error_has_code(self) -> None:
        e = VCenterError("x", code="auth_failed", http_status=502)
        assert str(e) == "x"
        assert e.code == "auth_failed"
        assert e.http_status == 502