"""L4 High-level API — user-facing classes."""

from __future__ import annotations

from agent_sandbox.api.capability import ResolvedCapabilities, resolve_capabilities
from agent_sandbox.api.code import CodeContextModule
from agent_sandbox.api.commands import CommandsModule
from agent_sandbox.api.files import FilesModule
from agent_sandbox.api.network import NetworkModule
from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.api.server_capabilities import ServerCapabilities
from agent_sandbox.api.server_client import ServerClient

__all__ = [
    "Sandbox",
    "ServerClient",
    "ServerCapabilities",
    "CommandsModule",
    "FilesModule",
    "CodeContextModule",
    "NetworkModule",
    "ResolvedCapabilities",
    "resolve_capabilities",
]
