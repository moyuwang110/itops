"""导入并注册全部外部平台适配器（连通性测试器/客户端工厂）。

在应用启动时 import 一次即可，后续通过 config_service 的测试入口与各 service 使用。
"""
from __future__ import annotations

from app.integrations import register_client_factory, register_tester

# ---- Zabbix ----
from app.integrations.zabbix.client import ZabbixClient, zabbix_tester

register_tester("zabbix", zabbix_tester)
register_client_factory("zabbix", lambda conf: ZabbixClient(conf))

# ---- 大模型 ----
from app.integrations.llm import PROVIDER_TESTERS as _LLM_TESTERS

for _name, _tester in _LLM_TESTERS.items():
    register_tester(_name, _tester)

# ---- 日志平台 ----
from app.integrations.logs import build_platform_client, log_platform_tester

for _name in ("graylog", "loki", "elasticsearch"):
    register_tester(_name, lambda conf, n=_name: log_platform_tester(
        {**conf, "_provider": n}))
    register_client_factory(
        _name, lambda conf, n=_name: build_platform_client(n, conf)
    )

# ---- 通知渠道 ----
from app.integrations.notify import build_channel, notify_tester

for _name in ("feishu", "wecom"):
    register_tester(
        _name, lambda conf, n=_name: notify_tester({**conf, "_provider": n})
    )
    register_client_factory(
        _name, lambda conf, n=_name: build_channel(n, conf)
    )
