"""AC-3(脱敏)/Task5：集成配置加密存储与系统设置。"""
from __future__ import annotations

from app.core.database import AsyncSessionLocal
from app.models.config import IntegrationConfig


async def test_secret_encrypted_and_masked(client, auth_headers):
    payload = {
        "type": "llm",
        "provider": "deepseek",
        "name": "DeepSeek 测试",
        "enabled": True,
        "is_default": True,
        "settings": {
            "base_url": "https://api.deepseek.com",
            "api_key": "sk-plain-secret-123",
            "model": "deepseek-chat",
            "temperature": 0.2,
        },
    }
    resp = await client.post("/api/v1/configs", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["settings"]["api_key"] == "******"
    assert data["settings"]["base_url"] == "https://api.deepseek.com"

    # 数据库中必须是密文
    async with AsyncSessionLocal() as db:
        row = await db.get(IntegrationConfig, data["id"])
        stored_key = row.settings["api_key"]
        assert stored_key.startswith("enc:v1:")
        assert "sk-plain-secret-123" not in stored_key

    # 列表接口同样脱敏
    listed = await client.get("/api/v1/configs?type=llm", headers=auth_headers)
    assert listed.json()[0]["settings"]["api_key"] == "******"


async def test_mask_keeps_old_secret(client, auth_headers):
    body = {
        "type": "llm",
        "provider": "doubao",
        "settings": {"api_key": "sk-first", "model": "doubao-pro"},
    }
    created = (await client.post("/api/v1/configs", json=body, headers=auth_headers)).json()

    # 再次提交时密钥传掩码（表示不修改），仅改 model
    body2 = {
        "type": "llm",
        "provider": "doubao",
        "settings": {"api_key": "******", "model": "doubao-lite"},
    }
    await client.post("/api/v1/configs", json=body2, headers=auth_headers)

    async with AsyncSessionLocal() as db:
        row = await db.get(IntegrationConfig, created["id"])
        from app.core.security import cipher
        assert cipher.decrypt(row.settings["api_key"]) == "sk-first"
        assert row.settings["model"] == "doubao-lite"


async def test_system_setting_defaults_and_update(client, auth_headers):
    resp = await client.get("/api/v1/configs/system", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["before_minutes"] == 30

    upd = await client.put(
        "/api/v1/configs/system",
        json={"before_minutes": 45, "auto_notify_channels": ["feishu"]},
        headers=auth_headers,
    )
    assert upd.json()["before_minutes"] == 45
    assert upd.json()["auto_notify_channels"] == ["feishu"]


async def test_empty_secret_clears_value(client, auth_headers):
    """M3：敏感字段提交空串必须真正清空，而不是静默保留旧值。"""
    body = {
        "type": "llm", "provider": "minimax",
        "settings": {"api_key": "sk-to-be-cleared", "model": "abab"},
    }
    created = (await client.post("/api/v1/configs", json=body,
                                 headers=auth_headers)).json()
    body2 = {
        "type": "llm", "provider": "minimax",
        "settings": {"api_key": "", "model": "abab2"},
    }
    await client.post("/api/v1/configs", json=body2, headers=auth_headers)
    async with AsyncSessionLocal() as db:
        row = await db.get(IntegrationConfig, created["id"])
        assert "api_key" not in row.settings
        assert row.settings["model"] == "abab2"


async def test_webhook_masked_shape_keeps_old_secret(client, auth_headers):
    """M3：直接把脱敏形态 scheme://host/****** 回传，不得当作新值加密入库。"""
    url = "https://open.feishu.cn/open-apis/bot/v2/hook/abcd1234"
    body = {
        "type": "notify_channel", "provider": "feishu",
        "settings": {"webhook_url": url, "sign_secret": "sec-x"},
    }
    created = (await client.post("/api/v1/configs", json=body,
                                 headers=auth_headers)).json()
    masked_url = created["settings"]["webhook_url"]
    assert masked_url == "https://open.feishu.cn/******"

    body2 = {
        "type": "notify_channel", "provider": "feishu",
        "settings": {"webhook_url": masked_url, "sign_secret": "******"},
    }
    await client.post("/api/v1/configs", json=body2, headers=auth_headers)
    async with AsyncSessionLocal() as db:
        row = await db.get(IntegrationConfig, created["id"])
        from app.core.security import cipher
        assert cipher.decrypt(row.settings["webhook_url"]) == url
        assert cipher.decrypt(row.settings["sign_secret"]) == "sec-x"


async def test_cancel_default_clears_only_row(client, auth_headers):
    """M4：取消某供应商默认后，不应残留两个默认；允许该类型没有默认。"""
    for i, provider in enumerate(("deepseek", "minimax"), start=1):
        body = {
            "type": "llm", "provider": provider, "is_default": True,
            "settings": {"api_key": f"sk-{provider}", "model": provider},
        }
        await client.post("/api/v1/configs", json=body, headers=auth_headers)

    rows = (await client.get("/api/v1/configs?type=llm",
                             headers=auth_headers)).json()
    defaults = {r["provider"]: r["is_default"] for r in rows}
    # 后设的 minimax 为默认，deepseek 已被清掉
    assert defaults == {"deepseek": False, "minimax": True}

    # 再把 minimax 默认取消
    await client.post("/api/v1/configs", json={
        "type": "llm", "provider": "minimax", "is_default": False,
        "settings": {"api_key": "******", "model": "minimax"},
    }, headers=auth_headers)
    rows = (await client.get("/api/v1/configs?type=llm",
                             headers=auth_headers)).json()
    assert all(r["is_default"] is False for r in rows)
