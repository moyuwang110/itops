"""统一业务异常与全局异常处理。"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class BizError(Exception):
    """业务错误：返回 200 体外的标准错误结构，HTTP 状态码可指定。"""

    def __init__(self, message: str, code: str = "biz_error", http_status: int = 400,
                 detail: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status
        self.detail = detail


class IntegrationError(BizError):
    """外部平台（Zabbix/日志平台/大模型/IM）调用失败。"""

    def __init__(self, platform: str, message: str, detail: Any = None) -> None:
        super().__init__(
            f"[{platform}] {message}",
            code=f"integration_{platform}_error",
            http_status=502,
            detail=detail,
        )


class ConfigMissingError(BizError):
    def __init__(self, what: str) -> None:
        super().__init__(f"{what} 未配置或未启用，请先在“集成配置”中完成配置",
                         code="config_missing", http_status=400)


def _error_body(code: str, message: str, detail: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"ok": False, "code": code, "message": message}
    if detail is not None:
        body["detail"] = detail
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def _biz_handler(_request: Request, exc: BizError) -> JSONResponse:
        if exc.http_status >= 500:
            logger.error("业务异常: %s %s", exc.message, exc.detail or "")
        return JSONResponse(
            status_code=exc.http_status,
            content=_error_body(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request,
                                  exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("validation_error", "请求参数校验失败",
                                exc.errors()),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常 %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_error_body("internal_error", "服务器内部错误，请查看后端日志"),
        )
