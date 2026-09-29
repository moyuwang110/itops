"""Agent CRUD：增删改查、按用户隔离、默认 Agent 切换。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent


async def list_agents(db: AsyncSession, user: str) -> list[Agent]:
    result = await db.execute(
        select(Agent).where(Agent.user == user).order_by(Agent.is_default.desc(), Agent.id.asc())
    )
    return list(result.scalars())


async def get_agent(db: AsyncSession, agent_id: int, user: str) -> Agent | None:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user == user)
    )
    return result.scalar_one_or_none()


async def get_default_agent(db: AsyncSession, user: str) -> Agent | None:
    result = await db.execute(
        select(Agent).where(Agent.user == user, Agent.is_default.is_(True))
    )
    return result.scalar_one_or_none()


async def create_agent(db: AsyncSession, user: str, payload: dict) -> Agent:
    if payload.get("is_default"):
        # 同用户旧默认降级
        await _clear_default(db, user)
    agent = Agent(user=user, **payload)
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def update_agent(db: AsyncSession, agent: Agent, payload: dict) -> Agent:
    if payload.get("is_default"):
        await _clear_default(db, agent.user, exclude_id=agent.id)
    for k, v in payload.items():
        setattr(agent, k, v)
    await db.commit()
    await db.refresh(agent)
    return agent


async def delete_agent(db: AsyncSession, agent: Agent) -> None:
    await db.delete(agent)
    await db.commit()


async def _clear_default(db: AsyncSession, user: str, exclude_id: int | None = None) -> None:
    stmt = select(Agent).where(Agent.user == user, Agent.is_default.is_(True))
    if exclude_id is not None:
        stmt = stmt.where(Agent.id != exclude_id)
    result = await db.execute(stmt)
    agents = list(result.scalars())
    for a in agents:
        a.is_default = False
    if agents:
        await db.commit()