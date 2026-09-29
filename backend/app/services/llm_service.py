"""大模型调用服务：默认供应商优先 + 备用降级链。"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConfigMissingError
from app.integrations.llm import LLMChain, build_chain
from app.models.constants import CFG_LLM
from app.services.config_service import decrypt_settings, list_configs


async def get_llm_chain(db: AsyncSession, providers: list[str] | None = None) -> LLMChain:
    rows = [r for r in await list_configs(db, CFG_LLM) if r.enabled]
    if providers:
        rows = [r for r in rows if r.provider in providers]
    if not rows:
        if providers:
            raise ConfigMissingError(f"指定的供应商未启用: {providers}")
        raise ConfigMissingError("大模型供应商")
    # 默认供应商排第一，其余按 priority
    rows.sort(key=lambda r: (not r.is_default, r.priority, r.id))
    items = [(r.provider, decrypt_settings(r)) for r in rows]
    return build_chain(items)
