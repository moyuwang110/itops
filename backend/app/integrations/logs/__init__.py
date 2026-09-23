"""Graylog / Loki / Elasticsearch 日志平台适配。"""
from app.integrations.logs.base import LogPlatformClient, LogQuery
from app.integrations.logs.graylog import GraylogClient
from app.integrations.logs.loki import LokiClient
from app.integrations.logs.elasticsearch import ElasticsearchClient

_PLATFORMS = {
    "graylog": GraylogClient,
    "loki": LokiClient,
    "elasticsearch": ElasticsearchClient,
}


def build_platform_client(provider: str, conf: dict) -> LogPlatformClient:
    cls = _PLATFORMS.get(provider)
    if cls is None:
        raise ValueError(f"不支持的日志平台: {provider}")
    return cls(conf)


async def log_platform_tester(conf: dict) -> tuple[bool, str]:
    provider = conf.get("_provider", "")
    try:
        client = build_platform_client(provider, conf)
        count = await client.test()
        return True, f"连接成功，测试查询返回 {count} 条日志"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


__all__ = [
    "LogPlatformClient",
    "LogQuery",
    "GraylogClient",
    "LokiClient",
    "ElasticsearchClient",
    "build_platform_client",
    "log_platform_tester",
]
