"""Subagent detail built only from ids the CLIs actually emitted.

Codex: ``collab_tool_call`` items name ``receiver_thread_ids``; the same ids can sit in the
session's own rollout (Codex exec JSONL sometimes drops ``spawn_agent``). A child's items and
turns are read from that child's rollout file, and only for ids the session's JSONL or
rollout names. ``CODEX_HOME`` is never scanned for unrelated sessions.

Qwen Code: stream-json tags every subagent message with ``parent_tool_use_id``; the runtime
keeps those entries, and turns are groups of them split at assistant-message boundaries.
"""

from __future__ import annotations

import contextlib
import glob
import json
import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .runtime import Session

__all__ = [
    "SubagentTurn",
    "codex_home",
    "collect_records",
    "turns_for",
]

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{5,95}$")
_MAX_ROLLOUT_BYTES = 16 * 1024 * 1024
_MAX_TEXT = 64 * 1024
_ID_KEYS = ("receiver_thread_ids", "receiver_thread_id", "new_thread_id")


class SubagentTurn(dict[str, Any]):
    """``{"id", "entries", "complete"}``."""


def codex_home(environ: Mapping[str, str]) -> str:
    """Where Codex keeps its rollouts for this server's child processes."""
    configured = environ.get("CODEX_HOME")
    return configured or os.path.join(os.path.expanduser("~"), ".codex")


def _find_rollout(home: str, thread_id: str) -> str | None:
    if not _ID_RE.match(thread_id):
        return None
    pattern = os.path.join(
        glob.escape(home), "sessions", "**", f"rollout-*-{glob.escape(thread_id)}.jsonl"
    )
    for path in sorted(glob.glob(pattern, recursive=True)):
        if os.path.isfile(path) and not os.path.islink(path):
            return path
    return None


def _read_lines(path: str) -> list[dict[str, Any]]:
    try:
        if os.path.getsize(path) > _MAX_ROLLOUT_BYTES:
            return []
        with open(path, encoding="utf-8", errors="replace") as fh:
            rows = []
            for raw in fh:
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
            return rows
    except OSError:
        return []


def _named_ids(node: Any, out: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _ID_KEYS:
                values = value if isinstance(value, list) else [value]
                out.extend(v for v in values if isinstance(v, str) and _ID_RE.match(v))
            else:
                _named_ids(value, out)
    elif isinstance(node, list):
        for value in node:
            _named_ids(value, out)


def rollout_child_ids(home: str, parent_thread_id: str) -> list[str]:
    """Child thread ids named inside the parent thread's own rollout."""
    path = _find_rollout(home, parent_thread_id)
    if path is None:
        return []
    found: list[str] = []
    for row in _read_lines(path):
        _named_ids(row, found)
    return [i for i in dict.fromkeys(found) if i != parent_thread_id]


def collect_records(
    session: Session, runtime_name: str, environ: Mapping[str, str]
) -> list[dict[str, Any]]:
    """Every subagent of *session*: ids from the CLI stream and, for Codex, its rollout."""
    with session.cond:
        records = {sid: dict(rec) for sid, rec in session.subagents.items()}
    if runtime_name == "codex" and session.native_session_id:
        for thread_id in rollout_child_ids(codex_home(environ), session.native_session_id):
            records.setdefault(
                thread_id,
                {
                    "id": thread_id,
                    "name": None,
                    "instructions": None,
                    "opened_at": session.created_at,
                    "closed_at": None,
                    "source": "codex",
                    "entries": [],
                },
            )
    return sorted(records.values(), key=lambda r: (r["opened_at"], r["id"]))


# ---------------------------------------------------------------------- #
# Turns and items
# ---------------------------------------------------------------------- #


def _cap(text: str) -> str:
    return text[:_MAX_TEXT]


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _rollout_turns(thread_id: str, rows: list[dict[str, Any]]) -> list[SubagentTurn]:
    turns: list[SubagentTurn] = []

    def start(native: str | None) -> SubagentTurn:
        turn = SubagentTurn(
            id=native or f"turn_{len(turns) + 1}_{thread_id}", entries=[], complete=True
        )
        turns.append(turn)
        return turn

    current: SubagentTurn | None = None
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        kind = row.get("type")
        ptype = payload.get("type")
        if kind == "turn_context" or (
            kind == "event_msg" and ptype in ("task_started", "turn_started")
        ):
            native = payload.get("turn_id")
            if current is None or current["entries"]:
                current = start(native if isinstance(native, str) else None)
            elif isinstance(native, str):
                current["id"] = native
            continue
        if kind != "response_item":
            continue
        if current is None:
            current = start(None)
        entries = current["entries"]
        if ptype == "message" and payload.get("role") in ("user", "assistant"):
            text = _content_text(payload.get("content"))
            if text:
                entries.append({"kind": "message", "role": payload["role"], "text": _cap(text)})
        elif ptype == "reasoning":
            text = "".join(
                s.get("text", "") for s in payload.get("summary") or [] if isinstance(s, dict)
            )
            if text:
                entries.append({"kind": "reasoning", "role": "assistant", "text": _cap(text)})
        elif ptype == "function_call":
            args: Any = payload.get("arguments")
            if isinstance(args, str):
                with contextlib.suppress(ValueError):
                    args = json.loads(args)
            entries.append(
                {
                    "kind": "tool_call",
                    "role": "assistant",
                    "call_id": str(payload.get("call_id") or ""),
                    "name": str(payload.get("name") or "tool"),
                    "arguments": args,
                    "output": None,
                    "ok": None,
                }
            )
        elif ptype == "function_call_output":
            call_id = str(payload.get("call_id") or "")
            output = payload.get("output")
            text = output if isinstance(output, str) else json.dumps(output, default=str)
            for existing in reversed(entries):
                if existing.get("kind") == "tool_call" and existing.get("call_id") == call_id:
                    existing["output"] = _cap(text)
                    existing["ok"] = True
                    break
    return turns


def _stream_turns(sid: str, entries: list[dict[str, Any]]) -> list[SubagentTurn]:
    """Group a tagged parent stream: a turn ends at each assistant message."""
    turns: list[SubagentTurn] = []
    current: SubagentTurn | None = None
    for entry in entries:
        if current is None:
            current = SubagentTurn(id=f"turn_{len(turns) + 1}_{sid}", entries=[], complete=False)
            turns.append(current)
        current["entries"].append(entry)
        if entry.get("kind") == "message" and entry.get("role") == "assistant":
            current["complete"] = True
            current = None
    return turns


def turns_for(record: dict[str, Any], environ: Mapping[str, str]) -> tuple[list[SubagentTurn], str]:
    """Turns of one subagent and the difference code that describes how they were grouped."""
    if record.get("source") == "codex":
        path = _find_rollout(codex_home(environ), record["id"])
        rows = _read_lines(path) if path else []
        return _rollout_turns(record["id"], rows), "turns_from_rollout"
    return _stream_turns(record["id"], list(record.get("entries") or [])), (
        "turns_grouped_from_parent_stream"
    )
