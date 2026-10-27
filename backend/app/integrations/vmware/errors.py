"""vCenter 适配器业务异常。"""
from __future__ import annotations


class VCenterError(RuntimeError):
    """vCenter 业务错误基类。"""

    def __init__(self, message: str, *, code: str = "vcenter_error", http_status: int = 502):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


__all__ = ["VCenterError"]