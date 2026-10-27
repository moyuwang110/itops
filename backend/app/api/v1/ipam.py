"""IPAM 接口：网段、VLAN、IP 地址登记、扫描与变更记录。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.services import ipam_service

router = APIRouter(prefix="/ipam", tags=["ipam"])


# ---------- 入参模型 ----------


class VlanIn(BaseModel):
    vlan_id: int = Field(ge=1, le=4094)
    name: str = ""
    remark: str = ""


class VlanUpdateIn(BaseModel):
    vlan_id: int | None = Field(default=None, ge=1, le=4094)
    name: str | None = None
    remark: str | None = None


class SubnetIn(BaseModel):
    name: str = ""
    cidr: str
    gateway: str = ""
    purpose: str = ""
    vlan_ref: int | None = None
    remark: str = ""
    auto_scan: bool = True


class SubnetUpdateIn(BaseModel):
    name: str | None = None
    gateway: str | None = None
    purpose: str | None = None
    vlan_ref: int | None = None
    remark: str | None = None
    auto_scan: bool | None = None


class AssignIn(BaseModel):
    subnet_id: int
    ip: str
    assigned_to: str = ""
    purpose: str = ""
    remark: str = ""
    mac: str = ""
    hostname: str = ""


# ---------- VLAN ----------


@router.get("/vlans", summary="VLAN 列表")
async def vlans(db: AsyncSession = Depends(get_db),
                _user: str = Depends(get_current_user)) -> list[dict]:
    return await ipam_service.list_vlans(db)


@router.post("/vlans", summary="创建 VLAN")
async def create_vlan(payload: VlanIn, db: AsyncSession = Depends(get_db),
                      _user: str = Depends(get_current_user)) -> dict:
    return await ipam_service.create_vlan(db, payload.model_dump())


@router.put("/vlans/{vlan_pk}", summary="更新 VLAN")
async def update_vlan(vlan_pk: int, payload: VlanUpdateIn,
                      db: AsyncSession = Depends(get_db),
                      _user: str = Depends(get_current_user)) -> dict:
    return await ipam_service.update_vlan(db, vlan_pk, payload.model_dump(exclude_unset=True))


@router.delete("/vlans/{vlan_pk}", summary="删除 VLAN")
async def delete_vlan(vlan_pk: int, db: AsyncSession = Depends(get_db),
                      _user: str = Depends(get_current_user)) -> dict:
    await ipam_service.delete_vlan(db, vlan_pk)
    return {"ok": True}


# ---------- 网段 ----------


@router.get("/subnets", summary="网段列表")
async def subnets(db: AsyncSession = Depends(get_db),
                  _user: str = Depends(get_current_user)) -> list[dict]:
    return await ipam_service.list_subnets(db)


@router.post("/subnets", summary="创建网段")
async def create_subnet(payload: SubnetIn, db: AsyncSession = Depends(get_db),
                        _user: str = Depends(get_current_user)) -> dict:
    return await ipam_service.create_subnet(db, payload.model_dump())


@router.put("/subnets/{subnet_pk}", summary="更新网段")
async def update_subnet(subnet_pk: int, payload: SubnetUpdateIn,
                        db: AsyncSession = Depends(get_db),
                        _user: str = Depends(get_current_user)) -> dict:
    return await ipam_service.update_subnet(db, subnet_pk, payload.model_dump(exclude_unset=True))


@router.delete("/subnets/{subnet_pk}", summary="删除网段")
async def delete_subnet(subnet_pk: int, db: AsyncSession = Depends(get_db),
                        _user: str = Depends(get_current_user)) -> dict:
    await ipam_service.delete_subnet(db, subnet_pk)
    return {"ok": True}


@router.post("/subnets/{subnet_pk}/scan", summary="立即扫描网段")
async def scan_subnet(subnet_pk: int, db: AsyncSession = Depends(get_db),
                      _user: str = Depends(get_current_user)) -> dict:
    return await ipam_service.scan_subnet(db, subnet_pk)


# ---------- IP 地址 ----------


@router.get("/addresses", summary="网段内 IP 地址列表")
async def addresses(
    subnet_id: int,
    status: str = "",
    keyword: str = "",
    only_conflict: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> dict:
    return await ipam_service.list_addresses(
        db, subnet_id, status=status, keyword=keyword,
        only_conflict=only_conflict, page=page, page_size=page_size,
    )


@router.post("/addresses/assign", summary="手工登记 / 分配 IP")
async def assign_ip(payload: AssignIn, db: AsyncSession = Depends(get_db),
                    user: str = Depends(get_current_user)) -> dict:
    return await ipam_service.manual_assign(db, payload.model_dump(), operator=user)


@router.post("/addresses/{ip_pk}/release", summary="释放手工登记")
async def release_ip(ip_pk: int, db: AsyncSession = Depends(get_db),
                     user: str = Depends(get_current_user)) -> dict:
    return await ipam_service.release_ip(db, ip_pk, operator=user)


@router.get("/conflicts", summary="冲突地址列表")
async def conflicts(subnet_id: int | None = None,
                    db: AsyncSession = Depends(get_db),
                    _user: str = Depends(get_current_user)) -> list[dict]:
    return await ipam_service.list_conflicts(db, subnet_id)


@router.get("/changelogs", summary="IP 变更记录")
async def changelogs(
    subnet_id: int | None = None,
    ip: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> dict:
    return await ipam_service.list_changelogs(db, subnet_id, ip=ip, page=page, page_size=page_size)
