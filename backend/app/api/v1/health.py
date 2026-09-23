"""系统健康检查。"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

router = APIRouter()


@router.get("/ping")
async def ping() -> dict[str, object]:
    return {"ok": True, "app": settings.app_name}


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "ok": db_ok,
        "app": settings.app_name,
        "database": "ok" if db_ok else "error",
        "db_type": settings.database_url.split(":", 1)[0],
    }
