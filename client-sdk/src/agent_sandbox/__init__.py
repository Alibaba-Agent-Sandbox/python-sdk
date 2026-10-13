"""Agent Sandbox Client SDK — Create, manage, and interact with cloud sandboxes."""

from __future__ import annotations

from pkgutil import extend_path
from typing import Any

from agent_sandbox._version import __version__

# ``agent_sandbox`` is a shared namespace: ``agent_sandbox.server`` ships in the
# separate ``agent-sandbox-server`` distribution, possibly installed in another
# directory (editable installs, vendored layouts).
__path__ = extend_path(__path__, __name__)

__all__ = [
    "__version__",
    "Sandbox",
    "SandboxError",
    "AuthenticationError",
    "SandboxCreationError",
    "ExecutionError",
    "FileOperationError",
    "NetworkError",
    "sandbox",
]


def __getattr__(name: str) -> Any:
    if name == "Sandbox":
        from agent_sandbox.api.sandbox import Sandbox

        return Sandbox
    if name in (
        "SandboxError",
        "AuthenticationError",
        "SandboxCreationError",
        "ExecutionError",
        "FileOperationError",
        "NetworkError",
    ):
        from agent_sandbox.models import errors

        return getattr(errors, name)
    if name == "sandbox":
        from agent_sandbox.declarative.decorator import sandbox as _sandbox

        return _sandbox
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
