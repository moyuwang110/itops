"""VMware vCenter 相关接口（需登录）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import BizError
from app.integrations import CLIENT_FACTORIES
from app.integrations.vmware import VCenterClient
from app.integrations.vmware.errors import VCenterError
from app.services import config_service

router = APIRouter(prefix="/vmware", tags=["vmware"], dependencies=[Depends(get_current_user)])


async def _get_vcenter_client(db: AsyncSession) -> VCenterClient:
    rows = await config_service.list_configs(db, "vmware")
    vcenter_cfg = next((r for r in rows if r.provider == "vcenter" and r.enabled), None)
    if vcenter_cfg is None:
        raise BizError("未配置或未启用 VMware vCenter Server，请先在集成配置中添加。", code="not_configured", http_status=400)
    factory = CLIENT_FACTORIES.get("vcenter")
    if factory is None:
        raise BizError("vCenter 适配器未就绪", code="adapter_missing", http_status=500)
    plain = config_service.decrypt_settings(vcenter_cfg)
    client = factory(plain)
    await client.connect()
    return client


@router.get("/vms", summary="获取 vCenter 虚拟机清单")
async def list_vms(db: AsyncSession = Depends(get_db)) -> dict:
    client = await _get_vcenter_client(db)
    try:
        try:
            vms = await client.list_vms()
        except VCenterError as exc:
            raise BizError(str(exc), code=exc.code, http_status=exc.http_status)
        except Exception as exc:  # noqa: BLE001
            raise BizError(f"获取虚拟机清单失败：{exc}", code="vmware_error", http_status=502)
    finally:
        await client.disconnect()
    powered_on = sum(1 for v in vms if v.get("power_state") == "poweredOn")
    powered_off = sum(1 for v in vms if v.get("power_state") == "poweredOff")
    suspended = sum(1 for v in vms if v.get("power_state") == "suspended")
    return {
        "total": len(vms),
        "powered_on": powered_on,
        "powered_off": powered_off,
        "suspended": suspended,
        "vms": vms,
    }