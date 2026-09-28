"""pytest 公共夹具：内存数据库 + ASGI 测试客户端。"""
from __future__ import annotations

import os
import tempfile

# 使用文件型 SQLite 而非 :memory:+StaticPool，避免后台任务与请求共享单连接导致的
# 事务可见性竞态（StaticPool 下所有 session 复用同一 DBAPI 连接）。
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
# 测试环境强制覆盖（不依赖外部 .env / shell 环境变量）
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-admin-pass"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret"
os.environ["FERNET_KEY"] = "pR5JQWEyc02scbP_TNs52W89eKVdY3KPUQOptDzwlnY="
os.environ["ZABBIX_WEBHOOK_TOKEN"] = "test-webhook-token"
os.environ["REQUIRE_SECURE_SECRETS"] = "false"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    # 每个用例重置登录限流器，避免跨用例触发 429
    from app.core.rate_limit import login_limiter
    login_limiter.reset()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 每个用例重建表，保证库隔离
        from app.core.database import Base, engine, init_models
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await init_models()
        # 播种测试管理员（保证登录可用）
        from app.services import auth_service
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await auth_service.seed_admin_user(db)
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": os.environ["ADMIN_PASSWORD"]},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
