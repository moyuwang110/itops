"""集成配置与系统设置接口（均需登录）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.schemas.config import (
    ConfigUpsert,
    SystemSettingIn,
    TestResult,
)
from app.services import config_service

router = APIRouter(prefix="/configs", tags=["configs"], dependencies=[Depends(get_current_user)])


@router.get("", summary="集成配置列表")
async def list_configs(
    type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = await config_service.list_configs(db, type)
    return [config_service.to_out_dict(r) for r in rows]


@router.post("", summary="新增/更新集成配置（按 type+provider 幂等）")
async def upsert_config(
    payload: ConfigUpsert,
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await config_service.upsert_config(db, payload)
    return config_service.to_out_dict(row)


@router.delete("/{config_id}", summary="删除集成配置")
async def delete_config(config_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    await config_service.delete_config(db, config_id)
    return {"ok": True}


@router.post("/{config_id}/test", summary="连通性/测试发送", response_model=TestResult)
async def test_config(config_id: int, db: AsyncSession = Depends(get_db)) -> TestResult:
    ok, message = await config_service.test_config(db, config_id)
    return TestResult(ok=ok, message=message)


@router.get("/system", summary="获取系统分析设置")
async def get_system_setting(db: AsyncSession = Depends(get_db)) -> dict:
    row = await config_service.get_system_setting(db)
    return {
        "auto_analysis": row.auto_analysis,
        "before_minutes": row.before_minutes,
        "after_minutes": row.after_minutes,
        "log_keywords": row.log_keywords,
        "auto_notify_channels": row.auto_notify_channels or [],
    }


@router.put("/system", summary="更新系统分析设置")
async def update_system_setting(
    payload: SystemSettingIn, db: AsyncSession = Depends(get_db)
) -> dict:
    row = await config_service.update_system_setting(db, payload)
    return {
        "auto_analysis": row.auto_analysis,
        "before_minutes": row.before_minutes,
        "after_minutes": row.after_minutes,
        "log_keywords": row.log_keywords,
        "auto_notify_channels": row.auto_notify_channels or [],
    }
