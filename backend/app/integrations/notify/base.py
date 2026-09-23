"""通知渠道基类。"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError


class NotifyChannel:
    platform = "base"
    # 机器人消息体长度上限（字节/字符），子类覆盖
    max_length = 4000

    def __init__(self, conf: dict) -> None:
        self.webhook_url = conf.get("webhook_url", "")
        self.secret = conf.get("secret", "")
        self.timeout = float(conf.get("timeout") or settings.http_timeout)
        if not self.webhook_url:
            raise IntegrationError(self.platform, "Webhook 地址未配置")

    def _signed_url(self) -> str:  # pragma: no cover - 抽象
        raise NotImplementedError

    async def _post(self, payload: dict) -> None:
        url = self._signed_url()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                resp = await http.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise IntegrationError(self.platform, f"请求失败: {exc}") from exc
        if resp.status_code != 200:
            raise IntegrationError(self.platform,
                                   f"HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise IntegrationError(self.platform, "返回非 JSON",
                                   detail=resp.text[:300]) from exc
        if data.get("errcode") not in (0, None) or data.get("StatusCode", 0) not in (0, None):
            raise IntegrationError(
                self.platform,
                f"平台返回错误: {data.get('errmsg') or data}",
                detail=str(data)[:300],
            )

    async def send_test(self) -> None:  # pragma: no cover - 抽象
        raise NotImplementedError
