"""Transport contracts and lazy exports."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_sandbox.transport.auth_contract import ApiKeyAuth as ApiKeyAuth
    from agent_sandbox.transport.auth_contract import AuthProvider as AuthProvider
    from agent_sandbox.transport.config import TransportConfig as TransportConfig
    from agent_sandbox.transport.http import HttpClient as HttpClient


__all__ = ["TransportConfig", "HttpClient", "ApiKeyAuth", "AuthProvider"]


def __getattr__(name: str) -> Any:
    modules = {
        "TransportConfig": "agent_sandbox.transport.config",
        "HttpClient": "agent_sandbox.transport.http",
        "ApiKeyAuth": "agent_sandbox.transport.auth_contract",
        "AuthProvider": "agent_sandbox.transport.auth_contract",
    }
    if name not in modules:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(modules[name]), name)
