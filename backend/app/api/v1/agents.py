"""Agent CRUD 接口（按当前用户隔离）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import BizError
from app.integrations.llm.client import PROVIDER_META
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    provider: str
    model: str = ""
    system_prompt: str = ""
    temperature: float = 0.2
    is_default: bool = False


class AgentOut(BaseModel):
    id: int
    name: str
    provider: str
    model: str
    system_prompt: str
    temperature: float
    is_default: bool


def _to_dict(a) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "provider": a.provider,
        "model": a.model,
        "system_prompt": a.system_prompt,
        "temperature": a.temperature,
        "is_default": a.is_default,
    }


@router.get("/providers", summary="可选的大模型供应商列表")
async def providers() -> list[dict]:
    return [
        {"provider": k, "label": v["label"], "default_model": v["default_model"]}
        for k, v in PROVIDER_META.items()
    ]


@router.get("", summary="我的 Agent 列表")
async def list_my_agents(
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
) -> list[dict]:
    rows = await agent_service.list_agents(db, user)
    return [_to_dict(r) for r in rows]


@router.post("", summary="新建 Agent")
async def create_agent(
    body: AgentIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    if body.provider not in PROVIDER_META:
        raise BizError(f"不支持的供应商: {body.provider}", code="invalid", http_status=400)
    payload = body.model_dump()
    row = await agent_service.create_agent(db, user, payload)
    return _to_dict(row)


@router.put("/{agent_id}", summary="修改 Agent")
async def update_agent(
    agent_id: int,
    body: AgentIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    if body.provider not in PROVIDER_META:
        raise BizError(f"不支持的供应商: {body.provider}", code="invalid", http_status=400)
    row = await agent_service.get_agent(db, agent_id, user)
    if row is None:
        raise BizError("Agent 不存在", code="not_found", http_status=404)
    row = await agent_service.update_agent(db, row, body.model_dump())
    return _to_dict(row)


@router.delete("/{agent_id}", summary="删除 Agent")
async def delete_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    row = await agent_service.get_agent(db, agent_id, user)
    if row is None:
        raise BizError("Agent 不存在", code="not_found", http_status=404)
    await agent_service.delete_agent(db, row)
    return {"ok": True}


@router.post("/{agent_id}/default", summary="设为默认 Agent")
async def set_default(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    row = await agent_service.get_agent(db, agent_id, user)
    if row is None:
        raise BizError("Agent 不存在", code="not_found", http_status=404)
    row = await agent_service.update_agent(db, row, {"is_default": True})
    return _to_dict(row)