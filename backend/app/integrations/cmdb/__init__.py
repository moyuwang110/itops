"""OneOps CMDB 适配。"""
from app.integrations.cmdb.client import CMDBClient, OneOpsClient


def build_cmdb_client(conf: dict) -> CMDBClient:
    return CMDBClient(conf)


async def cmdb_tester(conf: dict) -> tuple[bool, str]:
    """连通性测试：通过 async 客户端登录并访问一次下游接口。"""
    client: CMDBClient | None = None
    try:
        client = CMDBClient(conf)
        await client.connect()
        info = await client.test()
        user = info.get("user", "")
        return True, f"连接成功：用户 {user}" if user else "连接成功"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    finally:
        if client is not None:
            await client.disconnect()


__all__ = ["OneOpsClient", "CMDBClient", "build_cmdb_client", "cmdb_tester"]