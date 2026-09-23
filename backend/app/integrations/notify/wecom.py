"""企业微信群机器人：加签 + markdown 消息。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import quote_plus

from app.integrations.notify.base import NotifyChannel
from app.integrations.notify.render import render_markdown


class WeComChannel(NotifyChannel):
    platform = "wecom"
    max_length = 4096

    def _signed_url(self) -> str:
        if not self.secret:
            return self.webhook_url
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{self.secret}"
        digest = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = quote_plus(base64.b64encode(digest).decode("utf-8"))
        sep = "&" if "?" in self.webhook_url else "?"
        return f"{self.webhook_url}{sep}timestamp={timestamp}&sign={sign}"

    async def send_report(self, view: dict) -> None:
        content = render_markdown(view, max_len=3600)
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        await self._post(payload)

    async def send_test(self) -> None:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": "### ITOPS 通知测试\n> 连接成功，企业微信机器人配置正确。",
            },
        }
        await self._post(payload)
