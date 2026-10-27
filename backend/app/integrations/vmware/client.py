"""VMware vCenter Server 适配器：连接、连通测试、虚拟机清单拉取。

pyvmomi 是同步阻塞 IO，本适配器通过 `asyncio.to_thread` 把所有阻塞调用抛到
默认线程池中执行，从而不阻塞 FastAPI 事件循环。
"""
from __future__ import annotations

import asyncio
import atexit
import socket
import ssl
from typing import Any

from pyVmomi import vim
from pyVim.connect import Disconnect, SmartConnect

from app.integrations.vmware.errors import VCenterError


def _ssl_context(verify_ssl: bool) -> ssl.SSLContext | None:
    if verify_ssl:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class VCenterClient:
    """vCenter 客户端，封装同步 pyvmomi 调用，对外提供 async 接口。"""

    CONNECT_TIMEOUT = 10

    def __init__(self, conf: dict[str, Any]):
        self.conf = conf or {}
        self.host = (self.conf.get("host") or "").strip().replace("https://", "").replace("http://", "").rstrip("/")
        self.port = int(self.conf.get("port") or 443)
        self.username = self.conf.get("username") or ""
        self.password = self.conf.get("password") or ""
        self.verify_ssl = bool(self.conf.get("verify_ssl", False))
        self._si = None

    # ---- 生命周期 ----
    async def connect(self) -> vim.ServiceInstance:
        if self._si is not None:
            return self._si
        if not self.host:
            raise VCenterError("vCenter 地址不能为空", code="not_configured", http_status=400)
        if not self.username or not self.password:
            raise VCenterError("用户名和密码不能为空", code="not_configured", http_status=400)
        ctx = _ssl_context(self.verify_ssl)
        try:
            self._si = await asyncio.to_thread(self._sync_connect, ctx)
        except (socket.timeout, OSError) as exc:
            raise VCenterError(f"无法连接到 vCenter：{exc}", code="connection_failed", http_status=502) from exc
        except Exception as exc:  # noqa: BLE001
            raise VCenterError(f"vCenter 连接失败：{exc}", code="auth_failed", http_status=502) from exc
        if self._si is None:
            raise VCenterError("无法连接到 vCenter Server", code="connection_failed", http_status=502)
        atexit.register(Disconnect, self._si)
        return self._si

    def _sync_connect(self, ctx: ssl.SSLContext | None) -> vim.ServiceInstance:
        # 局部 socket 超时，避免污染全局默认
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.CONNECT_TIMEOUT)
        try:
            return SmartConnect(
                host=self.host,
                port=self.port,
                user=self.username,
                pwd=self.password,
                sslContext=ctx,
            )
        finally:
            socket.setdefaulttimeout(old_timeout)

    async def disconnect(self) -> None:
        if self._si is not None:
            try:
                await asyncio.to_thread(Disconnect, self._si)
            except Exception:  # noqa: BLE001
                pass
            self._si = None

    async def __aenter__(self) -> "VCenterClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.disconnect()

    # ---- 工具 ----
    @staticmethod
    def _get_obj(content, vimtype, name: str | None = None):
        container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
        try:
            objs = container.view
            if name:
                for obj in objs:
                    if obj.name == name:
                        return obj
                return None
            return list(objs)
        finally:
            container.Destroy()

    # ---- 业务 ----
    async def test(self) -> dict[str, Any]:
        """连通性测试：连接并返回 vCenter 版本信息。"""
        si = await self.connect()
        return await asyncio.to_thread(self._sync_test, si)

    @staticmethod
    def _sync_test(si) -> dict[str, Any]:
        about = si.content.about
        return {
            "name": about.name,
            "version": about.version,
            "build": about.build,
            "api_type": about.apiType,
            "api_version": about.apiVersion,
            "full_name": about.fullName,
        }

    async def list_vms(self) -> list[dict[str, Any]]:
        """拉取全部虚拟机清单。"""
        si = await self.connect()
        return await asyncio.to_thread(self._sync_list_vms, si)

    def _sync_list_vms(self, si) -> list[dict[str, Any]]:
        content = si.content
        vms = self._get_obj(content, [vim.VirtualMachine]) or []
        result: list[dict[str, Any]] = []
        for vm in vms:
            summary = vm.summary
            config = summary.config
            guest = summary.guest
            runtime = summary.runtime
            rp_name = ""
            if vm.resourcePool and vm.resourcePool.name:
                rp_name = vm.resourcePool.name
            result.append({
                "name": vm.name,
                "mor": str(vm._moId),
                "power_state": runtime.powerState if runtime else "unknown",
                "guest_os": config.guestFullName if config else "",
                "guest_hostname": guest.hostName if guest else "",
                "guest_ip": guest.ipAddress if guest else "",
                "num_cpu": config.numCpu if config else 0,
                "memory_mb": config.memorySizeMB if config else 0,
                "num_ethernet_cards": config.numEthernetCards if config else 0,
                "num_virtual_disks": config.numVirtualDisks if config else 0,
                "overall_status": summary.overallStatus,
                "resource_pool": rp_name,
                "guest_tools_status": guest.toolsRunningStatus if guest else "",
                "annotation": config.annotation if config else "",
            })
        return result


__all__ = ["VCenterClient"]