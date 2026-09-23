"""认证相关 Schema。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import create_access_token


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    username: str


def build_login_response(username: str) -> LoginResponse:
    token = create_access_token(username, {"jti": uuid.uuid4().hex})
    return LoginResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        username=username,
    )
