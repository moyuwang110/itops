"""轻量内存限流器：基于客户端 IP 的滑动窗口计数。

适用于登录等敏感接口的防暴力破解。单进程有效；多副本部署时需替换为
Redis 等共享存储（本项目当前单实例，内存方案足够）。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class SlidingWindowRateLimiter:
    """滑动窗口：每个 key 在 window_seconds 内最多 max_requests 次。"""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """返回 (是否允许, 剩余可用次数)。"""
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False, 0
            bucket.append(now)
            return True, self.max_requests - len(bucket)

    def reset(self) -> None:
        """清空所有计数（测试用）。"""
        with self._lock:
            self._buckets.clear()


# 登录限流器：每 IP 每分钟最多 5 次（成功/失败均计数）
login_limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
