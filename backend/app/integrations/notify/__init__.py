"""飞书 / 企业微信群机器人通知。"""
from __future__ import annotations

from app.core.exceptions import IntegrationError
from app.integrations.notify.feishu import FeishuChannel
from app.integrations.notify.wecom import WeComChannel

_CHANNELS = {"feishu": FeishuChannel, "wecom": WeComChannel}


def build_channel(provider: str, conf: dict):
    cls = _CHANNELS.get(provider)
    if cls is None:
        raise IntegrationError("notify", f"不支持的通知渠道: {provider}")
    return cls(conf)


async def notify_tester(conf: dict) -> tuple[bool, str]:
    provider = conf.get("_provider", "")
    try:
        channel = build_channel(provider, conf)
        await channel.send_test()
        return True, "测试消息发送成功"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
