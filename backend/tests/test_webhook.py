"""AC-1 / TR-7.1：Zabbix Webhook 接收、Token、去重、恢复。"""
from __future__ import annotations

import os

from app.core.database import AsyncSessionLocal
from app.models.alert import Alert
from sqlalchemy import func, select

TOKEN = os.environ["ZABBIX_WEBHOOK_TOKEN"]

PROBLEM = {
    "event_id": "EVT-1001",
    "host": "web01",
    "trigger": "CPU utilization > 90%",
    "severity": "4",
    "status": "PROBLEM",
    "datetime": "2026-09-22 10:00:00",
    "details": "CPU 使用率持续高于 90%",
}
RECOVERY = {**PROBLEM, "status": "OK", "datetime": "2026-09-22 10:30:00"}


async def _disable_auto(client, auth_headers):
    await client.put("/api/v1/configs/system",
                     json={"auto_analysis": False}, headers=auth_headers)


async def test_dedup_and_recovery(client, auth_headers):
    await _disable_auto(client, auth_headers)
    url = "/api/v1/webhooks/zabbix"
    h = {"X-Webhook-Token": TOKEN}

    r1 = await client.post(url, json=PROBLEM, headers=h)
    assert r1.status_code == 200 and r1.json()["dedup"] == "created"
    r2 = await client.post(url, json=PROBLEM, headers=h)
    assert r2.status_code == 200 and r2.json()["dedup"] == "updated"

    async with AsyncSessionLocal() as db:
        count = (await db.execute(
            select(func.count(Alert.id)).where(Alert.event_id == "EVT-1001")
        )).scalar_one()
        assert count == 1

    r3 = await client.post(url, json=RECOVERY, headers=h)
    assert r3.status_code == 200
    async with AsyncSessionLocal() as db:
        alert = (await db.execute(
            select(Alert).where(Alert.event_id == "EVT-1001")
        )).scalar_one()
        assert alert.status == "resolved"
        assert alert.recovered_at is not None
        assert alert.raw_payload["event_id"] == "EVT-1001"
        assert alert.severity == "严重"  # 数字级别映射


async def test_token_required(client, auth_headers):
    await _disable_auto(client, auth_headers)
    # 无 token
    r = await client.post("/api/v1/webhooks/zabbix", json=PROBLEM)
    assert r.status_code == 403
    # query token
    r2 = await client.post(f"/api/v1/webhooks/zabbix?token={TOKEN}", json=PROBLEM)
    assert r2.status_code == 200
    # 错误 token
    r3 = await client.post("/api/v1/webhooks/zabbix", json=PROBLEM,
                           headers={"X-Webhook-Token": "wrong"})
    assert r3.status_code == 403


async def test_malformed_payload(client, auth_headers):
    await _disable_auto(client, auth_headers)
    h = {"X-Webhook-Token": TOKEN}
    r = await client.post("/api/v1/webhooks/zabbix", json={"foo": "bar"}, headers=h)
    assert r.status_code == 400
    r2 = await client.post("/api/v1/webhooks/zabbix", json=["not", "object"],
                           headers=h)
    assert r2.status_code == 400
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count(Alert.id)))).scalar_one() == 0


async def test_response_fast(client, auth_headers):
    import time
    await _disable_auto(client, auth_headers)
    start = time.perf_counter()
    r = await client.post("/api/v1/webhooks/zabbix", json=PROBLEM,
                          headers={"X-Webhook-Token": TOKEN})
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    assert elapsed < 0.5
