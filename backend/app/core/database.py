"""异步 SQLAlchemy 引擎、会话与建表（方言中立，支持 SQLite / PostgreSQL）。"""
from __future__ import annotations

import os
from urllib.parse import urlparse

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _sqlite_db_path(url: str) -> str | None:
    """从 sqlite+aiosqlite:/// URI 提取数据库文件路径。

    支持三种形式：
    - sqlite+aiosqlite:///./data/itops.db  → ./data/itops.db
    - sqlite+aiosqlite:////app/data/itops.db → /app/data/itops.db
    - sqlite+aiosqlite:///:memory:        → None（内存库）
    """
    if not url.startswith("sqlite"):
        return None
    parsed = urlparse(url)
    path = parsed.path
    # sqlite+aiosqlite:////app/x.db → netloc='' path='//app/x.db'，需去掉前导斜杠
    # sqlite+aiosqlite:///./data/x.db  → netloc='' path='./data/x.db'
    if path.startswith("//"):
        path = path[1:]
    if not path or path == ":memory:":
        return None
    return path


def _ensure_sqlite_dir(url: str) -> None:
    db_path = _sqlite_db_path(url)
    if db_path and ":memory:" not in db_path:
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)


_ensure_sqlite_dir(settings.database_url)

_is_memory = ":memory:" in settings.database_url
_is_sqlite = settings.database_url.startswith("sqlite")
# 内存库必须用 StaticPool（共享同一连接才能共享数据库）；
# 文件型 SQLite 用 NullPool，避免 QueuePool 复用连接时的事务可见性问题
# （后台任务与 HTTP 请求各自持有独立连接，SQLite 文件锁处理并发）。
_poolclass = StaticPool if _is_memory else (NullPool if _is_sqlite else None)
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=not _is_sqlite,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    poolclass=_poolclass,
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragma(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_models() -> None:
    # 导入以注册所有模型
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 兼容存量库：Base.metadata.create_all 不会给已有表加新字段
    # 仅 PostgreSQL 走 schema diff（SQLite 不支持 IF NOT EXISTS 子句需单独处理）。
    if settings.database_url.startswith("postgresql"):
        await _apply_pg_schema_diffs()


# 字段补齐清单：键为"表.列"，值为目标列类型（与模型定义保持同步）。
# 仅覆盖"新增字段"场景（additive migration），不做 drop/rename。
_PG_COLUMN_DDL = {
    "reports.agent_id": "INTEGER",
    "reports.agent_name": "VARCHAR(64)",
    "alerts.acknowledged": "BOOLEAN DEFAULT FALSE",
}


async def _apply_pg_schema_diffs() -> None:
    """给已存在的 PostgreSQL 表加上模型里新增的列，避免运行时 UndefinedColumnError。"""
    from sqlalchemy import text
    async with engine.begin() as conn:
        for qualified, col_type in _PG_COLUMN_DDL.items():
            table, col = qualified.split(".", 1)
            await conn.execute(text(
                f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}'
            ))
