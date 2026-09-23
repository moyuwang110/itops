"""统一日志查询接口。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import BizError
from app.integrations.logs.log_helpers import split_keywords
from app.services import log_service, zabbix_service

router = APIRouter(prefix="/logs", tags=["logs"],
                   dependencies=[Depends(get_current_user)])


@router.get("/platforms", summary="已启用日志平台列表")
async def platforms(db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await log_service.enabled_platforms(db)


@router.get("/query", summary="统一日志查询")
async def query(
    platform: str = Query(..., description="graylog/loki/elasticsearch"),
    start: str | None = None,
    end: str | None = None,
    keyword: str = "",
    host: str = "",
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = int(time.time())
    try:
        start_ts = zabbix_service.parse_time(start) or now - 1800
        end_ts = zabbix_service.parse_time(end) or now
    except ValueError as exc:
        raise BizError(str(exc), code="bad_time")
    # 关键词按逗号/空白切分，多词 OR；原始串同时透传给平台原生查询
    keywords = split_keywords(keyword)
    return await log_service.query_logs(
        db, platform=platform, start_ts=start_ts, end_ts=end_ts,
        keyword=keyword, host=host, limit=limit, keywords=keywords or None,
    )
