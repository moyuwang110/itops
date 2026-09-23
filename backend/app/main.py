"""ITOPS 后端入口。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete

from app.api.v1 import api_router
from app.core.config import settings, validate_secure_secrets
from app.core.database import AsyncSessionLocal, init_models
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestIDMiddleware, configure_logging
from app.models.auth import RevokedToken
import app.integrations.loader  # noqa: F401  注册外部平台适配器

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    configure_logging(settings.debug)
    # 生产强校验：默认密钥/口令未更换则拒绝启动
    if settings.require_secure_secrets:
        validate_secure_secrets(settings)
    await init_models()
    # 清理已过期的登出令牌黑名单
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RevokedToken).where(
            RevokedToken.expires_at < datetime.utcnow()))
        await db.commit()
    # 回收崩溃前停留在 processing 的分析任务
    try:
        from app.services.analysis_service import recover_stale
        reset = await recover_stale()
        if reset:
            logger.warning("启动回收：%s 个中断的分析任务已重置为 pending", reset)
    except Exception:  # noqa: BLE001
        logger.exception("启动回收 processing 告警失败")
    logger.info("ITOPS 后端启动完成", extra={"db": settings.database_url.split(":", 1)[0]})
    yield


def create_app() -> FastAPI:
    configure_logging(settings.debug)
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestIDMiddleware)
    origins = settings.cors_origin_list
    # credentials 与通配源 * 不能同时使用（浏览器会拒绝）：显式来源才放行凭证
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()
