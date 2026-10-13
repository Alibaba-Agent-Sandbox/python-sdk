"""``/v1/responses`` as a labeled local one-shot CLI turn (R-01..R-05, R-07, R-08 engine).

Each response is one turn of a local codex or qwen-code process. ``model`` selects a stored
definition (its id) or passes through as the CLI's ``-m``. Only ``mcp`` tools are accepted.
Output items report what the CLI actually emitted: assistant messages, reasoning, commands,
real MCP calls, and every other native tool as a local ``tool_call`` item. Nothing is ever
shaped like an OpenAI-hosted tool that did not run.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import threading
import uuid
from typing import TYPE_CHECKING, Any, TypeVar

from ..types import ServerRequest, ServerResponse, SSEResponse
from .api_common import (
    body_of,
    err,
    first,
    from_agent_exc,
    get_agent_runtime,
    header,
    label,
    metadata_strict,
    page,
    principal_of,
    select_or_response,
    url_check,
)
from .api_definitions import McpTool, spec_from_fields, tools_of
from .api_sessions import submit_turn
from .config import McpServerSpec
from .errors import AgentNotFoundError, AgentRuntimeError, LocalApiError
from .local_state import Record, SessionMeta, get_state

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .runtime import Item, Session, Turn

__all__ = [
    "ResponsesSocket",
    "handle_response_cancel",
    "handle_response_delete",
    "handle_response_get",
    "handle_response_input_items",
    "handle_responses_compact",
    "handle_responses_create",
]

_SAMPLING_IGNORED = (
    "temperature",
    "top_p",
    "max_output_tokens",
    "top_logprobs",
    "truncation",
    "parallel_tool_calls",
    "user",
    "safety_identifier",
    "prompt_cache_key",
    "prompt_cache_retention",
    "stream_options",
)
_ACCEPTED = frozenset(
    {
        "model",
        "input",
        "instructions",
        "tools",
        "metadata",
        "previous_response_id",
        "store",
        "background",
        "stream",
        "tool_choice",
        "service_tier",
        "reasoning",
        "text",
        "include",
        "conversation",
        "prompt",
        "adapter",
        "runtime",
        *_SAMPLING_IGNORED,
    }
)
_LABEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_IGNORED_HEADER = "X-Agent-Sandbox-Ignored-Params"
_WAIT_SLACK_S = 30.0


def _workspace() -> str:
    """Working directory of response turns (``ABX_AGENTS_RESPONSES_WORKSPACE``)."""
    return os.environ.get("ABX_AGENTS_RESPONSES_WORKSPACE", "").strip() or "/workspace"


def _missing(response_id: str) -> ServerResponse:
    return err(
        404,
        f"response {response_id!r} not found",
        code="resource_not_found",
        param="response_id",
    )


# ---------------------------------------------------------------------- #
# Request parsing
# ---------------------------------------------------------------------- #


def _parse_tools(raw: Any) -> list[McpTool]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise LocalApiError("tools: expected a list", param="tools")
    tools: list[McpTool] = []
    seen: set[str] = set()
    for i, tool in enumerate(raw):
        where = f"tools[{i}]"
        if not isinstance(tool, dict) or tool.get("type") != "mcp":
            raise LocalApiError(
                f"{where}.type: only mcp tools are supported by the local agent runtime",
                param=f"{where}.type",
            )
        for key in tool:
            if key not in (
                "type",
                "server_label",
                "server_url",
                "headers",
                "authorization",
                "require_approval",
                "allowed_tools",
                "server_description",
            ):
                raise LocalApiError(f"{where}.{key}: unsupported parameter", param=f"{where}.{key}")
        label_ = tool.get("server_label")
        if not isinstance(label_, str) or not _LABEL_RE.match(label_) or label_ in seen:
            raise LocalApiError(
                f"{where}.server_label: a unique label of 1 to 40 [A-Za-z0-9_-] characters",
                param=f"{where}.server_label",
            )
        seen.add(label_)
        url_check(
            tool.get("server_url"), f"{where}.server_url", https_only=False, allow_private=True
        )
        if tool.get("allowed_tools"):
            raise LocalApiError(
                f"{where}.allowed_tools: neither CLI can restrict the MCP tool list",
                param=f"{where}.allowed_tools",
            )
        if tool.get("require_approval") not in (None, "never"):
            raise LocalApiError(
                f"{where}.require_approval: the CLI runs unattended; only never applies",
                param=f"{where}.require_approval",
            )
        headers: dict[str, str] = {}
        raw_headers = tool.get("headers")
        if raw_headers is not None:
            if not isinstance(raw_headers, dict):
                raise LocalApiError(
                    f"{where}.headers: expected a mapping", param=f"{where}.headers"
                )
            for name, value in raw_headers.items():
                if (
                    not isinstance(name, str)
                    or not name
                    or not isinstance(value, str)
                    or not value
                    or any(ch in value for ch in "\r\n\x00")
                ):
                    raise LocalApiError(
                        f"{where}.headers: invalid header", param=f"{where}.headers"
                    )
                headers[name] = value
        authorization = tool.get("authorization")
        if authorization is not None:
            if (
                not isinstance(authorization, str)
                or not authorization
                or any(ch in authorization for ch in "\r\n\x00")
            ):
                raise LocalApiError(
                    f"{where}.authorization: expected a token string",
                    param=f"{where}.authorization",
                )
            headers["Authorization"] = f"Bearer {authorization}"
        tools.append(McpTool(label_, str(tool["server_url"]), headers, None))
    return tools


def _normalize_input(raw: Any) -> tuple[str, str | None, list[dict[str, Any]]]:
    """``(prompt, instructions, stored input items)`` of a Responses ``input`` value."""
    if raw is None or raw == "" or raw == []:
        raise LocalApiError("input: required", param="input")
    items = [{"type": "message", "role": "user", "content": raw}] if isinstance(raw, str) else raw
    if not isinstance(items, list):
        raise LocalApiError("input: expected a string or a list of messages", param="input")
    prompt: list[str] = []
    system: list[str] = []
    stored: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        where = f"input[{i}]"
        if not isinstance(item, dict) or item.get("type", "message") != "message":
            raise LocalApiError(
                f"{where}.type: only message items are supported", param=f"{where}.type"
            )
        role = item.get("role")
        if role not in ("user", "system", "developer"):
            raise LocalApiError(
                f"{where}.role: user, system or developer (assistant history is not replayable)",
                param=f"{where}.role",
            )
        content = item.get("content")
        parts = [{"type": "input_text", "text": content}] if isinstance(content, str) else content
        if not isinstance(parts, list):
            raise LocalApiError(f"{where}.content: required", param=f"{where}.content")
        texts: list[str] = []
        for j, part in enumerate(parts):
            if not isinstance(part, dict) or part.get("type") != "input_text":
                raise LocalApiError(
                    f"{where}.content[{j}].type: only input_text is supported",
                    param=f"{where}.content[{j}].type",
                )
            if not isinstance(part.get("text"), str):
                raise LocalApiError(
                    f"{where}.content[{j}].text: expected a string",
                    param=f"{where}.content[{j}].text",
                )
            texts.append(part["text"])
        text = "\n".join(texts)
        (prompt if role == "user" else system).append(text)
        stored.append(
            {
                "id": "msg_" + uuid.uuid4().hex[:24],
                "type": "message",
                "role": role,
                "content": [{"type": "input_text", "text": t} for t in texts],
            }
        )
    joined = "\n\n".join(p for p in prompt if p)
    if not joined:
        raise LocalApiError("input: needs at least one non-empty user message", param="input")
    return joined, ("\n\n".join(s for s in system if s) or None), stored


def _validate(body: dict[str, Any]) -> list[str]:
    """Refuse what cannot be honoured; return the ignored sampling parameters present."""
    for key in body:
        if key not in _ACCEPTED:
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    if body.get("conversation") is not None:
        raise LocalApiError(
            "conversation: stored conversations are not available", param="conversation"
        )
    if body.get("prompt") is not None:
        raise LocalApiError("prompt: stored prompt templates are not available", param="prompt")
    if body.get("include"):
        raise LocalApiError(
            "include: the local runtime cannot fill any includable output", param="include"
        )
    if body.get("service_tier") not in (None, "auto", "default"):
        raise LocalApiError("service_tier: only auto and default", param="service_tier")
    if body.get("tool_choice") not in (None, "auto"):
        raise LocalApiError("tool_choice: only auto", param="tool_choice")
    text = body.get("text")
    if text is not None:
        if not isinstance(text, dict):
            raise LocalApiError("text: expected an object", param="text")
        fmt = text.get("format")
        if fmt is not None and not (isinstance(fmt, dict) and fmt.get("type") == "text"):
            raise LocalApiError("text.format: only text is supported", param="text.format")
    for flag in ("store", "background", "stream"):
        if body.get(flag) is not None and not isinstance(body[flag], bool):
            raise LocalApiError(f"{flag}: expected a boolean", param=flag)
    if body.get("background") and body.get("store") is False:
        raise LocalApiError("background: requires store to be true", param="background")
    ignored = [k for k in _SAMPLING_IGNORED if body.get(k) is not None]
    if isinstance(text, dict) and text.get("verbosity") is not None:
        ignored.append("text.verbosity")
    return ignored


# ---------------------------------------------------------------------- #
# Wire objects
# ---------------------------------------------------------------------- #


def _item_status(status: str) -> str:
    return status if status in ("in_progress", "completed", "incomplete", "failed") else "completed"


def _output_item(item: Item) -> dict[str, Any]:
    d = item.to_dict()
    data = d["data"]
    local_label = label("response_is_cli_turn")
    suffix = d["id"].removeprefix("item_")
    if d["type"] == "message":
        status = (
            d["status"]
            if d["status"] in ("in_progress", "completed", "incomplete")
            else "completed"
        )
        return {
            "id": "msg_" + suffix,
            "type": "message",
            "status": status,
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": str(data.get("text", "")), "annotations": []}
            ],
        }
    if d["type"] == "reasoning":
        text = str(data.get("text", ""))
        return {
            "id": "rs_" + suffix,
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": text}] if text else [],
            "status": _item_status(d["status"]),
        }
    if d["type"] == "command_execution":
        return {
            "id": "cmd_" + suffix,
            "type": "command_execution",
            "status": _item_status(d["status"]),
            "command": data.get("command") or "",
            "cwd": data.get("cwd"),
            "output": data.get("output"),
            "exit_code": data.get("exit_code"),
            "duration_ms": data.get("duration_ms"),
            "x_agent_sandbox": local_label,
        }
    if data.get("kind") == "mcp":
        return {
            "id": "mcp_" + suffix,
            "type": "mcp_call",
            "status": _item_status(d["status"]),
            "server_label": data.get("server_label") or "",
            "name": data.get("name") or "tool",
            "arguments": json.dumps(data.get("arguments"), default=str),
            "output": data.get("output"),
            "error": data.get("error"),
            "x_agent_sandbox": local_label,
        }
    return {
        "id": "tc_" + suffix,
        "type": "tool_call",
        "status": _item_status(d["status"]),
        "tool_name": data.get("name") or "tool",
        "arguments": data.get("arguments"),
        "output": data.get("output"),
        "error": data.get("error"),
        "x_agent_sandbox": local_label,
    }


def _usage(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    if not usage:
        return None
    inp = int(usage.get("input_tokens", 0))
    out = int(usage.get("output_tokens", 0))
    return {
        "input_tokens": inp,
        "input_tokens_details": {
            "cached_tokens": int(usage.get("cached_tokens", 0)),
            "cache_write_tokens": 0,
        },
        "output_tokens": out,
        "output_tokens_details": {"reasoning_tokens": int(usage.get("reasoning_tokens", 0))},
        "total_tokens": int(usage.get("total_tokens", inp + out)),
    }


def _find_turn(session: Session, turn_id: str) -> Turn | None:
    for turn in session.turns:
        if turn.id == turn_id:
            return turn
    return None


def _status(turn: Turn) -> str:
    return (
        turn.status
        if turn.status in ("queued", "in_progress", "completed", "failed", "cancelled")
        else "failed"
    )


def response_object(record: Record, turn: Turn) -> dict[str, Any]:
    """The ``response`` object for a stored response and its turn."""
    d = record.data
    status = _status(turn)
    error = None
    if turn.error:
        code = (
            "rate_limit_exceeded" if turn.error["code"] == "rate_limit_exceeded" else "server_error"
        )
        error = {"code": code, "message": turn.error["message"]}
    differences = ["response_is_cli_turn"]
    if d["model_resolved"]:
        differences.append("model_passthrough")
    extra = {"model_resolved": d["model_resolved"]}
    if d.get("steered"):
        differences.append("queued_steer")
    return {
        "id": record.id,
        "object": "response",
        "created_at": record.created_at,
        "completed_at": int(turn.completed_at)
        if status == "completed" and turn.completed_at
        else None,
        "status": status,
        "background": d["background"],
        "error": error,
        "incomplete_details": None,
        "instructions": d.get("instructions"),
        "metadata": dict(d["metadata"]),
        "model": d["model"],
        "output": [_output_item(i) for i in turn.items],
        "parallel_tool_calls": False,
        "previous_response_id": d.get("previous_response_id"),
        "service_tier": None,
        "store": d["store"],
        "temperature": None,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "tools": [dict(t) for t in d["tools"]],
        "top_p": None,
        "usage": _usage(turn.usage),
        "x_agent_sandbox": label(*differences, **extra),
    }


def _tool_echo(tool: McpTool) -> dict[str, Any]:
    return {"type": "mcp", "server_label": tool.label, "server_url": tool.url}


# ---------------------------------------------------------------------- #
# Streaming (replay of the stored turn)
# ---------------------------------------------------------------------- #


def _sse(event: dict[str, Any]) -> str:
    return (
        f"event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'), default=str)}\n\n"
    )


def _events_for(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Official-shaped stream events that replay a finished (or running) response."""
    events: list[dict[str, Any]] = []
    tag = response["x_agent_sandbox"]
    response = {
        **response,
        "x_agent_sandbox": {
            **tag,
            "differences": [*tag["differences"], "stream_replayed_after_turn"],
        },
    }

    def add(type_: str, **fields: Any) -> None:
        events.append({"type": type_, "sequence_number": len(events), **fields})

    shell = {**response, "status": "in_progress", "output": [], "usage": None, "completed_at": None}
    add("response.created", response=shell)
    add("response.in_progress", response=shell)
    for index, item in enumerate(response["output"]):
        if item["type"] == "message":
            text = item["content"][0]["text"]
            empty = {**item, "status": "in_progress", "content": []}
            add("response.output_item.added", output_index=index, item=empty)
            part = {"type": "output_text", "text": "", "annotations": []}
            add(
                "response.content_part.added",
                item_id=item["id"],
                output_index=index,
                content_index=0,
                part=part,
            )
            if text:
                add(
                    "response.output_text.delta",
                    item_id=item["id"],
                    output_index=index,
                    content_index=0,
                    delta=text,
                    logprobs=[],
                )
            add(
                "response.output_text.done",
                item_id=item["id"],
                output_index=index,
                content_index=0,
                text=text,
                logprobs=[],
            )
            add(
                "response.content_part.done",
                item_id=item["id"],
                output_index=index,
                content_index=0,
                part=item["content"][0],
            )
        else:
            add(
                "response.output_item.added",
                output_index=index,
                item={**item, "status": "in_progress"},
            )
        add("response.output_item.done", output_index=index, item=item)
    terminal = {
        "completed": "response.completed",
        "failed": "response.failed",
        "cancelled": "response.incomplete",
    }.get(response["status"])
    if terminal:
        add(terminal, response=response)
    return events


def _stream(
    record: Record, turn: Turn, *, after: int | None = None, live: bool = True
) -> Iterator[str]:
    def frames() -> Iterator[str]:
        if live and not turn.done.is_set():
            current = response_object(record, turn)
            tag = current["x_agent_sandbox"]
            shell = {
                **current,
                "status": "in_progress",
                "output": [],
                "usage": None,
                "x_agent_sandbox": {
                    **tag,
                    "differences": [*tag["differences"], "stream_replayed_after_turn"],
                },
            }
            for n, kind in enumerate(("response.created", "response.in_progress")):
                if after is None or n > after:
                    yield _sse({"type": kind, "sequence_number": n, "response": shell})
            while not turn.done.wait(15.0):
                yield ": keep-alive\n\n"
            start = 2
        else:
            start = 0
        for event in _events_for(response_object(record, turn)):
            if event["sequence_number"] < start:
                continue
            if after is not None and event["sequence_number"] <= after:
                continue
            yield _sse(event)

    return frames()


def _stream_response(record: Record, turn: Turn, *, after: int | None, live: bool) -> SSEResponse:
    return SSEResponse(
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
        event_iterator=_stream(record, turn, after=after, live=live),
    )


# ---------------------------------------------------------------------- #
# Lifecycle helpers
# ---------------------------------------------------------------------- #


def _release(record: Record, *, hide_turn: bool = True) -> None:
    """Remove a response and, when it was the last one, its backing session."""
    state = get_state()
    state.responses.delete(record.owner, record.id)
    sid = record.data["session_id"]
    runtime = get_agent_runtime()
    others = [r for r in state.responses.list(record.owner) if r.data["session_id"] == sid]
    try:
        session = runtime.get_session(sid)
    except AgentNotFoundError:
        return
    turn = _find_turn(session, record.data["turn_id"])
    if hide_turn and turn is not None:
        turn.keep = False
    if others:
        if state.response_latest.get(sid) == record.id:
            state.response_latest[sid] = others[-1].id
        return
    meta = state.session_meta.pop(sid, None)
    state.response_latest.pop(sid, None)
    with contextlib.suppress(AgentNotFoundError):
        runtime.delete_session(sid)
    if meta is not None:
        runtime.store.delete(meta.spec_name)


def _release_when_done(record: Record, turn: Turn) -> None:
    def run() -> None:
        turn.done.wait()
        _release(record)

    threading.Thread(target=run, name="agents-response-release", daemon=True).start()


def _wait(session: Session, turn: Turn) -> None:
    spec = get_agent_runtime().store.get(session.agent_name)
    limit = (spec.limits.turn_timeout_s if spec else 1800.0) + _WAIT_SLACK_S
    get_agent_runtime().wait(turn, limit)


# ---------------------------------------------------------------------- #
# R-01 create
# ---------------------------------------------------------------------- #


def _create_response(
    request: ServerRequest, body: dict[str, Any], *, steered: bool = False
) -> tuple[Record, Turn, Session, list[str]] | ServerResponse:
    owner = principal_of(request)
    state = get_state()
    runtime = get_agent_runtime()
    ignored = _validate(body)
    model = body.get("model")
    if not isinstance(model, str) or not model.strip():
        raise LocalApiError("model: required", param="model")
    model = model.strip()
    metadata = metadata_strict(body.get("metadata"))
    req_tools = _parse_tools(body.get("tools"))
    prompt, system, input_items = _normalize_input(body.get("input"))
    instructions = body.get("instructions")
    if instructions is not None and not isinstance(instructions, str):
        raise LocalApiError("instructions: expected a string", param="instructions")
    if system:
        instructions = f"{instructions}\n\n{system}" if instructions else system
    store = body.get("store") is not False

    prev_id = body.get("previous_response_id")
    previous: Record | None = None
    if prev_id is not None:
        previous = state.responses.get(owner, prev_id) if isinstance(prev_id, str) else None
        if previous is None:
            raise LocalApiError(
                f"response {prev_id!r} not found",
                param="previous_response_id",
                code="resource_not_found",
                status=404,
            )
        if state.response_latest.get(previous.data["session_id"]) != previous.id:
            raise LocalApiError(
                "previous_response_id: only the latest response of a conversation can be "
                "continued; the CLI session is linear",
                param="previous_response_id",
                code="agents.previous_response_not_latest",
            )
    created: Session | None = None
    try:
        if previous is not None:
            session = runtime.get_session(previous.data["session_id"])
            spec_name = state.session_meta[session.id].spec_name
            adapter = previous.data["adapter"]
            tools_echo = list(previous.data["tools"]) + [_tool_echo(t) for t in req_tools]
            model_display = previous.data["model"]
            model_resolved = previous.data["model_resolved"]
            instr_default = None
        else:
            definition = state.definitions.get(owner, model) if model.startswith("agent_") else None
            if definition is not None:
                adapter = definition.data["adapter"]
                def_tools = tools_of(definition)
                spec = spec_from_fields(
                    name="resp-" + uuid.uuid4().hex[:20],
                    adapter=adapter,
                    workspace=_workspace(),
                    instructions=definition.data.get("instructions"),
                    model=definition.data["model"],
                    tools=def_tools,
                    reasoning_effort=definition.data.get("reasoning_effort"),
                )
                model_display = definition.data["model"]
                model_resolved = spec.model is not None
                tools_echo = [_tool_echo(t) for t in def_tools] + [_tool_echo(t) for t in req_tools]
            else:
                selected = select_or_response(request, body)
                if isinstance(selected, ServerResponse):
                    return selected
                adapter = selected
                effort = None
                reasoning = body.get("reasoning")
                if isinstance(reasoning, dict) and adapter == "codex":
                    effort = reasoning.get("effort")
                    if effort not in (None, "none", "minimal", "low", "medium", "high", "xhigh"):
                        raise LocalApiError(
                            "reasoning.effort: invalid value", param="reasoning.effort"
                        )
                elif reasoning is not None and "reasoning" not in ignored:
                    ignored.append("reasoning")
                spec = spec_from_fields(
                    name="resp-" + uuid.uuid4().hex[:20],
                    adapter=adapter,
                    workspace=_workspace(),
                    instructions=None,
                    model=model,
                    tools=[],
                    reasoning_effort=effort,
                )
                model_resolved = spec.model is not None
                model_display = spec.model or adapter
                tools_echo = [_tool_echo(t) for t in req_tools]
            runtime.store.put(spec)
            session = runtime.create_session(spec.name, {})
            created = session
            spec_name = spec.name
            state.session_meta[session.id] = SessionMeta(
                owner=owner,
                kind="response",
                adapter=adapter,
                spec_name=spec_name,
                display_id=spec_name,
                display_model=model_display,
            )
            instr_default = None
        extra_mcp = {
            t.label: McpServerSpec(name=t.label, url=t.url, headers=dict(t.headers))
            for t in req_tools
        }
        rid = "resp_" + uuid.uuid4().hex[:24]
        record = state.responses.create(
            owner,
            {
                "session_id": session.id,
                "turn_id": "",
                "adapter": adapter,
                "model": model_display,
                "model_resolved": model_resolved,
                "instructions": body.get("instructions")
                if isinstance(body.get("instructions"), str)
                else instr_default,
                "metadata": metadata,
                "tools": tools_echo,
                "input_items": input_items,
                "background": bool(body.get("background")),
                "store": store,
                "previous_response_id": prev_id,
                "steered": steered,
            },
            rid=rid,
        )
        turn = submit_turn(
            session,
            prompt,
            instructions=instructions,
            extra_mcp=extra_mcp,
            input_items=input_items,
            extra={"response_id": rid},
        )
    except Exception:
        if created is not None:
            state.session_meta.pop(created.id, None)
            with contextlib.suppress(AgentNotFoundError):
                runtime.delete_session(created.id)
            runtime.store.delete(created.agent_name)
        raise
    record.data["turn_id"] = turn.id
    state.response_latest[session.id] = record.id
    if not store:
        _release_when_done(record, turn)
    return record, turn, session, ignored


_R = TypeVar("_R", ServerResponse, SSEResponse)


def _with_headers(response: _R, ignored: list[str]) -> _R:
    if ignored:
        response.headers[_IGNORED_HEADER] = ",".join(ignored)
    return response


def handle_responses_create(request: ServerRequest) -> ServerResponse | SSEResponse:
    """``POST /v1/responses`` (R-01)."""
    body = body_of(request)
    owner = principal_of(request)
    key = header(request, "Idempotency-Key")
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    state = get_state()
    if key:
        if len(key) > 128 or not key.isascii() or not key.isprintable():
            return err(
                400,
                "Idempotency-Key must be printable ASCII up to 128 characters",
                code="invalid_request",
                param="Idempotency-Key",
            )
        with state.lock:
            previous = state.idempotency.get((owner, "responses", key))
        if previous is not None:
            if previous[0] != digest:
                return err(
                    409,
                    "Idempotency-Key was reused with a different request body",
                    code="idempotency.mismatch",
                    param="Idempotency-Key",
                )
            record = state.responses.get(owner, previous[1])
            if record is not None:
                return _render(record, stream=bool(body.get("stream")), wait=True)
    result = _create_response(request, body)
    if isinstance(result, ServerResponse):
        return result
    record, turn, session, ignored = result
    if key:
        with state.lock:
            state.idempotency[(owner, "responses", key)] = (digest, record.id)
    if body.get("stream"):
        return _with_headers(
            _stream_response(record, turn, after=None, live=True),
            ignored,
        )
    if not body.get("background"):
        _wait(session, turn)
    obj = response_object(record, turn)
    if body.get("stream") is not True and record.data["background"]:
        obj["status"] = "in_progress" if turn.status in ("queued", "in_progress") else obj["status"]
    return _with_headers(ServerResponse.ok(obj), ignored)


def _render(record: Record, *, stream: bool, wait: bool) -> ServerResponse | SSEResponse:
    runtime = get_agent_runtime()
    try:
        session = runtime.get_session(record.data["session_id"])
    except AgentNotFoundError:
        return _missing(record.id)
    turn = _find_turn(session, record.data["turn_id"])
    if turn is None:
        return _missing(record.id)
    if stream:
        return _stream_response(record, turn, after=None, live=True)
    if wait and not record.data["background"]:
        _wait(session, turn)
    return ServerResponse.ok(response_object(record, turn))


# ---------------------------------------------------------------------- #
# R-02..R-05
# ---------------------------------------------------------------------- #


def _stored(request: ServerRequest) -> tuple[Record, Session, Turn] | ServerResponse:
    response_id = request.path_params["response_id"]
    record = get_state().responses.get(principal_of(request), response_id)
    if record is None:
        return _missing(response_id)
    try:
        session = get_agent_runtime().get_session(record.data["session_id"])
    except AgentNotFoundError:
        return _missing(response_id)
    turn = _find_turn(session, record.data["turn_id"])
    if turn is None:
        return _missing(response_id)
    return record, session, turn


def handle_response_get(request: ServerRequest) -> ServerResponse | SSEResponse:
    """``GET /v1/responses/{response_id}`` (R-02); ``stream=true`` replays the stored turn."""
    found = _stored(request)
    if isinstance(found, ServerResponse):
        return found
    record, _session, turn = found
    if first(request.query, "stream") == "true":
        after_raw = first(request.query, "starting_after")
        if after_raw is not None and not after_raw.isdigit():
            raise LocalApiError(
                "starting_after: expected a sequence number", param="starting_after"
            )
        after = int(after_raw) if after_raw is not None else None
        return _stream_response(record, turn, after=after, live=True)
    return ServerResponse.ok(response_object(record, turn))


def handle_response_delete(request: ServerRequest) -> ServerResponse:
    """``DELETE /v1/responses/{response_id}`` (R-03): the response and its turn record."""
    found = _stored(request)
    if isinstance(found, ServerResponse):
        return found
    record, _session, _turn = found
    _release(record)
    return ServerResponse.ok(
        {
            "id": record.id,
            "object": "response",
            "deleted": True,
            "x_agent_sandbox": label("response_is_cli_turn", compute="local_state"),
        }
    )


def handle_response_cancel(request: ServerRequest) -> ServerResponse:
    """``POST /v1/responses/{response_id}/cancel`` (R-04): only while the turn is running."""
    found = _stored(request)
    if isinstance(found, ServerResponse):
        return found
    record, _session, turn = found
    if turn.status not in ("queued", "in_progress"):
        raise LocalApiError(
            f"response is already {turn.status}; only a running response can be cancelled",
            param="response_id",
            code="agents.not_cancellable",
        )
    runtime = get_agent_runtime()
    runtime.cancel_turn(turn)
    runtime.wait(turn, runtime.kill_grace_s + runtime.term_grace_s + 5)
    return ServerResponse.ok(response_object(record, turn))


def handle_response_input_items(request: ServerRequest) -> ServerResponse:
    """``GET /v1/responses/{response_id}/input_items`` (R-05): items as accepted at create."""
    found = _stored(request)
    if isinstance(found, ServerResponse):
        return found
    record, _session, _turn = found
    items = [
        {**item, "x_agent_sandbox": label("response_is_cli_turn", compute="local_state")}
        for item in record.data["input_items"]
    ]
    return page(items, request.query)


# ---------------------------------------------------------------------- #
# R-07 compact
# ---------------------------------------------------------------------- #


def handle_responses_compact(request: ServerRequest) -> ServerResponse:
    """``POST /v1/responses/compact`` (R-07): Qwen ``/compress``; Codex is 400."""
    body = body_of(request)
    for key in body:
        if key not in ("model", "previous_response_id", "adapter", "runtime"):
            raise LocalApiError(f"{key}: compaction takes the stored conversation only", param=key)
    owner = principal_of(request)
    state = get_state()
    prev_id = body.get("previous_response_id")
    if not isinstance(prev_id, str) or not prev_id:
        raise LocalApiError(
            "previous_response_id: required; the summary is of that conversation",
            param="previous_response_id",
        )
    previous = state.responses.get(owner, prev_id)
    if previous is None:
        raise LocalApiError(
            f"response {prev_id!r} not found",
            param="previous_response_id",
            code="resource_not_found",
            status=404,
        )
    if previous.data["adapter"] != "qwen-code":
        raise LocalApiError(
            "compaction is not supported for codex: its exec mode emits no compaction item",
            param="model",
            code="agents.compact_unsupported",
        )
    if state.response_latest.get(previous.data["session_id"]) != previous.id:
        raise LocalApiError(
            "previous_response_id: only the latest response can be compacted",
            param="previous_response_id",
            code="agents.previous_response_not_latest",
        )
    runtime = get_agent_runtime()
    session = runtime.get_session(previous.data["session_id"])
    turn = submit_turn(session, "/compress", keep=False)
    _wait(session, turn)
    if turn.status != "completed":
        raise LocalApiError(
            "the CLI could not compress the conversation",
            code="agents.compact_failed",
            param="previous_response_id",
        )
    output = [_output_item(i) for i in turn.items if i.type == "message"]
    summary = " ".join(
        part["text"] for item in output for part in item["content"] if part.get("text")
    )
    extra: dict[str, Any] = {}
    try:
        counts = json.loads(summary)
        for key, out_key in (
            ("originalTokenCount", "original_token_count"),
            ("newTokenCount", "new_token_count"),
        ):
            if isinstance(counts, dict) and isinstance(counts.get(key), int):
                extra[out_key] = counts[key]
    except ValueError:
        pass
    return ServerResponse.ok(
        {
            "id": "resp_cmp_" + uuid.uuid4().hex[:20],
            "object": "response.compaction",
            "created_at": int(turn.created_at),
            "output": output,
            "usage": _usage(turn.usage),
            "x_agent_sandbox": label(
                "summary_not_encrypted_compaction", "response_is_cli_turn", **extra
            ),
        }
    )


# ---------------------------------------------------------------------- #
# R-08 socket engine (transport-independent)
# ---------------------------------------------------------------------- #


class ResponsesSocket:
    """Client-event engine of ``responses.connect``.

    ``response.create`` runs the same CLI turn as ``POST /v1/responses`` and returns its
    stream events. ``response.steer`` cannot reach a running ``codex exec`` or ``qwen``
    process, so it queues a successor turn behind the active one (``queued_steer``).
    The WebSocket transport itself lives outside this module.
    """

    def __init__(self, request: ServerRequest) -> None:
        self._request = request

    def handle(self, frame: dict[str, Any]) -> list[dict[str, Any]]:
        """Process one client event; returns the server events to send."""
        kind = frame.get("type")
        body = {k: v for k, v in frame.items() if k != "type"}
        if kind not in ("response.create", "response.steer"):
            raise LocalApiError(f"type: unsupported client event {kind!r}", param="type")
        body.pop("stream", None)
        try:
            result = _create_response(self._request, body, steered=kind == "response.steer")
        except AgentRuntimeError as exc:
            return [{"type": "error", "error": from_agent_exc(exc).body["error"]}]
        if isinstance(result, ServerResponse):
            return [{"type": "error", "error": result.body["error"]}]
        record, turn, session, _ignored = result
        _wait(session, turn)
        return _events_for(response_object(record, turn))


def handle_responses_connect(request: ServerRequest) -> ServerResponse:
    """``GET /v1/responses``: a plain HTTP GET is not a WebSocket upgrade."""
    return err(
        400,
        "responses.connect needs a WebSocket upgrade, which this HTTP transport does not "
        "perform; use POST /v1/responses",
        code="agents.websocket_upgrade_required",
    )
