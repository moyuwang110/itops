"""飞书自定义机器人：加签 + interactive 卡片。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import quote_plus

from app.integrations.notify.base import NotifyChannel
from app.integrations.notify.render import render_markdown, severity_color


class FeishuChannel(NotifyChannel):
    platform = "feishu"
    max_length = 28000

    def _signed_url(self) -> str:
        if not self.secret:
            return self.webhook_url
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{self.secret}"
        digest = hmac.new(string_to_sign.encode("utf-8"),
                          digestmod=hashlib.sha256).digest()
        sign = quote_plus(base64.b64encode(digest).decode("utf-8"))
        sep = "&" if "?" in self.webhook_url else "?"
        return f"{self.webhook_url}{sep}timestamp={timestamp}&sign={sign}"

    def _card(self, view: dict) -> dict:
        md = render_markdown(view, max_len=20000)
        color = severity_color(view.get("severity", ""))
        title = (f"{view.get('title') or 'Zabbix 告警'}"
                 f"（{'已恢复' if view.get('status') == 'resolved' else '告警'}）")
        elements = [
            {"tag": "div", "text": {"tag": "lark_md", "content": md}},
        ]
        if view.get("link"):
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看完整分析报告"},
                    "url": view["link"],
                    "type": "primary",
                }],
            })
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title[:120]},
                    "template": "green" if view.get("status") == "resolved" else color,
                },
                "elements": elements,
            },
        }

    async def send_report(self, view: dict) -> None:
        await self._post(self._card(view))

    async def send_test(self) -> None:
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "ITOPS 通知测试"},
                    "template": "blue",
                },
                "elements": [{
                    "tag": "div",
                    "text": {"tag": "lark_md",
                             "content": "**连接成功**\nITOPS 飞书机器人配置正确。"},
                }],
            },
        }
        await self._post(payload)
