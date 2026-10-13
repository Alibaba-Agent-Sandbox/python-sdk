"""Adapter registry: built-ins, entry points and ``ABX_AGENTS_ADAPTER_MODULES``."""

from __future__ import annotations

import importlib
import logging
import os
import threading

from .base import (
    AdapterCapabilities,
    AgentAdapter,
    EventParser,
    Invocation,
    InvocationFile,
    TurnContext,
)
from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter
from .command import CommandAdapter
from .cursor import CursorAdapter
from .qwen_code import QwenCodeAdapter

__all__ = [
    "AdapterCapabilities",
    "AdapterRegistry",
    "AgentAdapter",
    "EventParser",
    "Invocation",
    "InvocationFile",
    "TurnContext",
    "default_adapters",
    "register_adapter",
    "ENTRY_POINT_GROUP",
    "MODULES_ENV_VAR",
]

ENTRY_POINT_GROUP = "agent_sandbox.agent_adapters"
MODULES_ENV_VAR = "ABX_AGENTS_ADAPTER_MODULES"

_log = logging.getLogger(__name__)


class AdapterRegistry:
    """Name/alias → adapter class registry."""

    def __init__(self, *, builtins: bool = True) -> None:
        self._classes: dict[str, type[AgentAdapter]] = {}
        self._aliases: dict[str, str] = {}
        self._lock = threading.Lock()
        if builtins:
            for cls in (
                CodexAdapter,
                ClaudeCodeAdapter,
                CursorAdapter,
                QwenCodeAdapter,
                CommandAdapter,
            ):
                self.register(cls)

    def register(self, cls: type[AgentAdapter], *, override: bool = False) -> type[AgentAdapter]:
        """Register *cls*; a name/alias clash is an error unless ``override=True``."""
        name = getattr(cls, "name", None)
        if not name or not isinstance(name, str):
            raise ValueError(f"{cls!r} must define a non-empty class attribute 'name'")
        with self._lock:
            keys = (name, *cls.aliases)
            if not override:
                for key in keys:
                    owner = self._aliases.get(key) or (key if key in self._classes else None)
                    if owner is not None and owner != name:
                        raise ValueError(
                            f"adapter name/alias {key!r} is already registered by {owner!r}"
                        )
                if name in self._classes:
                    raise ValueError(f"adapter {name!r} is already registered (use override=True)")
            self._classes[name] = cls
            for alias in cls.aliases:
                self._aliases[alias] = name
        return cls

    def resolve_name(self, name: str) -> str | None:
        """Canonical adapter name for *name* or an alias (``None`` if unknown)."""
        key = name.strip().lower()
        if key in self._classes:
            return key
        return self._aliases.get(key)

    def get(self, name: str) -> AgentAdapter | None:
        """A fresh adapter instance for *name* (or alias)."""
        canonical = self.resolve_name(name)
        return self._classes[canonical]() if canonical else None

    def names(self) -> list[str]:
        """Canonical adapter names."""
        return sorted(self._classes)

    def load_plugins(self) -> list[str]:
        """Load entry-point and env-var adapters; returns the names loaded."""
        loaded: list[str] = []
        try:
            from importlib.metadata import entry_points

            for ep in entry_points(group=ENTRY_POINT_GROUP):
                try:
                    cls = ep.load()
                    self.register(cls)
                    loaded.append(cls.name)
                except Exception as exc:  # plugin errors must not break the server
                    _log.warning("failed to load agent adapter entry point %s: %s", ep.name, exc)
        except Exception as exc:
            _log.debug("entry point discovery failed: %s", exc)
        for module in filter(
            None, (m.strip() for m in os.environ.get(MODULES_ENV_VAR, "").split(","))
        ):
            try:
                importlib.import_module(module)
            except Exception as exc:
                _log.warning("failed to import agent adapter module %s: %s", module, exc)
        return loaded


_default = AdapterRegistry()
_plugins_loaded = False
_plugins_lock = threading.Lock()


def default_adapters() -> AdapterRegistry:
    """The process-wide registry (plugins are discovered on first use)."""
    global _plugins_loaded
    with _plugins_lock:
        if not _plugins_loaded:
            _plugins_loaded = True
            _default.load_plugins()
    return _default


def register_adapter(cls: type[AgentAdapter], *, override: bool = False) -> type[AgentAdapter]:
    """Register *cls* in the default registry (usable as a class decorator)."""
    return _default.register(cls, override=override)
