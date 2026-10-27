"""OneOps CMDB 相关接口（需登录）。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import BizError
from app.integrations import CLIENT_FACTORIES
from app.integrations.cmdb import CMDBClient
from app.integrations.cmdb.client import CMDBError
from app.services import config_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cmdb", tags=["cmdb"], dependencies=[Depends(get_current_user)])


async def _get_cmdb_client(db: AsyncSession) -> CMDBClient:
    rows = await config_service.list_configs(db, "cmdb")
    cfg = next((r for r in rows if r.provider == "oneops" and r.enabled), None)
    if cfg is None:
        raise BizError("未配置或未启用 CMDB，请先在集成配置中添加。", code="not_configured", http_status=400)
    factory = CLIENT_FACTORIES.get("oneops")
    if factory is None:
        raise BizError("CMDB 适配器未就绪", code="adapter_missing", http_status=500)
    plain = config_service.decrypt_settings(cfg)
    client = factory(plain)
    await client.connect()
    return client


def _translate_error(exc: CMDBError) -> BizError:
    return BizError(str(exc), code=exc.code, http_status=exc.http_status)


@router.get("/ci-types", summary="获取 CI 类型列表")
async def ci_types(db: AsyncSession = Depends(get_db)) -> dict:
    client = await _get_cmdb_client(db)
    try:
        rows = await client.list_ci_types()
    except CMDBError as exc:
        raise _translate_error(exc)
    finally:
        await client.disconnect()
    return {"items": rows}


@router.get("/relation-types", summary="获取关系类型列表")
async def relation_types(db: AsyncSession = Depends(get_db)) -> dict:
    client = await _get_cmdb_client(db)
    try:
        rows = await client.list_relation_types()
    except CMDBError as exc:
        raise _translate_error(exc)
    finally:
        await client.disconnect()
    return {"items": rows}


@router.get("/attributes", summary="获取 CI 类型属性列表（含中文别名）")
async def attributes(
    db: AsyncSession = Depends(get_db),
    ci_type: str | None = Query(None, description="CI 类型 id 或 name"),
) -> dict:
    client = await _get_cmdb_client(db)
    try:
        rows = await client.list_attributes(ci_type=ci_type)
    except CMDBError as exc:
        raise _translate_error(exc)
    finally:
        await client.disconnect()
    return {"items": rows}


@router.get("/statistics", summary="获取 CMDB 统计信息")
async def statistics(db: AsyncSession = Depends(get_db)) -> dict:
    client = await _get_cmdb_client(db)
    try:
        return await client.get_statistics()
    except CMDBError as exc:
        raise _translate_error(exc)
    finally:
        await client.disconnect()


@router.get("/cis", summary="获取 CI 实例列表")
async def cis(
    db: AsyncSession = Depends(get_db),
    ci_type: str | None = Query(None, description="CI 类型筛选（unique_key）"),
    keyword: str | None = Query(None, description="关键字搜索（字段化，不做全字段扫描）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    client = await _get_cmdb_client(db)
    try:
        result = await client.list_cis(
            ci_type=ci_type, keyword=keyword, page=page, page_size=page_size,
        )
    except CMDBError as exc:
        raise _translate_error(exc)
    finally:
        await client.disconnect()
    return result