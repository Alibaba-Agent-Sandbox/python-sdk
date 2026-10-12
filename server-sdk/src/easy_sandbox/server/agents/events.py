"""Adapter-neutral event vocabulary produced by runtime adapters."""

from __future__ import annotations

import dataclasses
from typing import Any

__all__ = [
    "ParsedEvent",
    "session_event",
    "text_delta",
    "message",
    "reasoning_delta",
    "reasoning",
    "tool_start",
    "tool_output",
    "tool_end",
    "usage",
    "error",
    "result",
    "log",
    "subagent",
]


@dataclasses.dataclass
class ParsedEvent:
    """One normalised event parsed from an agent CLI's output.

    ``kind`` is one of ``session``, ``text_delta``, ``message``,
    ``reasoning_delta``, ``reasoning``, ``tool_start``, ``tool_output``,
    ``tool_end``, ``usage``, ``error``, ``result``, ``log``, ``subagent``.
    """

    kind: str
    item_id: str | None = None
    text: str | None = None
    data: dict[str, Any] = dataclasses.field(default_factory=dict)


def session_event(native_id: str) -> ParsedEvent:
    """The CLI's own session/thread id (resume handle)."""
    return ParsedEvent("session", text=native_id)


def text_delta(item_id: str, text: str) -> ParsedEvent:
    """Incremental assistant text for message *item_id*."""
    return ParsedEvent("text_delta", item_id, text)


def message(item_id: str, text: str) -> ParsedEvent:
    """Complete assistant message (authoritative text)."""
    return ParsedEvent("message", item_id, text)


def reasoning_delta(item_id: str, text: str) -> ParsedEvent:
    """Incremental reasoning/thinking summary text."""
    return ParsedEvent("reasoning_delta", item_id, text)


def reasoning(item_id: str, text: str) -> ParsedEvent:
    """Complete reasoning/thinking summary."""
    return ParsedEvent("reasoning", item_id, text)


def tool_start(
    item_id: str,
    kind: str,
    name: str,
    *,
    arguments: Any = None,
    command: str | None = None,
    server: str | None = None,
) -> ParsedEvent:
    """A tool call began.  *kind*: ``command``, ``mcp``, ``file_change``, ``web_search``, ``other``."""
    return ParsedEvent(
        "tool_start",
        item_id,
        data={
            "kind": kind,
            "name": name,
            "arguments": arguments,
            "command": command,
            "server": server,
        },
    )


def tool_output(item_id: str, delta: str) -> ParsedEvent:
    """Streamed output of a running tool call."""
    return ParsedEvent("tool_output", item_id, delta)


def tool_end(
    item_id: str,
    *,
    ok: bool = True,
    output: str | None = None,
    exit_code: int | None = None,
    error_text: str | None = None,
) -> ParsedEvent:
    """A tool call finished."""
    return ParsedEvent(
        "tool_end",
        item_id,
        output,
        {"ok": ok, "exit_code": exit_code, "error": error_text},
    )


def usage(
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    reasoning_tokens: int = 0,
    cost_usd: float | None = None,
) -> ParsedEvent:
    """Token usage reported by the CLI."""
    return ParsedEvent(
        "usage",
        data={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "reasoning_tokens": reasoning_tokens,
            "cost_usd": cost_usd,
        },
    )


def error(code: str, text: str, *, fatal: bool = False) -> ParsedEvent:
    """An error reported by the CLI; ``fatal`` fails the turn."""
    return ParsedEvent("error", text=text, data={"code": code, "fatal": fatal})


def result(ok: bool, text: str | None = None, stop_reason: str | None = None) -> ParsedEvent:
    """Terminal result record of the CLI."""
    return ParsedEvent("result", text=text, data={"ok": ok, "stop_reason": stop_reason})


def log(text: str) -> ParsedEvent:
    """A non-structured output line (kept for debugging only)."""
    return ParsedEvent("log", text=text)


def subagent(op: str, ids: list[str], **data: Any) -> ParsedEvent:
    """A subagent id the CLI itself emitted.

    *op* is ``open`` (the id first appears), ``close`` (the CLI closed it) or
    ``event`` (one item of the subagent's own stream, ``data['entry']``).
    """
    return ParsedEvent("subagent", data={"op": op, "ids": list(ids), **data})
