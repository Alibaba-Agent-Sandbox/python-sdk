"""OpenAI-shaped Agents HTTP routes for the Codex and Qwen Code slice.

Mounted under :data:`~easy_sandbox.server.router.CapabilityGroup.AGENTS`,
which stays disabled until ``EBX_SERVER_ENABLED_GROUPS`` includes ``agents``.
This module registers routes only. Sessions and turns are the existing
:class:`~easy_sandbox.server.agents.runtime.AgentRuntime`; wire objects come
from :mod:`easy_sandbox.server.agents.wire_sessions`; the other operations live in
the ``agents.api_*`` modules.

This slice serves ``codex`` and ``qwen-code`` (aliases ``qwen``, ``qwencode``,
``qwen_code``). Any other adapter name is ``404 not_found_error``. A request
that does not name one uses the first entry of
:data:`~easy_sandbox.server.agents.api_common.DEFAULT_AGENT_ORDER` (``codex``),
unless ``EBX_AGENTS_DEFAULT`` or ``EBX_AGENTS_CONFIG`` names another.

Everything here is a local operation. Every response carries
``X-Easy-Sandbox-Local: 1`` and every object an ``x_easy_sandbox`` label (see
:data:`~easy_sandbox.server.agents.api_common.DIFFERENCES`). The operations with no local
capability (``POST /v1/responses/input_tokens``, ``DELETE /v1/models/{id}``, executor
registration and channel) answer ``404 not_found_error`` with ``x-should-retry: false``.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from .agents.api_common import (
    DEFAULT_AGENT_ORDER,
    default_runtime_name,
    get_agent_runtime,
    label,
    local,
    reset_agent_runtime,
    select_or_response,
)
from .agents.api_common import (
    body_of as _body,
)
from .agents.api_common import (
    err as _err,
)
from .agents.api_common import (
    first as _first,
)
from .agents.api_common import (
    from_agent_exc as _from_agent_exc,
)
from .agents.api_common import (
    header as _header,
)
from .agents.api_common import (
    page as _page,
)
from .agents.api_common import (
    text_of as _text_of,
)
from .agents.api_definitions import (
    handle_definitions_create,
    handle_definitions_delete,
    handle_definitions_get,
    handle_definitions_list,
    handle_definitions_update,
)
from .agents.api_environments import (
    handle_blobs_create,
    handle_environment_files_create,
    handle_environment_files_list,
    handle_environments_create,
    handle_environments_get,
    handle_environments_list,
    handle_templates_create,
    handle_templates_delete,
    handle_templates_get,
    handle_templates_list,
    handle_templates_update,
)
from .agents.api_other import (
    handle_cannot_executor_channel,
    handle_cannot_executor_registration,
    handle_cannot_input_tokens,
    handle_cannot_model_delete,
    handle_event_types,
    handle_models_get,
    handle_models_list,
    handle_webhooks_create,
    handle_webhooks_delete,
    handle_webhooks_get,
    handle_webhooks_list,
    handle_webhooks_rotate,
    handle_webhooks_test,
    handle_webhooks_update,
)
from .agents.api_responses import (
    handle_response_cancel,
    handle_response_delete,
    handle_response_get,
    handle_response_input_items,
    handle_responses_compact,
    handle_responses_connect,
    handle_responses_create,
)
from .agents.api_sessions import (
    cleanup_session,
    decorate_session,
    decorate_turns_items,
    handle_artifact_content,
    handle_artifacts_delete,
    handle_artifacts_get,
    handle_artifacts_list,
    handle_session_update,
    handle_subagent_get,
    handle_subagent_items,
    handle_subagent_turn_get,
    handle_subagent_turn_items,
    handle_subagent_turns,
    handle_subagents_list,
    handle_traces_list,
    plan_session,
    session_or_error,
    submit_turn,
    visible_sessions,
)
from .agents.api_vaults import (
    handle_credentials_create,
    handle_credentials_delete,
    handle_credentials_get,
    handle_credentials_list,
    handle_credentials_update,
    handle_vaults_create,
    handle_vaults_delete,
    handle_vaults_get,
    handle_vaults_list,
    handle_vaults_update,
)
from .agents.errors import AgentRuntimeError
from .agents.local_state import get_state
from .agents.webhooks import emit as _emit_webhook
from .agents.wire_sessions import (
    SessionsEventMapper,
    item_object,
    session_object,
    sse_frame,
    turn_object,
)
from .router import CapabilityGroup, default_table
from .types import ServerRequest, ServerResponse, SSEResponse

if TYPE_CHECKING:
    from .agents.runtime import Session

__all__ = [
    "get_agent_runtime",
    "reset_agent_runtime",
]


# ---------------------------------------------------------------------- #
# Small parsers
# ---------------------------------------------------------------------- #


def _ack() -> ServerResponse:
    """HTTP 202 with an empty body (the dispatcher writes no JSON for this)."""
    return ServerResponse(status=202)


def _idempotency_key(request: ServerRequest) -> str | None | ServerResponse:
    key = _header(request, "Idempotency-Key")
    if key is None:
        return None
    if len(key) > 128 or not key.isascii() or not key.isprintable():
        return _err(
            400,
            "Idempotency-Key must be printable ASCII up to 128 characters",
            code="invalid_request",
            param="Idempotency-Key",
        )
    return key


def _idem_book(session: Session) -> dict[str, str]:
    book = getattr(session, "_idem_digest", None)
    if not isinstance(book, dict):
        book = {}
        session._idem_digest = book  # type: ignore[attr-defined]
    return book


def _agent_id_of(session: Session) -> str:
    meta = get_state().session_meta.get(session.id)
    return meta.display_id if meta else session.agent_name


def _session_obj(session: Session) -> dict[str, Any]:
    spec = get_agent_runtime().store.get(session.agent_name)
    return decorate_session(session_object(session, spec), session)


# ---------------------------------------------------------------------- #
# Handlers
# ---------------------------------------------------------------------- #


def handle_sessions_create(request: ServerRequest) -> ServerResponse:
    """``POST /v1/agents/sessions`` — bind a session to codex or qwen-code."""
    body = _body(request)
    if body.get("agent_id") is None:
        selected = select_or_response(request, body)
        if isinstance(selected, ServerResponse):
            return selected
    runtime = get_agent_runtime()
    try:
        plan = plan_session(request, body)
        runtime.store.put(plan.spec)
        try:
            session = runtime.create_session(plan.spec.name, _metadata(body))
        except AgentRuntimeError:
            runtime.store.delete(plan.spec.name)
            raise
        get_state().session_meta[session.id] = plan.meta
        _emit_webhook(
            plan.meta.owner,
            "agent.session.created",
            {
                "id": session.id,
                "environment_type": "self_hosted",
                "environment_id": plan.meta.environment_id,
            },
        )
        prompt = _text_of(body.get("input"))
        if prompt:
            submit_turn(session, prompt)
    except AgentRuntimeError as exc:
        return _from_agent_exc(exc)
    return ServerResponse.ok(_session_obj(session))


def _metadata(body: dict[str, Any]) -> dict[str, str]:
    from .agents.errors import AgentConfigError

    raw = body.get("metadata")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise AgentConfigError("metadata: expected a mapping of strings")
    out: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, (dict, list)) or value is None:
            raise AgentConfigError(f"metadata.{key}: expected a scalar")
        out[str(key)] = str(value)
    return out


def handle_sessions_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/sessions``."""
    objects = [_session_obj(session) for session in visible_sessions(request)]
    agent_id = _first(request.query, "agent_id")
    if agent_id is not None:
        objects = [o for o in objects if o["agent"]["id"] == agent_id]
    return _page(objects, request.query)


def handle_sessions_get(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/sessions/{id}``."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    return ServerResponse.ok(_session_obj(found))


def handle_sessions_delete(request: ServerRequest) -> ServerResponse:
    """``DELETE /v1/agents/sessions/{id}``."""
    session_id = request.path_params["id"]
    found = session_or_error(request, session_id)
    if isinstance(found, ServerResponse):
        return found
    try:
        get_agent_runtime().delete_session(session_id)
    except AgentRuntimeError as exc:
        return _from_agent_exc(exc)
    cleanup_session(session_id)
    return ServerResponse.ok(
        {
            "id": session_id,
            "object": "agent.session.deleted",
            "deleted": True,
            "x_easy_sandbox": decorate_session({"agent": {}}, found)["x_easy_sandbox"],
        }
    )


def _event_prompt(body: dict[str, Any]) -> tuple[str, bool] | ServerResponse:
    """Return ``(prompt, cancel)`` from an events body."""
    events = body.get("events")
    if events is None and "input" in body:
        return _text_of(body.get("input")), False
    if not isinstance(events, list) or not events:
        return _err(400, "events must be a non-empty list", code="invalid_request", param="events")
    texts: list[str] = []
    cancel = False
    for event in events:
        if not isinstance(event, dict):
            return _err(400, "each event must be an object", code="invalid_request", param="events")
        kind = event.get("type")
        if kind in ("agent.session.input.message", "input.message"):
            texts.append(_text_of(event.get("input", event.get("content", event.get("text")))))
        elif kind in ("agent.session.input.cancel", "input.cancel"):
            cancel = True
        elif kind in (
            "agent.session.input.tool_result",
            "agent.session.input.computer_use_approval_request_result",
        ):
            return _err(
                400,
                "tool results are not supported by this server",
                code="agents.tool_result_unsupported",
                param="events",
            )
        else:
            return _err(
                400,
                f"unsupported event type {kind!r}",
                code="invalid_request",
                param="events",
            )
    prompt = "\n".join(part for part in texts if part)
    if not prompt and not cancel:
        return _err(400, "input message is empty", code="invalid_request", param="events")
    return prompt, cancel


def handle_events_create(request: ServerRequest) -> ServerResponse:
    """``POST /v1/agents/sessions/{id}/events`` — queue a turn, HTTP 202, empty body."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    body = _body(request)
    key = _idempotency_key(request)
    if isinstance(key, ServerResponse):
        return key
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    if key:
        with found.cond:
            previous = _idem_book(found).get(key)
        if previous == digest:
            return _ack()
        if previous is not None:
            return _err(
                409,
                "Idempotency-Key was reused with a different request body",
                code="idempotency.mismatch",
                param="Idempotency-Key",
            )
    parsed = _event_prompt(body)
    if isinstance(parsed, ServerResponse):
        return parsed
    prompt, cancel = parsed
    runtime = get_agent_runtime()
    try:
        if cancel:
            runtime.cancel_active(found)
        if prompt:
            submit_turn(found, prompt, idempotency_key=key)
    except AgentRuntimeError as exc:
        return _from_agent_exc(exc)
    if key:
        with found.cond:
            book = _idem_book(found)
            book[key] = digest
            while len(book) > 256:
                book.pop(next(iter(book)))
    return _ack()


def _parse_after(query: dict[str, list[str]]) -> int | ServerResponse | None:
    raw = _first(query, "after")
    if raw is None:
        return None
    digits = raw
    if raw.startswith("evt_"):
        digits = ""
        for char in raw[4:]:
            if char.isdigit():
                digits += char
            else:
                break
    if not digits.isdigit():
        return _err(
            400,
            "after must be a sequence number or evt_<seq>",
            code="invalid_request",
            param="after",
        )
    return int(digits)


def _caught_up(session: Session, seq: int) -> bool:
    with session.cond:
        return session.active is None and not session.queue and session.last_seq == seq


def _iter_events(session: Session, after: int | None) -> Any:
    """Map runtime events to SSE. Close after a caught-up ``session.idle``."""
    spec = get_agent_runtime().store.get(session.agent_name)
    mapper = SessionsEventMapper(session, spec)
    cursor = session.last_seq if after is None else after
    for event in session.subscribe(after=cursor, ping_s=15.0):
        if event is None:
            yield ": ping\n\n"
            continue
        for wire in mapper.map(event):
            yield sse_frame(wire, event.seq)
        if event.type == "session.idle" and _caught_up(session, event.seq):
            return


def handle_events_stream(request: ServerRequest) -> SSEResponse | ServerResponse:
    """``GET /v1/agents/sessions/{id}/events`` — SSE of mapped session events.

    ``Accept: text/event-stream`` is the wire. The route is registered with
    ``streaming=True`` and always returns :class:`SSEResponse` for a live
    session. ``?after=<seq>`` replays the ring buffer (``after`` omitted tails
    from now and stays open through the next idle).
    """
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    after = _parse_after(request.query)
    if isinstance(after, ServerResponse):
        return after
    return SSEResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
        },
        event_iterator=_iter_events(found, after),
    )


def _items(session: Session) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for turn in session.turns:
        if not turn.keep:
            continue
        objects.extend(decorate_turns_items(item_object(item), item=True) for item in turn.items)
    return objects


def _turns(session: Session) -> list[dict[str, Any]]:
    agent_id = _agent_id_of(session)
    return [
        decorate_turns_items(turn_object(turn, agent_id)) for turn in session.turns if turn.keep
    ]


def handle_items_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/sessions/{id}/items``."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    return _page(_items(found), request.query)


def handle_turns_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/sessions/{id}/turns``."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    return _page(_turns(found), request.query)


def handle_turns_get(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/sessions/{id}/turns/{turn_id}``."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    turn_id = request.path_params["turn_id"]
    for turn in found.turns:
        if turn.id == turn_id and turn.keep:
            return ServerResponse.ok(decorate_turns_items(turn_object(turn, _agent_id_of(found))))
    return _err(404, f"turn {turn_id!r} not found", code="resource_not_found", param="turn_id")


def handle_turn_items_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/sessions/{id}/turns/{turn_id}/items``."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    turn_id = request.path_params["turn_id"]
    for turn in found.turns:
        if turn.id == turn_id and turn.keep:
            objects = [decorate_turns_items(item_object(item), item=True) for item in turn.items]
            return _page(objects, request.query)
    return _err(404, f"turn {turn_id!r} not found", code="resource_not_found", param="turn_id")


def handle_runtimes_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/runtimes`` — codex, then qwen-code.

    ``default`` is true for the runtime a request uses when it does not name one.
    """
    runtime = get_agent_runtime()
    chosen = default_runtime_name()
    data: list[dict[str, Any]] = []
    for name in DEFAULT_AGENT_ORDER:
        info = dict(runtime.runtime_info(name))
        info["id"] = info["name"]
        info["object"] = "agent.runtime"
        info["default"] = info["name"] == chosen
        info["x_easy_sandbox"] = label(compute="none", installed=bool(info.get("installed")))
        data.append(info)
    return _page(data, request.query)


# ---------------------------------------------------------------------- #
# Registration
# ---------------------------------------------------------------------- #

_table = default_table()
_AGENTS = CapabilityGroup.AGENTS


def _register(
    method: str,
    path: str,
    handler: Any,
    name: str,
    *,
    streaming: bool = False,
) -> None:
    _table.register(
        method,
        path,
        local(handler),
        group=_AGENTS,
        streaming=streaming,
        name=name,
    )


# Sessions, events, items, turns (order matters: first match wins).
_register("POST", "/v1/agents/sessions", handle_sessions_create, "agents_sessions_create")
_register("GET", "/v1/agents/sessions", handle_sessions_list, "agents_sessions_list")
_register("GET", "/v1/agents/sessions/{id}", handle_sessions_get, "agents_sessions_get")
_register("POST", "/v1/agents/sessions/{id}", handle_session_update, "agents_sessions_update")
_register("DELETE", "/v1/agents/sessions/{id}", handle_sessions_delete, "agents_sessions_delete")
_register(
    "POST",
    "/v1/agents/sessions/{id}/events",
    handle_events_create,
    "agents_sessions_events_create",
)
_register(
    "GET",
    "/v1/agents/sessions/{id}/events",
    handle_events_stream,
    "agents_sessions_events_stream",
    streaming=True,
)
_register("GET", "/v1/agents/sessions/{id}/items", handle_items_list, "agents_sessions_items_list")
_register("GET", "/v1/agents/sessions/{id}/turns", handle_turns_list, "agents_sessions_turns_list")
_register(
    "GET", "/v1/agents/sessions/{id}/turns/{turn_id}", handle_turns_get, "agents_sessions_turns_get"
)
_register(
    "GET",
    "/v1/agents/sessions/{id}/turns/{turn_id}/items",
    handle_turn_items_list,
    "agents_sessions_turns_items_list",
)

# Artifacts, traces, subagents (A-27..A-37).
_register(
    "GET", "/v1/agents/sessions/{id}/artifacts", handle_artifacts_list, "agents_artifacts_list"
)
_register(
    "GET",
    "/v1/agents/sessions/{id}/artifacts/{artifact_id}",
    handle_artifacts_get,
    "agents_artifacts_get",
)
_register(
    "DELETE",
    "/v1/agents/sessions/{id}/artifacts/{artifact_id}",
    handle_artifacts_delete,
    "agents_artifacts_delete",
)
_register(
    "GET",
    "/v1/agents/sessions/{id}/artifacts/{artifact_id}/content",
    handle_artifact_content,
    "agents_artifacts_content",
    streaming=True,
)
_register("GET", "/v1/agents/sessions/{id}/traces", handle_traces_list, "agents_traces_list")
_register(
    "GET", "/v1/agents/sessions/{id}/subagents", handle_subagents_list, "agents_subagents_list"
)
_register(
    "GET",
    "/v1/agents/sessions/{id}/subagents/{subagent_id}",
    handle_subagent_get,
    "agents_subagents_get",
)
_register(
    "GET",
    "/v1/agents/sessions/{id}/subagents/{subagent_id}/items",
    handle_subagent_items,
    "agents_subagents_items_list",
)
_register(
    "GET",
    "/v1/agents/sessions/{id}/subagents/{subagent_id}/turns",
    handle_subagent_turns,
    "agents_subagents_turns_list",
)
_register(
    "GET",
    "/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}",
    handle_subagent_turn_get,
    "agents_subagents_turns_get",
)
_register(
    "GET",
    "/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}/items",
    handle_subagent_turn_items,
    "agents_subagents_turns_items_list",
)

_register("GET", "/v1/agents/runtimes", handle_runtimes_list, "agents_runtimes_list")

# Environments, files, reduced templates (A-06..A-15).
# The literal "templates" is registered before {environment_id}.
_register(
    "POST", "/v1/agents/environments", handle_environments_create, "agents_environments_create"
)
_register("GET", "/v1/agents/environments", handle_environments_list, "agents_environments_list")
_register(
    "POST",
    "/v1/agents/environments/templates",
    handle_templates_create,
    "agents_environment_templates_create",
)
_register(
    "GET",
    "/v1/agents/environments/templates",
    handle_templates_list,
    "agents_environment_templates_list",
)
_register(
    "GET",
    "/v1/agents/environments/templates/{environment_template_id}",
    handle_templates_get,
    "agents_environment_templates_get",
)
_register(
    "POST",
    "/v1/agents/environments/templates/{environment_template_id}",
    handle_templates_update,
    "agents_environment_templates_update",
)
_register(
    "DELETE",
    "/v1/agents/environments/templates/{environment_template_id}",
    handle_templates_delete,
    "agents_environment_templates_delete",
)
_register(
    "GET",
    "/v1/agents/environments/{environment_id}",
    handle_environments_get,
    "agents_environments_get",
)
_register(
    "POST",
    "/v1/agents/environments/{environment_id}/files",
    handle_environment_files_create,
    "agents_environment_files_create",
)
_register(
    "GET",
    "/v1/agents/environments/{environment_id}/files",
    handle_environment_files_list,
    "agents_environment_files_list",
)
_register(
    "POST",
    "/v1/agents/environments/{environment_id}/register",
    handle_cannot_executor_registration,
    "agents_cannot_executor_registration",
)
_register(
    "GET",
    "/v1/agents/environments/{environment_id}/connect",
    handle_cannot_executor_channel,
    "agents_cannot_executor_channel",
)

# Agent definitions (A-01..A-05). Registered last: {agent_id} matches any single segment.
_register("POST", "/v1/agents", handle_definitions_create, "agents_definitions_create")
_register("GET", "/v1/agents", handle_definitions_list, "agents_definitions_list")
_register("GET", "/v1/agents/{agent_id}", handle_definitions_get, "agents_definitions_get")
_register("POST", "/v1/agents/{agent_id}", handle_definitions_update, "agents_definitions_update")
_register("DELETE", "/v1/agents/{agent_id}", handle_definitions_delete, "agents_definitions_delete")

# Vaults and credentials (A-38..A-47).
_register("POST", "/v1/vaults", handle_vaults_create, "agents_vaults_create")
_register("GET", "/v1/vaults", handle_vaults_list, "agents_vaults_list")
_register("GET", "/v1/vaults/{vault_id}", handle_vaults_get, "agents_vaults_get")
_register("POST", "/v1/vaults/{vault_id}", handle_vaults_update, "agents_vaults_update")
_register("DELETE", "/v1/vaults/{vault_id}", handle_vaults_delete, "agents_vaults_delete")
_register(
    "POST",
    "/v1/vaults/{vault_id}/credentials",
    handle_credentials_create,
    "agents_vault_credentials_create",
)
_register(
    "GET",
    "/v1/vaults/{vault_id}/credentials",
    handle_credentials_list,
    "agents_vault_credentials_list",
)
_register(
    "GET",
    "/v1/vaults/{vault_id}/credentials/{credential_id}",
    handle_credentials_get,
    "agents_vault_credentials_get",
)
_register(
    "POST",
    "/v1/vaults/{vault_id}/credentials/{credential_id}",
    handle_credentials_update,
    "agents_vault_credentials_update",
)
_register(
    "DELETE",
    "/v1/vaults/{vault_id}/credentials/{credential_id}",
    handle_credentials_delete,
    "agents_vault_credentials_delete",
)

# Responses as a local one-shot CLI turn (R-01..R-05, R-07); R-06 is a labeled 404.
_register(
    "POST", "/v1/responses", handle_responses_create, "agents_responses_create", streaming=True
)
_register("GET", "/v1/responses", handle_responses_connect, "agents_responses_connect")
_register(
    "POST",
    "/v1/responses/input_tokens",
    handle_cannot_input_tokens,
    "agents_cannot_responses_input_tokens",
)
_register("POST", "/v1/responses/compact", handle_responses_compact, "agents_responses_compact")
_register(
    "GET",
    "/v1/responses/{response_id}",
    handle_response_get,
    "agents_responses_get",
    streaming=True,
)
_register(
    "DELETE", "/v1/responses/{response_id}", handle_response_delete, "agents_responses_delete"
)
_register(
    "POST",
    "/v1/responses/{response_id}/cancel",
    handle_response_cancel,
    "agents_responses_cancel",
)
_register(
    "GET",
    "/v1/responses/{response_id}/input_items",
    handle_response_input_items,
    "agents_responses_input_items",
)

# Models, local file blobs and webhook endpoints (O-01..O-03, O-06..O-14).
_register("GET", "/v1/models", handle_models_list, "agents_models_list")
_register("GET", "/v1/models/{model}", handle_models_get, "agents_models_get")
_register("DELETE", "/v1/models/{model}", handle_cannot_model_delete, "agents_cannot_models_delete")
_register("POST", "/v1/files", handle_blobs_create, "agents_files_create")
_register("POST", "/v1/webhook_endpoints", handle_webhooks_create, "agents_webhooks_create")
_register("GET", "/v1/webhook_endpoints", handle_webhooks_list, "agents_webhooks_list")
_register(
    "GET",
    "/v1/webhook_endpoints/{webhook_endpoint_id}",
    handle_webhooks_get,
    "agents_webhooks_get",
)
_register(
    "POST",
    "/v1/webhook_endpoints/{webhook_endpoint_id}",
    handle_webhooks_update,
    "agents_webhooks_update",
)
_register(
    "DELETE",
    "/v1/webhook_endpoints/{webhook_endpoint_id}",
    handle_webhooks_delete,
    "agents_webhooks_delete",
)
_register(
    "POST",
    "/v1/webhook_endpoints/{webhook_endpoint_id}/rotate_secret",
    handle_webhooks_rotate,
    "agents_webhooks_rotate_secret",
)
_register(
    "POST",
    "/v1/webhook_endpoints/{webhook_endpoint_id}/test",
    handle_webhooks_test,
    "agents_webhooks_test",
)
_register("GET", "/v1/webhook_event_types", handle_event_types, "agents_webhook_event_types")
