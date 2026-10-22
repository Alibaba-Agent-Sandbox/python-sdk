"""Structural protocol package with lazy historical wire exports."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_sandbox.protocol.port import PortClient as PortClient
    from agent_sandbox.providers.shared.e2b.code_interpreter import (
        CodeInterpreterProtocol as CodeInterpreterProtocol,
    )
    from agent_sandbox.providers.shared.e2b.filesystem import (
        FilesystemProtocol as FilesystemProtocol,
    )
    from agent_sandbox.providers.shared.e2b.process import ProcessProtocol as ProcessProtocol
    from agent_sandbox.providers.shared.e2b.sandbox import SandboxProtocol as SandboxProtocol
    from agent_sandbox.providers.shared.e2b.terminal import TerminalSession as TerminalSession

__all__ = [
    "SandboxProtocol",
    "ProcessProtocol",
    "FilesystemProtocol",
    "CodeInterpreterProtocol",
    "TerminalSession",
    "PortClient",
]


def __getattr__(name: str) -> Any:
    modules = {
        "SandboxProtocol": "sandbox",
        "ProcessProtocol": "process",
        "FilesystemProtocol": "filesystem",
        "CodeInterpreterProtocol": "code_interpreter",
        "TerminalSession": "terminal",
        "PortClient": "port",
    }
    if name not in modules:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(f"agent_sandbox.protocol.{modules[name]}"), name)
