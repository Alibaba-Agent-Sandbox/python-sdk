"""Adapter interface for agent runtimes (Codex, Claude Code, ...) — stdlib-only.

An adapter knows how to *invoke* a coding-agent CLI for one turn and how to
*parse* its machine-readable output into :class:`ParsedEvent` objects.  It never
spawns processes itself; :mod:`easy_sandbox.server.agents.runtime` does, which
keeps adapters pure and trivially unit-testable.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ..config import AgentSpec
    from ..events import ParsedEvent

__all__ = [
    "AdapterCapabilities",
    "AgentAdapter",
    "EventParser",
    "Invocation",
    "InvocationFile",
    "TurnContext",
    "classify_text",
    "toml_key",
    "toml_value",
    "with_preamble",
]


@dataclasses.dataclass(frozen=True)
class AdapterCapabilities:
    """What a runtime supports (reported by ``GET /agents/runtimes``)."""

    resume: bool = True
    partial_deltas: bool = False
    mcp: bool = True
    system_prompt: str = "preamble"  # "flag" | "preamble"
    base_url: bool = True
    max_turns: bool = False
    budget: bool = False
    experimental: bool = False


@dataclasses.dataclass
class InvocationFile:
    """A file the runtime must write before spawning the process."""

    path: str
    content: bytes
    mode: int = 0o600
    merge_key: str | None = None  # merge into an existing JSON file under this key
    git_exclude: bool = False  # add to ``.git/info/exclude`` of the workdir repo


@dataclasses.dataclass
class Invocation:
    """Everything needed to spawn one turn.  Secrets only in ``env``."""

    argv: list[str]
    env: dict[str, str] = dataclasses.field(default_factory=dict)
    stdin: bytes | None = None
    files: list[InvocationFile] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class TurnContext:
    """Inputs of :meth:`AgentAdapter.build_invocation`."""

    spec: AgentSpec
    prompt: str
    workdir: str
    turn_dir: str
    native_session_id: str | None = None
    first_turn: bool = True
    is_root: bool = dataclasses.field(default_factory=lambda: _geteuid() == 0)


def _geteuid() -> int:
    getter = getattr(os, "geteuid", None)
    return int(getter()) if getter else 1


class EventParser(ABC):
    """Incremental parser of one turn's output."""

    @abstractmethod
    def feed(self, line: str) -> list[ParsedEvent]:
        """Parse one stdout line (no trailing newline)."""

    def finish(self, returncode: int | None) -> list[ParsedEvent]:
        """Flush state after the process exited."""
        return []


class AgentAdapter(ABC):
    """Base class of runtime adapters.

    Subclasses set the class attributes and implement
    :meth:`build_invocation` and :meth:`new_parser`.  Register with
    :func:`easy_sandbox.server.agents.register_adapter`, an entry point of
    group ``easy_sandbox.agent_adapters`` or ``EBX_AGENTS_ADAPTER_MODULES``.
    """

    name: ClassVar[str]
    aliases: ClassVar[tuple[str, ...]] = ()
    binary: ClassVar[str]
    install_steps: ClassVar[tuple[tuple[str, ...], ...]] = ()
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities()
    prompt_transport: ClassVar[str] = "stdin"  # "stdin" | "argv"
    # Server environment variables forwarded to *this* runtime's child only.
    passthrough_env: ClassVar[tuple[str, ...]] = ()
    # Conventional credential variables (reported by the health check).
    credential_env_names: ClassVar[tuple[str, ...]] = ()

    def validate(self, spec: AgentSpec) -> list[str]:
        """Return configuration problems specific to this runtime."""
        return []

    @abstractmethod
    def build_invocation(self, ctx: TurnContext) -> Invocation:
        """Return argv/env/stdin/files for one turn."""

    @abstractmethod
    def new_parser(self, ctx: TurnContext) -> EventParser:
        """Return a fresh parser for one turn."""

    def health_argv(self) -> list[str]:
        """Command used by the health check."""
        return [self.binary, "--version"]

    def classify_failure(self, returncode: int | None, stderr_tail: str) -> tuple[str, str]:
        """Map a failed exit to ``(code, message)`` (message is not yet redacted)."""
        text = stderr_tail.strip()
        code = classify_text(text)
        if not text:
            text = f"{self.binary} exited with status {returncode}"
        return code, text[-1500:]

    # -- helpers shared by adapters ------------------------------------ #

    def effective_prompt(self, ctx: TurnContext) -> str:
        """Prompt text, with instructions prepended on the first turn for preamble runtimes."""
        if self.capabilities.system_prompt == "preamble":
            return with_preamble(ctx)
        return ctx.prompt

    def prompt_stdin(self, ctx: TurnContext) -> bytes | None:
        """Prompt bytes for stdin-transport adapters."""
        if self.prompt_transport != "stdin":
            return None
        return self.effective_prompt(ctx).encode("utf-8")

    def prompt_argv_value(self, ctx: TurnContext) -> str:
        """Prompt for argv-transport adapters; never starts with ``-``."""
        prompt = self.effective_prompt(ctx)
        return f"Task: {prompt}" if prompt.startswith("-") else prompt


def with_preamble(ctx: TurnContext) -> str:
    """Prompt with the agent's instructions prepended (first turn of a session only)."""
    instructions = ctx.spec.instructions
    if instructions and ctx.first_turn and ctx.native_session_id is None:
        return f"{instructions.strip()}\n\n---\n\n{ctx.prompt}"
    return ctx.prompt


_CLASSIFIERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "authentication_error",
        re.compile(
            r"\b401\b|\b403\b|unauthori[sz]ed|invalid[ _-]?api[ _-]?key|incorrect api key|"
            r"authentication|not logged in|/login|invalid x-api-key|permission denied.*api",
            re.I,
        ),
    ),
    ("rate_limit_exceeded", re.compile(r"\b429\b|rate[ _-]?limit|quota|too many requests", re.I)),
    ("server_overloaded", re.compile(r"overloaded|\b503\b|\b529\b|service unavailable", re.I)),
    (
        "context_length_exceeded",
        re.compile(r"context[ _-]?length|prompt is too long|too many tokens|maximum context", re.I),
    ),
    (
        "connection_failed",
        re.compile(r"ECONNREFUSED|ENOTFOUND|connection (?:refused|reset)|getaddrinfo", re.I),
    ),
)


def classify_text(text: str) -> str:
    """Best-effort mapping of error text to an Agents-API error code."""
    for code, pattern in _CLASSIFIERS:
        if pattern.search(text):
            return code
    return "internal_error"


_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def toml_key(key: str) -> str:
    """Quote a TOML key segment when needed."""
    return key if _BARE_KEY.match(key) else json.dumps(key)


def toml_value(value: Any) -> str:
    """Render a Python value as a TOML literal (strings, bools, ints, lists, tables)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        inner = ", ".join(f"{toml_key(str(k))} = {toml_value(v)}" for k, v in value.items())
        return "{" + inner + "}"
    raise TypeError(f"cannot render {type(value).__name__} as TOML")
