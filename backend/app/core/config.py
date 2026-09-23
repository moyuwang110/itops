"""全局配置：环境变量 / .env 注入。"""
from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 基础
    app_name: str = "ITOPS 智能运维分析平台"
    debug: bool = False
    public_base_url: str = "http://localhost:8080"
    cors_origins: str = "*"

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./data/itops.db"

    # 安全 / 登录
    admin_username: str = "admin"
    admin_password: str = "ChangeMe_2026!"
    jwt_secret_key: str = "dev-only-jwt-secret-please-change"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    fernet_key: str = "pR5JQWEyc02scbP_TNs52W89eKVdY3KPUQOptDzwlnY="
    zabbix_webhook_token: str = ""

    # 生产安全：置 true 时，若仍在使用内置默认密钥/口令则拒绝启动
    require_secure_secrets: bool = False
    # API 文档开关（生产建议关闭）
    enable_docs: bool = True

    # 外部调用
    http_timeout: float = 120.0

    # 分析默认参数
    analysis_auto_enabled: bool = True
    analysis_before_minutes: int = 30
    analysis_after_minutes: int = 10
    auto_notify_channels: str = ""

    @field_validator("analysis_before_minutes", "analysis_after_minutes")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("分析时间窗口不能为负数")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins or self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def auto_notify_channel_list(self) -> list[str]:
        return [c.strip() for c in self.auto_notify_channels.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# 内置开发默认值（require_secure_secrets=true 时禁止沿用）
DEFAULT_ADMIN_PASSWORDS = {"ChangeMe_2026!"}
DEFAULT_JWT_SECRETS = {
    "dev-only-jwt-secret-please-change",
    "dev-only-jwt-secret-please-change-0123456789abcdef",
}
DEFAULT_FERNET_KEYS = {"pR5JQWEyc02scbP_TNs52W89eKVdY3KPUQOptDzwlnY="}


def validate_secure_secrets(s: Settings) -> None:
    """生产模式启动前强校验：内置默认口令/密钥必须全部更换。"""
    insecure: list[str] = []
    if s.admin_password in DEFAULT_ADMIN_PASSWORDS:
        insecure.append("ADMIN_PASSWORD")
    if s.jwt_secret_key in DEFAULT_JWT_SECRETS:
        insecure.append("JWT_SECRET_KEY")
    if s.fernet_key in DEFAULT_FERNET_KEYS:
        insecure.append("FERNET_KEY")
    if insecure:
        raise RuntimeError(
            "检测到未更换的内置默认密钥/口令：%s。"
            "请在环境变量或 .env 中设置自定义值后再启动（REQUIRE_SECURE_SECRETS=true）。"
            % ", ".join(insecure)
        )
