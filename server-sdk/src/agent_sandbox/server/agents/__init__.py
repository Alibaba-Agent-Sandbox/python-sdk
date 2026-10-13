"""Hosted coding-agent runtime for the sandbox HTTP server (opt-in ``agents`` group).

Public extension API::

    from agent_sandbox.server.agents import AgentAdapter, register_adapter

See ``docs/en/design/agents-api.md``.
"""

from __future__ import annotations

from . import events
from .adapters import (
    AdapterCapabilities,
    AdapterRegistry,
    AgentAdapter,
    EventParser,
    Invocation,
    InvocationFile,
    TurnContext,
    default_adapters,
    register_adapter,
)
from .config import (
    AgentSpec,
    GitSpec,
    LimitsSpec,
    McpServerSpec,
    ProviderSpec,
    WorkspaceSpec,
)
from .errors import AgentConfigError, AgentNotFoundError, AgentRuntimeError
from .events import ParsedEvent
from .redact import Redactor
from .runtime import AgentRuntime, Item, RuntimeEvent, Session, Turn
from .store import AgentStore

__all__ = [
    "AdapterCapabilities",
    "AdapterRegistry",
    "AgentAdapter",
    "AgentConfigError",
    "AgentNotFoundError",
    "AgentRuntime",
    "AgentRuntimeError",
    "AgentSpec",
    "AgentStore",
    "EventParser",
    "GitSpec",
    "Invocation",
    "InvocationFile",
    "Item",
    "LimitsSpec",
    "McpServerSpec",
    "ParsedEvent",
    "ProviderSpec",
    "Redactor",
    "RuntimeEvent",
    "Session",
    "Turn",
    "TurnContext",
    "WorkspaceSpec",
    "default_adapters",
    "events",
    "register_adapter",
]
