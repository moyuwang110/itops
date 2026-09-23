"""日志平台适配器基类与归一化结构。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.exceptions import IntegrationError


@dataclass
class LogQuery:
    start_ts: int
    end_ts: int
    keyword: str = ""          # 原始查询串（用户输入，平台原生语法）
    host: str = ""
    limit: int = 100
    # 多关键词（任一匹配，OR 语义）；为空则回退到 keyword
    keywords: list[str] | None = None


class LogPlatformClient:
    platform = "base"

    def __init__(self, conf: dict) -> None:
        self.conf = conf
        self.timeout = float(conf.get("timeout") or 15)

    async def query(self, q: LogQuery) -> list[dict]:  # pragma: no cover - 抽象
        raise NotImplementedError

    async def test(self) -> int:
        """连通性测试：返回采样条数。"""
        now = int(datetime.now(timezone.utc).timestamp())
        rows = await self.query(LogQuery(now - 300, now, limit=5))
        return len(rows)

    def _error(self, message: str, detail=None) -> IntegrationError:
        return IntegrationError(self.platform, message, detail=detail)

    @staticmethod
    def normalize(ts: int | float | None, host: str, source: str,
                  level: str, message: str, raw: dict | None = None) -> dict:
        if ts:
            iso = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        else:
            iso = ""
        return {
            "ts": int(ts) if ts else 0,
            "timestamp": iso,
            "host": host or "",
            "source": source or "",
            "level": str(level or ""),
            "message": message or "",
            "raw": raw or {},
        }
