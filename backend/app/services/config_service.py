"""集成配置服务：密钥加密落库、脱敏读取、连通性测试、系统设置。"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.core.exceptions import BizError
from app.core.security import MASK, SENSITIVE_KEYS, cipher, mask_settings
from app.core.timeutil import to_iso, utcnow
from app.integrations import CONNECTION_TESTERS
from app.models.config import IntegrationConfig, SystemSetting
from app.models.constants import CFG_LLM

logger = logging.getLogger(__name__)


# ---------- 配置增改查 ----------


async def list_configs(db: AsyncSession, config_type: str | None = None) -> list[IntegrationConfig]:
    stmt = select(IntegrationConfig).order_by(
        IntegrationConfig.type, IntegrationConfig.priority, IntegrationConfig.id
    )
    if config_type:
        stmt = stmt.where(IntegrationConfig.type == config_type)
    rows = list((await db.execute(stmt)).scalars().all())
    return rows


async def get_config(db: AsyncSession, config_id: int) -> IntegrationConfig:
    row = await db.get(IntegrationConfig, config_id)
    if row is None:
        raise BizError("配置不存在", code="not_found", http_status=404)
    return row


async def get_config_by_provider(db: AsyncSession, config_type: str,
                                 provider: str) -> IntegrationConfig | None:
    stmt = select(IntegrationConfig).where(
        IntegrationConfig.type == config_type,
        IntegrationConfig.provider == provider,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def decrypt_settings(row: IntegrationConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (row.settings or {}).items():
        if isinstance(v, str) and k.lower() in SENSITIVE_KEYS:
            try:
                out[k] = cipher.decrypt(v)
            except ValueError:
                out[k] = ""
        else:
            out[k] = v
    return out


def _merge_and_encrypt(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """合并配置：掩码值表示沿用旧值；敏感值加密。"""
    merged: dict[str, Any] = {}
    decrypted_old: dict[str, Any] = {}
    for k, v in (existing or {}).items():
        if isinstance(v, str) and k.lower() in SENSITIVE_KEYS:
            try:
                decrypted_old[k] = cipher.decrypt(v)
            except ValueError:
                decrypted_old[k] = ""
        else:
            decrypted_old[k] = v

    for k, v in incoming.items():
        lk = k.lower()
        if lk in SENSITIVE_KEYS:
            if v in (None, ""):
                # 空值：清空该敏感字段（不沿用旧值，也不在 merged 中保留）
                continue
            old_plain = decrypted_old.get(k, "")
            masked_old = mask_settings({k: old_plain}).get(k) if old_plain else None
            # 提交值等于后端输出的脱敏形态（****** 或 scheme://host/******）：
            # 视为"未修改"，沿用旧密文，避免把掩码串当新密钥加密入库
            if v == MASK or (masked_old is not None and v == masked_old):
                if old_plain:
                    merged[k] = cipher.encrypt(old_plain)
                # 旧值不存在则跳过
            else:
                merged[k] = cipher.encrypt(str(v))
        else:
            merged[k] = v
    # 保留传入未涉及的旧键
    for k, v in decrypted_old.items():
        if k not in merged and k not in incoming:
            if k.lower() in SENSITIVE_KEYS and v:
                merged[k] = cipher.encrypt(v)
            else:
                merged[k] = v
    return merged


async def upsert_config(db: AsyncSession, payload) -> IntegrationConfig:
    row = await get_config_by_provider(db, payload.type, payload.provider)
    if row is None:
        row = IntegrationConfig(
            type=payload.type,
            provider=payload.provider,
            name=payload.name or payload.provider,
            settings={},
        )
        db.add(row)

    row.name = payload.name or payload.provider
    row.enabled = payload.enabled
    row.priority = payload.priority
    row.settings = _merge_and_encrypt(row.settings or {}, payload.settings or {})

    if payload.is_default:
        row.is_default = True
        # 同类型仅一个默认（含尚未 flush 的新行：row.id 为 None 时条件 IS NOT NULL 命中全部旧记录）
        others = (await db.execute(
            select(IntegrationConfig).where(
                IntegrationConfig.type == payload.type,
                IntegrationConfig.id != row.id,
            )
        )).scalars().all()
        for other in others:
            other.is_default = False
    else:
        # 取消默认（含已有记录从 True 改 False 的情况）；允许该类型没有默认供应商
        row.is_default = False

    await db.commit()
    await db.refresh(row)
    return row


async def delete_config(db: AsyncSession, config_id: int) -> None:
    row = await get_config(db, config_id)
    await db.delete(row)
    await db.commit()


async def test_config(db: AsyncSession, config_id: int) -> tuple[bool, str]:
    row = await get_config(db, config_id)
    tester = CONNECTION_TESTERS.get(row.provider)
    if tester is None:
        raise BizError(f"{row.provider} 暂不支持连通性测试", http_status=400)
    plain = decrypt_settings(row)
    try:
        ok, message = await tester(plain)
    except Exception as exc:  # noqa: BLE001
        logger.exception("连通性测试异常 provider=%s", row.provider)
        ok, message = False, f"测试异常: {exc}"
    row.last_test_at = utcnow()
    row.last_test_ok = ok
    row.last_test_message = message[:500]
    await db.commit()
    return ok, message


def to_out_dict(row: IntegrationConfig) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "provider": row.provider,
        "name": row.name,
        "settings": mask_settings(decrypt_settings(row)),
        "enabled": row.enabled,
        "is_default": row.is_default,
        "priority": row.priority,
        "last_test_at": to_iso(row.last_test_at),
        "last_test_ok": row.last_test_ok,
        "last_test_message": row.last_test_message,
    }


# ---------- 系统设置 ----------


async def get_system_setting(db: AsyncSession) -> SystemSetting:
    row = await db.get(SystemSetting, 1)
    if row is None:
        row = SystemSetting(
            id=1,
            auto_analysis=app_settings.analysis_auto_enabled,
            before_minutes=app_settings.analysis_before_minutes,
            after_minutes=app_settings.analysis_after_minutes,
            auto_notify_channels=app_settings.auto_notify_channel_list,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def update_system_setting(db: AsyncSession, payload) -> SystemSetting:
    row = await get_system_setting(db)
    for field in ("auto_analysis", "before_minutes", "after_minutes",
                  "log_keywords", "auto_notify_channels"):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row
