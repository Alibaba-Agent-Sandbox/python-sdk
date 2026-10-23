"""Session assembly for providers that explicitly select the shared E2B wire protocol."""

from __future__ import annotations

from typing import Any

from .code_interpreter import UnsupportedCodeProtocol
from .filesystem import FilesystemProtocol
from .process import ProcessProtocol
from .sandbox import SandboxProtocol


def session_protocols(http: Any, *, provider_id: str = "unknown") -> dict[str, Any]:
    return {
        "sandbox_protocol": SandboxProtocol(http),
        "process_protocol": ProcessProtocol(http),
        "filesystem_protocol": FilesystemProtocol(http),
        "code_interpreter_protocol": UnsupportedCodeProtocol(provider_id),
    }


async def prepare_session(provider: Any, info: Any) -> dict[str, Any]:
    from .auth import EnvdTokenManager

    options: dict[str, Any] = {}
    if getattr(provider, "envd_allow_missing", False):
        options = {
            "allow_missing": True,
            "basic_user": getattr(provider, "envd_basic_user", "root") or "root",
        }
    return {
        "envd_token": EnvdTokenManager(
            info.envd_access_token, sandbox_id=info.sandbox_id, **options
        )
    }
