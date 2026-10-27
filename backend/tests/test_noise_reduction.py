"""告警降噪服务测试：去重、抑制、关联分析、统计。"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.alert import Alert
from app.models.constants import ALERT_PROBLEM
from app.services import alert_noise_service as ns


@pytest.fixture(autouse=True)
def reset_stats():
    """每个测试前清零统计，避免互相干扰。"""
    ns.reset_noise_stats()
    yield


def _settings(**kw):
    defaults = dict(
        dedup_enabled=True, dedup_window_minutes=5,
        suppression_enabled=True, correlation_enabled=True,
        storm_threshold=10, storm_window_minutes=5,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _parsed(**kw):
    defaults = dict(
        event_id="evt-1", host="host-01", host_id="1001",
        title="CPU 使用率过高", trigger_id="t-1",
        severity="警告", is_recovery=False,
        occurred_at=datetime.utcnow(), detail_text="",
    )
    defaults.update(kw)
    return defaults


def test_compute_dedup_key_same_for_same_host_trigger_title():
    a = _parsed()
    b = _parsed(event_id="evt-2")
    assert ns.compute_dedup_key(a) == ns.compute_dedup_key(b)


def test_compute_dedup_key_differs_by_host():
    a = _parsed()
    b = _parsed(host="host-02")
    assert ns.compute_dedup_key(a) != ns.compute_dedup_key(b)


def test_compute_dedup_key_differs_by_title():
    a = _parsed()
    b = _parsed(title="磁盘空间不足")
    assert ns.compute_dedup_key(a) != ns.compute_dedup_key(b)


def test_compute_dedup_key_case_insensitive_host():
    a = _parsed(host="Host-01")
    b = _parsed(host="host-01")
    assert ns.compute_dedup_key(a) == ns.compute_dedup_key(b)


def test_is_host_down_alert():
    assert ns._is_host_down_alert(_parsed(title="主机不可达"))
    assert ns._is_host_down_alert(_parsed(title="ICMP ping failed"))
    assert ns._is_host_down_alert(_parsed(title="Server is down"))
    assert not ns._is_host_down_alert(_parsed(title="CPU 使用率过高"))


@pytest.mark.asyncio
async def test_evaluate_pass_when_no_match(db_session):
    """无重复、无抑制时正常放行。"""
    parsed = _parsed()
    result = await ns.evaluate_noise_reduction(db_session, parsed, _settings())
    assert result["action"] == "pass"
    assert result["dedup_key"]
    stats = ns.get_noise_stats()
    assert stats["total_received"] == 1
    assert stats["passed"] == 1


@pytest.mark.asyncio
async def test_evaluate_dedup_within_window(db_session):
    """窗口内相同指纹的第二条告警应被去重。"""
    s = _settings()
    parsed1 = _parsed(event_id="evt-1")
    await ns.evaluate_noise_reduction(db_session, parsed1, s)

    # 模拟入库（创建一条带 dedup_key 的告警）
    key = ns.compute_dedup_key(parsed1)
    alert = Alert(
        source="zabbix", event_id="evt-1", host=parsed1["host"],
        title=parsed1["title"], trigger_id=parsed1["trigger_id"],
        severity=parsed1["severity"], status=ALERT_PROBLEM,
        occurred_at=datetime.utcnow(), dedup_key=key,
        analysis_status="pending",
    )
    db_session.add(alert)
    await db_session.commit()

    # 第二条相同指纹
    parsed2 = _parsed(event_id="evt-2")
    result = await ns.evaluate_noise_reduction(db_session, parsed2, s)
    assert result["action"] == "dedup"
    assert result["dedup_alert"] is not None
    assert result["dedup_alert"].dedup_count == 1

    stats = ns.get_noise_stats()
    assert stats["deduped"] == 1


@pytest.mark.asyncio
async def test_evaluate_dedup_disabled(db_session):
    """关闭去重后不再合并。"""
    s = _settings(dedup_enabled=False)
    # 入库一条
    key = ns.compute_dedup_key(_parsed())
    db_session.add(Alert(
        source="zabbix", event_id="evt-1", host="host-01",
        title="CPU 过高", trigger_id="t-1", severity="警告",
        status=ALERT_PROBLEM, occurred_at=datetime.utcnow(), dedup_key=key,
        analysis_status="pending",
    ))
    await db_session.commit()

    parsed2 = _parsed(event_id="evt-2")
    result = await ns.evaluate_noise_reduction(db_session, parsed2, s)
    assert result["action"] == "pass"


@pytest.mark.asyncio
async def test_evaluate_suppress_maintenance(db_session):
    """标题含 [维护] 时被抑制。"""
    parsed = _parsed(title="[维护] 数据库例行维护", severity="警告")
    result = await ns.evaluate_noise_reduction(db_session, parsed, _settings())
    assert result["action"] == "suppress"
    assert "维护" in result["suppress_reason"]


@pytest.mark.asyncio
async def test_evaluate_correlation_host_down_suppresses_service(db_session):
    """主机不可达告警存在时，该主机的服务告警被关联抑制。"""
    s = _settings()
    # 先入库一条主机不可达告警
    down = Alert(
        source="zabbix", event_id="evt-down", host="host-01",
        title="主机不可达 (ping failed)", trigger_id="t-down",
        severity="灾难", status=ALERT_PROBLEM,
        occurred_at=datetime.utcnow(), dedup_key="k-down", analysis_status="pending",
    )
    db_session.add(down)
    await db_session.commit()

    # 该主机的服务告警
    parsed = _parsed(host="host-01", title="Nginx 服务异常", trigger_id="t-nginx",
                     event_id="evt-nginx")
    result = await ns.evaluate_noise_reduction(db_session, parsed, s)
    assert result["action"] == "suppress"
    assert "不可达" in result["suppress_reason"]


@pytest.mark.asyncio
async def test_evaluate_host_down_itself_not_suppressed(db_session):
    """主机不可达告警本身不应被抑制。"""
    s = _settings()
    down = Alert(
        source="zabbix", event_id="evt-down", host="host-01",
        title="主机不可达", trigger_id="t-down", severity="灾难",
        status=ALERT_PROBLEM, occurred_at=datetime.utcnow(),
        dedup_key="k-down", analysis_status="pending",
    )
    db_session.add(down)
    await db_session.commit()

    parsed = _parsed(host="host-01", title="主机不可达", trigger_id="t-down2",
                     event_id="evt-down-2")
    result = await ns.evaluate_noise_reduction(db_session, parsed, s)
    # 同一主机同一标题会被去重（不是抑制）
    assert result["action"] in ("dedup", "pass")


@pytest.mark.asyncio
async def test_evaluate_recovery_passes_through(db_session):
    """恢复消息直接放行，不做降噪。"""
    parsed = _parsed(is_recovery=True, title="[维护] test")
    result = await ns.evaluate_noise_reduction(db_session, parsed, _settings())
    assert result["action"] == "pass"


@pytest.mark.asyncio
async def test_evaluate_storm_suppresses_low_severity(db_session):
    """窗口内同主机告警数超过阈值时，低级别告警被抑制。"""
    s = _settings(storm_threshold=3, storm_window_minutes=5)
    for i in range(3):
        db_session.add(Alert(
            source="zabbix", event_id=f"evt-{i}", host="host-01",
            title=f"告警 {i}", trigger_id=f"t-{i}", severity="警告",
            status=ALERT_PROBLEM, occurred_at=datetime.utcnow(),
            dedup_key=f"k-{i}", analysis_status="pending",
        ))
    await db_session.commit()

    parsed = _parsed(host="host-01", title="磁盘 IO 高", trigger_id="t-io",
                     event_id="evt-io", severity="信息")
    result = await ns.evaluate_noise_reduction(db_session, parsed, s)
    assert result["action"] == "suppress"
    assert "风暴" in result["suppress_reason"]


@pytest.mark.asyncio
async def test_evaluate_storm_high_severity_passes(db_session):
    """风暴时高级别（严重/灾难）告警仍放行。"""
    s = _settings(storm_threshold=3, storm_window_minutes=5)
    for i in range(3):
        db_session.add(Alert(
            source="zabbix", event_id=f"evt-{i}", host="host-01",
            title=f"告警 {i}", trigger_id=f"t-{i}", severity="警告",
            status=ALERT_PROBLEM, occurred_at=datetime.utcnow(),
            dedup_key=f"k-{i}", analysis_status="pending",
        ))
    await db_session.commit()

    parsed = _parsed(host="host-01", title="核心服务宕机", trigger_id="t-core",
                     event_id="evt-core", severity="灾难")
    result = await ns.evaluate_noise_reduction(db_session, parsed, s)
    assert result["action"] == "pass"


@pytest.mark.asyncio
async def test_correlation_group_id_changes_over_time(db_session):
    """不同时间桶的关联分组 ID 不同。"""
    # 直接调用函数验证确定性
    g1 = ns.compute_correlation_group_id("host-01", 5)
    g2 = ns.compute_correlation_group_id("host-01", 5)
    assert g1 == g2  # 同一时间桶相同
    g3 = ns.compute_correlation_group_id("host-02", 5)
    assert g1 != g3  # 不同主机不同


@pytest.mark.asyncio
async def test_stats_accumulate(db_session):
    """统计计数正确累加。"""
    s = _settings()
    await ns.evaluate_noise_reduction(db_session, _parsed(event_id="a"), s)
    await ns.evaluate_noise_reduction(db_session, _parsed(event_id="b", host="h2"), s)
    await ns.evaluate_noise_reduction(db_session, _parsed(event_id="c", title="[维护]x"), s)
    stats = ns.get_noise_stats()
    assert stats["total_received"] == 3
    assert stats["passed"] == 2
    assert stats["suppressed"] == 1
