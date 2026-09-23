"""Zabbix 监控数据查询接口（需登录）。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import BizError
from app.services import zabbix_service

router = APIRouter(prefix="/zabbix", tags=["zabbix"],
                   dependencies=[Depends(get_current_user)])


@router.get("/hosts", summary="搜索/列出 Zabbix 主机")
async def hosts(
    keyword: str = "",
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await zabbix_service.query_hosts(db, keyword, limit)


@router.get("/items", summary="查询主机监控项")
async def items(
    host_id: str = Query(..., min_length=1),
    keyword: str = "",
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await zabbix_service.query_items(db, host_id, keyword, limit)


@router.get("/history", summary="查询监控项历史时间序列")
async def history(
    item_id: str = Query(...),
    value_type: int = Query(default=0, ge=0, le=4),
    start: str | None = Query(default=None, description="秒级时间戳或 ISO8601"),
    end: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = int(time.time())
    try:
        start_ts = zabbix_service.parse_time(start) or now - 3600
        end_ts = zabbix_service.parse_time(end) or now
    except ValueError as exc:
        raise BizError(str(exc), code="bad_time")
    points = await zabbix_service.query_history(
        db, item_id, value_type, start_ts, end_ts, limit
    )
    return {"item_id": item_id, "start": start_ts, "end": end_ts, "points": points}


@router.get("/trend", summary="查询监控项趋势聚合（小时级 min/avg/max）")
async def trend(
    item_id: str = Query(...),
    value_type: int = Query(default=0, ge=0, le=4),
    start: str | None = Query(default=None, description="秒级时间戳或 ISO8601"),
    end: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = int(time.time())
    try:
        start_ts = zabbix_service.parse_time(start) or now - 7 * 86400
        end_ts = zabbix_service.parse_time(end) or now
    except ValueError as exc:
        raise BizError(str(exc), code="bad_time")
    points = await zabbix_service.query_trend(
        db, item_id, value_type, start_ts, end_ts, limit
    )
    return {"item_id": item_id, "start": start_ts, "end": end_ts, "points": points}


@router.get("/problems", summary="Zabbix 当前未恢复问题")
async def problems(
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await zabbix_service.query_problems(db, limit)
