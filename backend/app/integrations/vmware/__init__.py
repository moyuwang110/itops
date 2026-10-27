"""VMware vCenter Server 适配。"""
from app.integrations.vmware.client import VCenterClient
from app.integrations.vmware.errors import VCenterError


def build_vcenter_client(conf: dict) -> VCenterClient:
    return VCenterClient(conf)


async def vcenter_tester(conf: dict) -> tuple[bool, str]:
    """异步连通性测试：通过 asyncio.to_thread 把阻塞 pyvmomi 抛到线程池。"""
    client = VCenterClient(conf)
    try:
        info = await client.test()
        return True, f"连接成功：{info.get('full_name', 'vCenter')} v{info.get('version', '')}"
    except VCenterError as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001
        return False, f"vCenter 测试异常：{exc}"
    finally:
        await client.disconnect()


__all__ = ["VCenterClient", "VCenterError", "build_vcenter_client", "vcenter_tester"]