"""In-memory registry of agent definitions (secrets live here only, never on disk)."""

from __future__ import annotations

import json
import os
import threading
from typing import TYPE_CHECKING, Any

from .config import AgentSpec
from .errors import AgentConfigError, AgentNotFoundError

if TYPE_CHECKING:
    import builtins
    from collections.abc import Mapping

    from .adapters import AdapterRegistry

__all__ = ["AgentStore", "CONFIG_ENV_VAR"]

CONFIG_ENV_VAR = "ABX_AGENTS_CONFIG"


class AgentStore:
    """Thread-safe name → :class:`AgentSpec` map."""

    def __init__(self, adapters: AdapterRegistry, *, allow_command: bool = True) -> None:
        self._adapters = adapters
        self._allow_command = allow_command
        self._specs: dict[str, AgentSpec] = {}
        self._lock = threading.Lock()

    def validate(self, spec: AgentSpec) -> None:
        """Raise :class:`AgentConfigError` when *spec* cannot run on this server."""
        problems: list[str] = []
        canonical = self._adapters.resolve_name(spec.runtime)
        adapter = self._adapters.get(spec.runtime)
        if adapter is None or canonical is None:
            available = ", ".join(self._adapters.names())
            problems.append(f"runtime: unknown runtime {spec.runtime!r}; available: {available}")
        else:
            spec.runtime = canonical
            if canonical == "command" and not self._allow_command:
                problems.append(
                    "runtime 'command' is disabled on this server (ABX_AGENTS_ALLOW_COMMAND=0)"
                )
            if spec.extra_args and not self._allow_command:
                problems.append(
                    "extra_args is disabled on this server (ABX_AGENTS_ALLOW_COMMAND=0)"
                )
            problems.extend(adapter.validate(spec))
        if problems:
            raise AgentConfigError(problems)

    def put(self, spec: AgentSpec) -> AgentSpec:
        """Validate and register (or replace) *spec*."""
        self.validate(spec)
        with self._lock:
            self._specs[spec.name] = spec
        return spec

    def get(self, name: str) -> AgentSpec | None:
        """The definition called *name* (or ``None``)."""
        with self._lock:
            return self._specs.get(name)

    def require(self, name: str) -> AgentSpec:
        """Like :meth:`get` but raises :class:`AgentNotFoundError`."""
        spec = self.get(name)
        if spec is None:
            raise AgentNotFoundError(f"agent {name!r} is not registered", param="model")
        return spec

    def delete(self, name: str) -> bool:
        """Remove a definition; returns whether it existed."""
        with self._lock:
            return self._specs.pop(name, None) is not None

    def list(self) -> list[AgentSpec]:
        """All definitions, sorted by name."""
        with self._lock:
            return sorted(self._specs.values(), key=lambda s: s.name)

    def resolve(self, model: str) -> AgentSpec:
        """Resolve an OpenAI ``model`` string: definition name, else a runtime name/alias.

        A runtime name creates (and registers) an *ephemeral* default agent.
        """
        spec = self.get(model)
        if spec is not None:
            return spec
        canonical = self._adapters.resolve_name(model)
        if canonical is None or canonical == "command":
            raise AgentNotFoundError(
                f"model {model!r} is not a registered agent or runtime "
                f"(runtimes: {', '.join(n for n in self._adapters.names() if n != 'command')})",
                param="model",
            )
        spec = AgentSpec(name=canonical, runtime=canonical, ephemeral=True)
        self.validate(spec)
        with self._lock:
            return self._specs.setdefault(canonical, spec)

    def load_config(
        self, source: str | Mapping[str, Any], environ: Mapping[str, str] | None = None
    ) -> builtins.list[str]:
        """Load definitions from a JSON file path or an already-parsed mapping.

        Accepted shapes: one agent object, a list of agents, or ``{"agents": [...]}``.
        ``${VAR}`` placeholders are expanded from *environ* (default: ``os.environ``).
        """
        if isinstance(source, str):
            with open(source, encoding="utf-8") as fh:
                data: Any = json.load(fh)
        else:
            data = source
        if isinstance(data, dict) and "agents" in data:
            data = data["agents"]
        items = data if isinstance(data, list) else [data]
        env = os.environ if environ is None else environ
        names: list[str] = []
        for item in items:
            spec = AgentSpec.from_dict(item, environ=env)
            self.put(spec)
            names.append(spec.name)
        return names
