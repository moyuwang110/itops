"""Task 1 冒烟测试：健康检查与安全工具。"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings, validate_secure_secrets
from app.core.security import (
    CredentialCipher,
    create_access_token,
    decode_access_token,
    mask_settings,
    verify_password,
    hash_password,
)


async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


async def test_ping_and_health(client):
    resp = await client.get("/api/v1/ping")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    health = await client.get("/api/v1/health")
    assert health.json()["database"] == "ok"


def test_password_hash():
    encoded = hash_password("s3cret!")
    assert encoded != "s3cret!"
    assert verify_password("s3cret!", encoded)
    assert not verify_password("wrong", encoded)


def test_jwt_roundtrip():
    token = create_access_token("admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "admin"


def test_credential_cipher():
    c = CredentialCipher()
    secret = "sk-1234567890"
    enc = c.encrypt(secret)
    assert enc.startswith("enc:v1:")
    assert secret not in enc
    assert c.decrypt(enc) == secret


def test_mask_settings():
    data = {
        "base_url": "https://api.deepseek.com",
        "api_key": "sk-secret",
        "nested": {"password": "p", "keep": 1},
        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/abcd",
    }
    masked = mask_settings(data)
    assert masked["api_key"] == "******"
    assert masked["nested"]["password"] == "******"
    assert masked["nested"]["keep"] == 1
    assert masked["webhook_url"].endswith("/******")
    assert "abcd" not in masked["webhook_url"]


def test_secure_secrets_validation_rejects_defaults():
    """M1：启用强校验时，内置默认口令/密钥必须触发拒绝启动错误。"""
    insecure = Settings(
        admin_password="ChangeMe_2026!",
        jwt_secret_key="dev-only-jwt-secret-please-change",
        fernet_key="pR5JQWEyc02scbP_TNs52W89eKVdY3KPUQOptDzwlnY=",
    )
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        validate_secure_secrets(insecure)

    secure = Settings(
        admin_password="Str0ng-Changed-Pwd!",
        jwt_secret_key="a" * 64,
        fernet_key=Fernet.generate_key().decode(),
    )
    validate_secure_secrets(secure)  # 不抛异常即通过
