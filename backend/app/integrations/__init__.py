"""外部平台适配器注册中心：避免上层服务与具体适配器循环依赖。"""
from __future__ import annotations

from typing import Awaitable, Callable

# provider -> async test(settings: dict) -> tuple[bool, str]
CONNECTION_TESTERS: dict[str, Callable[[dict], Awaitable[tuple[bool, str]]]] = {}

# provider -> 适配器工厂(settings: dict) -> client 实例（由各适配器模块注册）
CLIENT_FACTORIES: dict[str, Callable[[dict], object]] = {}


def register_tester(provider: str, func: Callable[[dict], Awaitable[tuple[bool, str]]]) -> None:
    CONNECTION_TESTERS[provider] = func


def register_client_factory(provider: str, factory: Callable[[dict], object]) -> None:
    CLIENT_FACTORIES[provider] = factory
