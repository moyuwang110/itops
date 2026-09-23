"""安全工具：管理员口令哈希、JWT、第三方凭据加密(Fernet)与脱敏。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

from app.core.config import settings

_PBKDF2_ROUNDS = 120_000

# ---------- 管理员口令（PBKDF2-HMAC-SHA256，不落明文） ----------


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, rounds, salt_hex, hash_hex = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


# ---------- JWT ----------


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


__all__ = ["JWTError", "create_access_token", "decode_access_token"]


# ---------- 第三方凭据加密 ----------


class CredentialCipher:
    """Fernet 对称加密；密文以 enc:v1: 前缀标识，便于识别与轮换。"""

    _prefix = "enc:v1:"

    def __init__(self, key: str | None = None) -> None:
        raw = (key or settings.fernet_key).encode()
        # 兼容直接传入 32 字节原始密钥的情况
        try:
            self._fernet = Fernet(raw)
        except (ValueError, TypeError):
            self._fernet = Fernet(base64.urlsafe_b64encode(raw[:32].ljust(32, b"0")))

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None or plaintext == "":
            return plaintext
        if plaintext.startswith(self._prefix):
            return plaintext
        token = self._fernet.encrypt(plaintext.encode()).decode()
        return f"{self._prefix}{token}"

    def decrypt(self, value: str) -> str:
        if not value:
            return value
        if not value.startswith(self._prefix):
            # 兼容历史明文（不阻断读取）
            return value
        try:
            return self._fernet.decrypt(value[len(self._prefix):].encode()).decode()
        except InvalidToken as exc:
            raise ValueError("凭据解密失败：密钥不匹配或数据损坏") from exc

    def is_encrypted(self, value: str) -> bool:
        return bool(value) and value.startswith(self._prefix)


cipher = CredentialCipher()

# 需要脱敏的字段名（小写匹配）
SENSITIVE_KEYS = {
    "api_key", "apikey", "token", "secret", "password", "passwd",
    "webhook_url", "secret_key", "sign_secret", "access_key",
}
MASK = "******"


def mask_settings(data: Any, sensitive_keys: set[str] | None = None) -> Any:
    """递归脱敏：敏感键若有值则返回掩码；webhook_url 仅保留协议+主机。"""
    keys = sensitive_keys or SENSITIVE_KEYS
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            lk = k.lower()
            if lk in {"webhook_url"} and isinstance(v, str) and v:
                out[k] = _mask_url(v)
            elif lk in keys and v not in (None, ""):
                out[k] = MASK
            else:
                out[k] = mask_settings(v, keys)
        return out
    if isinstance(data, list):
        return [mask_settings(i, keys) for i in data]
    return data


def _mask_url(url: str) -> str:
    try:
        scheme, rest = url.split("://", 1)
        host = rest.split("/", 1)[0]
        return f"{scheme}://{host}/******"
    except (ValueError, AttributeError):
        return MASK


def dumps_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)
