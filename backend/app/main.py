"""ITOPS 后端入口。"""
from __future__ import annotations

import asyncio
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

# Zabbix 告警同步间隔（秒）
ALERT_SYNC_INTERVAL = 60


async def _alert_sync_loop() -> None:
    """后台循环：定时同步 Zabbix 当前未恢复问题到本地 alerts 表。"""
    from app.services.alert_sync_service import sync_zabbix_alerts

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await sync_zabbix_alerts(db)
        except Exception:  # noqa: BLE001
            logger.exception("定时同步 Zabbix 告警异常")
        await asyncio.sleep(ALERT_SYNC_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    configure_logging(settings.debug)
    # 生产强校验：默认密钥/口令未更换则拒绝启动
    if settings.require_secure_secrets:
        validate_secure_secrets(settings)
    await init_models()
    # 播种初始管理员（users 表为空时）
    try:
        from app.services import auth_service
        async with AsyncSessionLocal() as db:
            await auth_service.seed_admin_user(db)
    except Exception:  # noqa: BLE001
        logger.exception("播种初始管理员失败")
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
    # 启动后立即同步一次 Zabbix 告警，再进入定时循环
    sync_task = asyncio.create_task(_alert_sync_loop())
    logger.info("ITOPS 后端启动完成", extra={"db": settings.database_url.split(":", 1)[0]})
    yield
    # 关闭共享 httpx 客户端，释放连接资源
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    try:
        from app.integrations.llm.client import close_shared_clients as close_llm
        from app.integrations.zabbix.client import close_shared_clients as close_zabbix
        await close_llm()
        await close_zabbix()
    except Exception:  # noqa: BLE001
        logger.exception("关闭共享 httpx 客户端失败")


def create_app() -> FastAPI:
    configure_logging(settings.debug)
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
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
