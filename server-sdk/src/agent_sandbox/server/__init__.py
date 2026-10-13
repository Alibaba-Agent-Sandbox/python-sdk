"""Container-side HTTP server — stdlib-only, zero external dependencies.

Quick start (inside a sandbox template's ``commands.py``)::

    from agent_sandbox.server import start
    start(9000)

Or for more control::

    from agent_sandbox.server import SandboxServer, ServerPolicy, command

    @command("greet")
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    server = SandboxServer(host="0.0.0.0", policy=ServerPolicy.only("transfer"))
    server.serve(port=9000)
"""

from __future__ import annotations

from ._version import __version__
from .app import SandboxServer, start
from .endpoints import CapabilityGroup
from .policy import PolicyDenied, ServerPolicy
from .registry import (
    CommandArg,
    CommandRegistry,
    RegisteredCommand,
    command,
    default_registry,
)
from .router import RouteInfo, RouteTable, default_table
from .routes_pty import (
    PtySession,
    PtySessionManager,
    pty_session_manager,
    start_pty_server,
)
from .types import ServerRequest, ServerResponse, SSEResponse

__all__ = [
    "__version__",
    "SandboxServer",
    "start",
    "ServerPolicy",
    "PolicyDenied",
    "CommandArg",
    "CommandRegistry",
    "RegisteredCommand",
    "command",
    "default_registry",
    "ServerRequest",
    "ServerResponse",
    "SSEResponse",
    "RouteTable",
    "RouteInfo",
    "CapabilityGroup",
    "default_table",
    "PtySession",
    "PtySessionManager",
    "pty_session_manager",
    "start_pty_server",
]
