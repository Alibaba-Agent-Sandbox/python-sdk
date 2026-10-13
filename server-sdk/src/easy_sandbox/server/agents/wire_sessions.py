"""Mapping of runtime state/events onto the OpenAI Agents API (beta) wire.

Subset served: sessions, turns, items and SSE events of a ``self_hosted``-shaped
environment.  See ``docs/en/design/agents-api.md`` (section 6.5) for the exact
compatibility boundary.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .errors import agents_wire_code

if TYPE_CHECKING:
    from .config import AgentSpec
    from .runtime import Item, RuntimeEvent, Session, Turn

__all__ = [
    "SessionsEventMapper",
    "item_object",
    "session_object",
    "sse_frame",
    "turn_object",
    "usage_object",
]


def sse_frame(event: dict[str, Any], seq: int | None = None) -> str:
    """Encode one SSE frame (``id`` is the runtime sequence number for resume)."""
    head = f"id: {seq}\n" if seq is not None else ""
    payload = json.dumps(event, separators=(",", ":"), default=str)
    return f"{head}event: {event['type']}\ndata: {payload}\n\n"


def usage_object(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    """Agents-API ``TokenUsage`` from the runtime's usage dict."""
    if not usage:
        return None
    inp = int(usage.get("input_tokens", 0))
    out = int(usage.get("output_tokens", 0))
    return {
        "input_tokens": inp,
        "input_tokens_details": {"cached_tokens": int(usage.get("cached_tokens", 0))},
        "output_tokens": out,
        "output_tokens_details": {"reasoning_tokens": int(usage.get("reasoning_tokens", 0))},
        "total_tokens": int(usage.get("total_tokens", inp + out)),
    }


def _ts(value: float | None) -> int | None:
    return None if value is None else int(value)


def _status(status: str) -> str:
    return (
        status
        if status in ("in_progress", "completed", "incomplete")
        else "completed"
        if status == "failed"
        else "in_progress"
    )


def item_object(item: Item | dict[str, Any]) -> dict[str, Any]:
    """Agents-API item for one runtime item.

    Item types are ``message``, ``reasoning``, ``command_execution``, and ``mcp_call``.
    """
    d = item if isinstance(item, dict) else item.to_dict()
    data = d["data"]
    base = {"id": d["id"], "turn_id": d["turn_id"]}
    if d["type"] == "message":
        text = str(data.get("text", ""))
        out: dict[str, Any] = {
            **base,
            "type": "message",
            "role": "assistant",
            "status": d["status"]
            if d["status"] in ("in_progress", "completed", "incomplete")
            else "completed",
            "content": [{"type": "output_text", "text": text}],
        }
        if data.get("phase"):
            out["phase"] = data["phase"]
        return out
    if d["type"] == "reasoning":
        text = str(data.get("text", ""))
        return {
            **base,
            "type": "reasoning",
            "status": d["status"]
            if d["status"] in ("in_progress", "completed", "incomplete")
            else "completed",
            "summary": [{"type": "summary_text", "text": text}] if text else [],
        }
    if d["type"] == "command_execution":
        return {
            **base,
            "type": "command_execution",
            "status": d["status"],
            "command": data.get("command") or "",
            "cwd": data.get("cwd"),
            "output": data.get("output"),
            "exit_code": data.get("exit_code"),
            "duration_ms": data.get("duration_ms"),
        }
    return {
        **base,
        "type": "mcp_call",
        "status": d["status"],
        "server_label": data.get("server_label") or "agent",
        "name": data.get("name") or "tool",
        "arguments": data.get("arguments"),
        "output": data.get("output"),
        "error": data.get("error"),
    }


def turn_object(turn: Turn | dict[str, Any], agent_id: str | None = None) -> dict[str, Any]:
    """Agents-API ``agent.session.turn`` object."""
    d = turn if isinstance(turn, dict) else turn.to_dict()
    error = d.get("error")
    return {
        "id": d["id"],
        "object": "agent.session.turn",
        "agent_id": agent_id or d.get("agent") or "",
        "session_id": d["session_id"],
        "status": d["status"],
        "created_at": _ts(d.get("created_at")),
        "started_at": _ts(d.get("started_at")),
        "completed_at": _ts(d.get("completed_at")),
        "error": {"code": agents_wire_code(error["code"]), "message": error["message"]}
        if error
        else None,
        "subagent_id": None,
        "usage": usage_object(d.get("usage")),
    }


def session_object(
    session: Session, spec: AgentSpec | None, *, status: str | None = None
) -> dict[str, Any]:
    """Agents-API ``agent.session`` object."""
    status = status or session.status
    usage_total: dict[str, int] = {}
    last_error: str | None = None
    for turn in list(session.turns):
        if turn.usage:
            for key in ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens"):
                usage_total[key] = usage_total.get(key, 0) + int(turn.usage.get(key, 0))
        last_error = turn.error["message"] if turn.error else None
    workspace = spec.workspace.path if spec else "/workspace"
    return {
        "id": session.id,
        "object": "agent.session",
        "agent": {
            "id": session.agent_name,
            "name": session.agent_name,
            "model": (spec.model if spec and spec.model else None) or session.agent_name,
            "instructions": spec.instructions if spec else None,
            "multi_agent": {"enabled": False},
            "reasoning": {"effort": (spec.reasoning_effort if spec else None), "summary": None},
            "service_tier": "default",
            "text": {"format": {"type": "text"}, "verbosity": "medium"},
            "tools": [],
        },
        "created_at": int(session.created_at),
        "environment": {
            "type": "self_hosted",
            "id": "env_easy_sandbox",
            "capability_directories": [],
            "remote_url": "",
            "workspace_directory": workspace,
        },
        "error": last_error if status == "failed" else None,
        "last_active_at": int(session.last_active_at),
        "metadata": dict(session.metadata),
        "required_actions": [],
        "status": status,
        "usage": usage_object(
            {
                **usage_total,
                "total_tokens": usage_total.get("input_tokens", 0)
                + usage_total.get("output_tokens", 0),
            }
        )
        if usage_total
        else None,
        "vault_ids": [],
    }


class SessionsEventMapper:
    """Convert :class:`RuntimeEvent` objects into Agents-API events."""

    def __init__(self, session: Session, spec: AgentSpec | None) -> None:
        self._session = session
        self._spec = spec

    def _id(self, ev: RuntimeEvent, n: int = 0) -> str:
        return f"evt_{ev.seq:010d}" + (f"_{n}" if n else "")

    def map(self, ev: RuntimeEvent) -> list[dict[str, Any]]:
        """Zero or more wire events for *ev*."""
        sid = ev.session_id
        tid = ev.turn_id
        out: list[dict[str, Any]] = []

        def add(type_: str, **fields: Any) -> None:
            out.append({"type": type_, "event_id": self._id(ev, len(out)), **fields})

        t = ev.type
        if t == "session.in_progress":
            add(
                "agent.session.in_progress",
                session=session_object(self._session, self._spec, status="in_progress"),
            )
        elif t == "session.idle":
            add(
                "agent.session.idle",
                session=session_object(self._session, self._spec, status="idle"),
            )
        elif t == "turn.queued":
            add(
                "agent.session.turn.created",
                session_id=sid,
                turn_id=tid,
                turn=turn_object(ev.data["turn"]),
            )
        elif t == "turn.started":
            add(
                "agent.session.turn.in_progress",
                session_id=sid,
                turn_id=tid,
                turn=turn_object(ev.data["turn"]),
            )
        elif t in ("turn.completed", "turn.failed", "turn.cancelled"):
            turn = turn_object(ev.data["turn"])
            fields: dict[str, Any] = {"session_id": sid, "turn_id": tid, "turn": turn}
            if turn["usage"] is not None:
                fields["usage"] = turn["usage"]
            add(f"agent.session.{t}", **fields)
        elif t == "item.added":
            item = ev.data["item"]
            idx = item["output_index"]
            add(
                "agent.session.turn.item.added",
                session_id=sid,
                turn_id=tid,
                output_index=idx,
                item=item_object(item),
            )
            if item["type"] == "message":
                add(
                    "agent.session.turn.content_part.added",
                    session_id=sid,
                    turn_id=tid,
                    item_id=item["id"],
                    output_index=idx,
                    content_index=0,
                    part={"type": "output_text", "text": ""},
                )
            elif item["type"] == "reasoning":
                add(
                    "agent.session.turn.reasoning_summary_part.added",
                    session_id=sid,
                    turn_id=tid,
                    item_id=item["id"],
                    output_index=idx,
                    summary_index=0,
                    part={"type": "summary_text", "text": ""},
                )
        elif t == "item.delta":
            kind = ev.data["kind"]
            base = {
                "session_id": sid,
                "turn_id": tid,
                "item_id": ev.data["item_id"],
                "output_index": ev.data["output_index"],
                "delta": ev.data["delta"],
            }
            if kind == "text":
                add("agent.session.turn.output_text.delta", content_index=0, **base)
            elif kind == "reasoning":
                add("agent.session.turn.reasoning_summary_text.delta", summary_index=0, **base)
            else:
                add("agent.output.command_execution_output.delta", **base)
        elif t == "item.done":
            item = ev.data["item"]
            idx = item["output_index"]
            data = item["data"]
            if item["type"] == "message":
                text = str(data.get("text", ""))
                add(
                    "agent.session.turn.output_text.done",
                    session_id=sid,
                    turn_id=tid,
                    item_id=item["id"],
                    output_index=idx,
                    content_index=0,
                    text=text,
                )
                add(
                    "agent.session.turn.content_part.done",
                    session_id=sid,
                    turn_id=tid,
                    item_id=item["id"],
                    output_index=idx,
                    content_index=0,
                    part={"type": "output_text", "text": text},
                )
            elif item["type"] == "reasoning":
                text = str(data.get("text", ""))
                add(
                    "agent.session.turn.reasoning_summary_text.done",
                    session_id=sid,
                    turn_id=tid,
                    item_id=item["id"],
                    output_index=idx,
                    summary_index=0,
                    text=text,
                )
                add(
                    "agent.session.turn.reasoning_summary_part.done",
                    session_id=sid,
                    turn_id=tid,
                    item_id=item["id"],
                    output_index=idx,
                    summary_index=0,
                    part={"type": "summary_text", "text": text},
                )
            add(
                "agent.session.turn.item.done",
                session_id=sid,
                turn_id=tid,
                output_index=idx,
                item=item_object(item),
            )
        return out
