"""自动分析条件规则评估测试。"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.auto_analysis_rules import should_auto_analyze


def _setting(**kw):
    defaults = dict(auto_analysis=True, auto_analysis_rules=[])
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _parsed(**kw):
    defaults = dict(
        event_id="e1", host="host-01", host_id="1",
        title="CPU 使用率过高", trigger_id="t1",
        severity="警告", is_recovery=False,
    )
    defaults.update(kw)
    return defaults


def test_auto_analysis_off_returns_false():
    assert should_auto_analyze(_parsed(), _setting(auto_analysis=False))[0] is False


def test_no_rules_analyze_all():
    """无规则时全部自动分析（向后兼容）。"""
    ok, reason = should_auto_analyze(_parsed(), _setting())
    assert ok is True
    assert "无规则" in reason


def test_severity_rule_match():
    rule = {"name": "严重告警", "enabled": True, "severities": ["严重", "灾难"],
            "hosts": [], "host_pattern": "", "time_ranges": [], "keywords": []}
    ok, reason = should_auto_analyze(
        _parsed(severity="灾难"), _setting(auto_analysis_rules=[rule])
    )
    assert ok is True
    assert reason == "严重告警"


def test_severity_rule_no_match():
    rule = {"name": "严重告警", "enabled": True, "severities": ["严重", "灾难"],
            "hosts": [], "host_pattern": "", "time_ranges": [], "keywords": []}
    ok, _ = should_auto_analyze(
        _parsed(severity="警告"), _setting(auto_analysis_rules=[rule])
    )
    assert ok is False


def test_host_exact_match():
    rule = {"name": "prod主机", "enabled": True, "severities": [],
            "hosts": ["prod-db-01", "prod-web-01"], "host_pattern": "",
            "time_ranges": [], "keywords": []}
    ok, _ = should_auto_analyze(
        _parsed(host="prod-db-01"), _setting(auto_analysis_rules=[rule])
    )
    assert ok is True
    ok, _ = should_auto_analyze(
        _parsed(host="dev-db-01"), _setting(auto_analysis_rules=[rule])
    )
    assert ok is False


def test_host_pattern_match():
    rule = {"name": "prod通配", "enabled": True, "severities": [],
            "hosts": [], "host_pattern": "prod-*",
            "time_ranges": [], "keywords": []}
    ok, _ = should_auto_analyze(
        _parsed(host="PROD-DB-01"), _setting(auto_analysis_rules=[rule])
    )
    assert ok is True
    ok, _ = should_auto_analyze(
        _parsed(host="test-db-01"), _setting(auto_analysis_rules=[rule])
    )
    assert ok is False


def test_keyword_match():
    rule = {"name": "数据库告警", "enabled": True, "severities": [],
            "hosts": [], "host_pattern": "",
            "time_ranges": [], "keywords": ["mysql", "数据库", "慢查询"]}
    ok, _ = should_auto_analyze(
        _parsed(title="MySQL 连接数过高"), _setting(auto_analysis_rules=[rule])
    )
    assert ok is True
    ok, _ = should_auto_analyze(
        _parsed(title="CPU 使用率过高"), _setting(auto_analysis_rules=[rule])
    )
    assert ok is False


def test_time_range_match():
    """当前时间应落在 00:00-23:59 范围内（几乎总是成立）。"""
    rule = {"name": "工作时间", "enabled": True, "severities": [],
            "hosts": [], "host_pattern": "",
            "time_ranges": [{"start": "00:00", "end": "23:59"}], "keywords": []}
    ok, _ = should_auto_analyze(_parsed(), _setting(auto_analysis_rules=[rule]))
    assert ok is True


def test_time_range_no_match():
    """构造一个不包含当前时间的区间。用 1 分钟窗口排除当前。"""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    # 取 2 小时前的 1 分钟窗口，确保不包含当前
    past = (now - timedelta(hours=2)).strftime("%H:%M")
    past_end = (now - timedelta(hours=2, minutes=-1)).strftime("%H:%M")
    rule = {"name": "过去时段", "enabled": True, "severities": [],
            "hosts": [], "host_pattern": "",
            "time_ranges": [{"start": past, "end": past_end}], "keywords": []}
    ok, _ = should_auto_analyze(_parsed(), _setting(auto_analysis_rules=[rule]))
    assert ok is False


def test_disabled_rule_skipped():
    rule = {"name": "停用规则", "enabled": False, "severities": ["警告"],
            "hosts": [], "host_pattern": "", "time_ranges": [], "keywords": []}
    ok, _ = should_auto_analyze(
        _parsed(severity="警告"), _setting(auto_analysis_rules=[rule])
    )
    # 规则停用 → 不匹配 → 不分析
    assert ok is False


def test_combined_conditions_and():
    """规则内多条件 AND：级别+主机都满足才触发。"""
    rule = {"name": "prod严重", "enabled": True, "severities": ["严重", "灾难"],
            "hosts": ["prod-01"], "host_pattern": "",
            "time_ranges": [], "keywords": []}
    # 级别满足但主机不满足
    ok, _ = should_auto_analyze(
        _parsed(severity="灾难", host="dev-01"), _setting(auto_analysis_rules=[rule])
    )
    assert ok is False
    # 都满足
    ok, _ = should_auto_analyze(
        _parsed(severity="灾难", host="prod-01"), _setting(auto_analysis_rules=[rule])
    )
    assert ok is True


def test_rules_or_relation():
    """多条规则间 OR：任一匹配即触发。"""
    rules = [
        {"name": "严重", "enabled": True, "severities": ["严重", "灾难"],
         "hosts": [], "host_pattern": "", "time_ranges": [], "keywords": []},
        {"name": "prod主机", "enabled": True, "severities": [],
         "hosts": ["prod-01"], "host_pattern": "",
         "time_ranges": [], "keywords": []},
    ]
    ok, _ = should_auto_analyze(
        _parsed(severity="警告", host="prod-01"), _setting(auto_analysis_rules=rules)
    )
    assert ok is True  # 匹配第二条
