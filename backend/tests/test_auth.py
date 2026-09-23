"""AC-9：登录鉴权。"""
from __future__ import annotations

import os


async def _login(client, password=None):
    return await client.post(
        "/api/v1/auth/login",
        json={"username": os.environ["ADMIN_USERNAME"] if "ADMIN_USERNAME" in os.environ else "admin",
              "password": password or os.environ["ADMIN_PASSWORD"]},
    )


async def test_login_success_and_access(client):
    resp = await _login(client)
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


async def test_login_wrong_password(client):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "bad"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "login_failed"


async def test_protected_requires_token(client):
    resp = await client.get("/api/v1/configs")
    assert resp.status_code == 401


async def test_logout_revokes_token(client):
    token = (await _login(client)).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 200
    again = await client.get("/api/v1/auth/me", headers=headers)
    assert again.status_code == 401


async def test_revoked_token_persisted_in_db(client):
    """M2：登出黑名单必须落库（重启/多副本有效），而非仅进程内 set。"""
    from app.core.database import AsyncSessionLocal
    from app.models.auth import RevokedToken
    token = (await _login(client)).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/auth/logout", headers=headers)
    from app.core.security import decode_access_token
    jti = decode_access_token(token)["jti"]
    async with AsyncSessionLocal() as db:
        row = await db.get(RevokedToken, jti)
        assert row is not None and row.expires_at is not None
