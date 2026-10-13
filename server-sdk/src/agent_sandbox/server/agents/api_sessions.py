"""Session-side local operations: creation plan, turn submission, update, artifacts,
traces and subagent detail (A-18, A-27..A-37).
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import TYPE_CHECKING, Any

from ..types import ServerRequest, ServerResponse, SSEResponse
from .api_common import (
    body_of,
    err,
    first,
    get_agent_runtime,
    label,
    metadata_strict,
    page,
    principal_of,
    select_adapter,
    workspace_of,
)
from .api_definitions import (
    parse_agent_fields,
    spec_from_fields,
    tools_of,
)
from .api_vaults import bind_credentials, turn_mcp_servers
from .errors import AgentNotFoundError, LocalApiError
from .local_state import SessionMeta, get_state
from .redact import Redactor
from .subagents import collect_records, turns_for
from .webhooks import watch_session

if TYPE_CHECKING:
    from .config import AgentSpec, McpServerSpec
    from .runtime import Session, Turn

__all__ = [
    "SessionPlan",
    "artifact_object",
    "cleanup_session",
    "decorate_session",
    "decorate_turns_items",
    "handle_artifact_content",
    "handle_artifacts_delete",
    "handle_artifacts_get",
    "handle_artifacts_list",
    "handle_session_update",
    "handle_subagent_get",
    "handle_subagent_items",
    "handle_subagent_turn_get",
    "handle_subagent_turn_items",
    "handle_subagent_turns",
    "handle_subagents_list",
    "handle_traces_list",
    "plan_session",
    "session_or_error",
    "submit_turn",
    "visible_sessions",
]

_SESSION_UPDATE_REFUSED = {
    "agent": "agent cannot change after the session is created",
    "vault_ids": "vault_ids cannot change after the session is created",
    "environment": "environment cannot change after the session is created",
}


def _not_found(session_id: str) -> ServerResponse:
    return err(
        404, f"session {session_id!r} not found", code="resource_not_found", param="session_id"
    )


def _visible(session: Session, owner: str) -> bool:
    meta = get_state().session_meta.get(session.id)
    return meta is None or (meta.owner == owner and meta.kind == "session")


def session_or_error(request: ServerRequest, session_id: str) -> Session | ServerResponse:
    """Look up a session the caller owns. A foreign id answers like an unknown id."""
    try:
        session = get_agent_runtime().get_session(session_id)
    except AgentNotFoundError:
        return _not_found(session_id)
    if not _visible(session, principal_of(request)):
        return _not_found(session_id)
    return session


def visible_sessions(request: ServerRequest) -> list[Session]:
    """Sessions of the caller (response-backed sessions are not listed)."""
    owner = principal_of(request)
    return [s for s in get_agent_runtime().list_sessions() if _visible(s, owner)]


# ---------------------------------------------------------------------- #
# Creation plan
# ---------------------------------------------------------------------- #


class SessionPlan:
    """A validated session: its spec and the metadata kept beside the runtime session."""

    def __init__(self, spec: AgentSpec, meta: SessionMeta) -> None:
        self.spec = spec
        self.meta = meta


def _vault_ids(owner: str, raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw) or len(raw) > 16:
        raise LocalApiError("vault_ids: expected up to 16 vault ids", param="vault_ids")
    state = get_state()
    for i, vault_id in enumerate(raw):
        if state.vaults.get(owner, vault_id) is None:
            raise LocalApiError(
                f"vault {vault_id!r} not found",
                param=f"vault_ids[{i}]",
                code="resource_not_found",
                status=404,
            )
    return list(dict.fromkeys(raw))


def plan_session(request: ServerRequest, body: dict[str, Any]) -> SessionPlan:
    """Resolve ``agent`` / ``agent_id``, ``environment`` and ``vault_ids`` into a spec."""
    owner = principal_of(request)
    state = get_state()
    inline = body.get("agent")
    agent_id = body.get("agent_id")
    if agent_id is not None and inline is not None:
        raise LocalApiError("agent_id: send either agent or agent_id, not both", param="agent_id")
    spec_name = "ses-" + uuid.uuid4().hex[:20]

    env_record = None
    environment = body.get("environment")
    env_id = environment.get("id") if isinstance(environment, dict) else None
    if env_id is not None:
        env_record = state.environments.get(owner, env_id) if isinstance(env_id, str) else None
        if env_record is None:
            raise LocalApiError(
                f"environment {env_id!r} not found",
                param="environment.id",
                code="resource_not_found",
                status=404,
            )
    workspace = workspace_of(body)
    env_vars: dict[str, str] = {}
    vault_ids = _vault_ids(owner, body.get("vault_ids"))
    if env_record is not None:
        bound = env_record.data["workspace_directory"]
        given = environment.get("workspace_directory") if isinstance(environment, dict) else None
        if given and given != bound:
            raise LocalApiError(
                "environment.workspace_directory differs from the environment's own directory",
                param="environment.workspace_directory",
            )
        workspace = bound
        env_vars = dict(env_record.private["env"])
        vault_ids = list(dict.fromkeys([*vault_ids, *env_record.data["vault_ids"]]))

    if agent_id is not None:
        definition = state.definitions.get(owner, agent_id) if isinstance(agent_id, str) else None
        if definition is None:
            raise LocalApiError(
                f"agent {agent_id!r} not found",
                param="agent_id",
                code="resource_not_found",
                status=404,
            )
        d = definition.data
        adapter = d["adapter"]
        tools = tools_of(definition)
        spec = spec_from_fields(
            name=spec_name,
            adapter=adapter,
            workspace=workspace,
            instructions=d.get("instructions"),
            model=d["model"],
            tools=tools,
            reasoning_effort=d.get("reasoning_effort"),
            env=env_vars,
        )
        display_id, display_name, display_model = definition.id, d.get("name"), d["model"]
        definition_id: str | None = definition.id
    else:
        adapter = select_adapter(request, body)
        agent = inline if isinstance(inline, dict) else {}
        fields = parse_agent_fields(
            {k: v for k, v in agent.items() if k not in ("adapter", "runtime")},
            adapter,
            create=False,
            prefix="agent.",
            allow_keys=frozenset(
                {
                    "model",
                    "instructions",
                    "name",
                    "metadata",
                    "multi_agent",
                    "reasoning",
                    "service_tier",
                    "text",
                    "tools",
                }
            ),
        )
        if body.get("tools") is not None:
            raise LocalApiError("tools: send tools inside agent", param="tools")
        tools = list(fields.get("tools") or [])
        from .api_common import model_field

        spec = spec_from_fields(
            name=spec_name,
            adapter=adapter,
            workspace=workspace,
            instructions=fields.get("instructions"),
            model=model_field(body),
            tools=tools,
            reasoning_effort=fields.get("reasoning_effort"),
            env=env_vars,
        )
        display_name = fields.get("name") or adapter
        display_id = str(display_name)
        display_model = spec.model or adapter
        definition_id = None

    bindings = bind_credentials(owner, vault_ids, tools)
    meta = SessionMeta(
        owner=owner,
        kind="session",
        adapter=adapter,
        spec_name=spec_name,
        display_id=display_id,
        display_name=display_name,
        display_model=display_model,
        tools_wire=[t.wire() for t in tools],
        definition_id=definition_id,
        environment_id=env_record.id if env_record is not None else None,
        vault_ids=vault_ids,
        bindings=bindings,
    )
    return SessionPlan(spec, meta)


def decorate_session(obj: dict[str, Any], session: Session) -> dict[str, Any]:
    """Apply local ids, tools and the label to an ``agent.session`` object."""
    obj["x_agent_sandbox"] = label("queued_not_steered", "usage_adapter_best_effort")
    meta = get_state().session_meta.get(session.id)
    if meta is None:
        return obj
    agent = obj["agent"]
    agent["id"] = meta.display_id
    agent["name"] = meta.display_name
    agent["model"] = meta.display_model
    agent["tools"] = list(meta.tools_wire)
    obj["vault_ids"] = list(meta.vault_ids)
    if meta.environment_id:
        obj["environment"]["id"] = meta.environment_id
    return obj


def decorate_turns_items(obj: dict[str, Any], *, item: bool = False) -> dict[str, Any]:
    """Label a turn or item object."""
    obj["x_agent_sandbox"] = label("redaction_best_effort" if item else "usage_adapter_best_effort")
    return obj


def cleanup_session(session_id: str) -> None:
    """Forget everything the local API keeps for a deleted session."""
    state = get_state()
    meta = state.session_meta.pop(session_id, None)
    state.artifacts.drop_session(session_id)
    if meta is not None:
        get_agent_runtime().store.delete(meta.spec_name)


# ---------------------------------------------------------------------- #
# Turn submission
# ---------------------------------------------------------------------- #


def submit_turn(
    session: Session,
    prompt: str,
    *,
    idempotency_key: str | None = None,
    instructions: str | None = None,
    extra_mcp: dict[str, McpServerSpec] | None = None,
    keep: bool = True,
    input_items: list[dict[str, Any]] | None = None,
    turn_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Turn:
    """Queue a turn with the vault credentials of the session injected as MCP headers.

    Raises:
        LocalApiError: a credential the session needs was deleted or expired.
    """
    runtime = get_agent_runtime()
    state = get_state()
    meta = state.session_meta.get(session.id)
    spec = runtime.store.get(session.agent_name)
    servers = turn_mcp_servers(meta.owner, meta, spec) if meta else {}
    if extra_mcp:
        servers.update(extra_mcp)
    after = session.last_seq
    turn = runtime.submit(
        session,
        prompt,
        instructions=instructions,
        mcp_servers=servers or None,
        keep=keep,
        input_items=input_items,
        idempotency_key=idempotency_key,
        turn_id=turn_id,
        extra=extra,
    )
    if meta is not None:
        watch_session(session, meta.owner, after, meta.environment_id)
    return turn


# ---------------------------------------------------------------------- #
# A-18 update
# ---------------------------------------------------------------------- #


def handle_session_update(request: ServerRequest) -> ServerResponse:
    """``POST /v1/agents/sessions/{id}`` (A-18): ``metadata`` only."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    body = body_of(request)
    for key in body:
        if key in _SESSION_UPDATE_REFUSED:
            raise LocalApiError(f"{key}: {_SESSION_UPDATE_REFUSED[key]}", param=key)
        if key != "metadata":
            raise LocalApiError(f"{key}: only metadata can be updated", param=key)
    if "metadata" in body:
        metadata = metadata_strict(body["metadata"])
        with found.cond:
            found.metadata = dict(metadata)
    from .wire_sessions import session_object

    runtime = get_agent_runtime()
    obj = session_object(found, runtime.store.get(found.agent_name))
    return ServerResponse.ok(decorate_session(obj, found))


# ---------------------------------------------------------------------- #
# Artifacts (A-27..A-30)
# ---------------------------------------------------------------------- #


def artifact_object(record: dict[str, Any], session: Session) -> dict[str, Any]:
    """``agent.session.artifact`` for a snapshot."""
    meta = get_state().session_meta.get(session.id)
    return {
        "id": record["id"],
        "object": "agent.session.artifact",
        "created_at": record["created_at"],
        "environment_id": (meta.environment_id if meta else None) or "env_agent_sandbox",
        "path": "/workspace/" + record["rel"],
        "session_id": record["session_id"],
        "size_bytes": record["size_bytes"],
        "turn_id": record["turn_id"],
        "x_agent_sandbox": label("snapshot_copy", "reported_paths_only", compute="local_state"),
    }


def _artifact_missing(artifact_id: str) -> ServerResponse:
    return err(
        404, f"artifact {artifact_id!r} not found", code="resource_not_found", param="artifact_id"
    )


def handle_artifacts_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/sessions/{id}/artifacts`` (A-27)."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    objects = [artifact_object(r, found) for r in get_state().artifacts.list(found.id)]
    env_filter = first(request.query, "environment_id")
    if env_filter is not None:
        objects = [o for o in objects if o["environment_id"] == env_filter]
    return page(objects, request.query)


def handle_artifacts_get(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/sessions/{id}/artifacts/{artifact_id}`` (A-28)."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    record = get_state().artifacts.get(found.id, request.path_params["artifact_id"])
    if record is None:
        return _artifact_missing(request.path_params["artifact_id"])
    return ServerResponse.ok(artifact_object(record, found))


def handle_artifacts_delete(request: ServerRequest) -> ServerResponse:
    """``DELETE /v1/agents/sessions/{id}/artifacts/{artifact_id}`` (A-29): snapshot only."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    artifact_id = request.path_params["artifact_id"]
    if not get_state().artifacts.delete(found.id, artifact_id):
        return _artifact_missing(artifact_id)
    return ServerResponse.ok(
        {
            "id": artifact_id,
            "object": "agent.session.artifact.deleted",
            "deleted": True,
            "x_agent_sandbox": label(
                "delete_removes_snapshot_only",
                "snapshot_copy",
                compute="local_state",
                deleted_scope="snapshot",
            ),
        }
    )


def handle_artifact_content(request: ServerRequest) -> SSEResponse | ServerResponse:
    """``GET /v1/agents/sessions/{id}/artifacts/{artifact_id}/content`` (A-30)."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    artifact_id = request.path_params["artifact_id"]
    store = get_state().artifacts
    record = store.get(found.id, artifact_id)
    data = store.read(record) if record else None
    if record is None or data is None:
        return _artifact_missing(artifact_id)
    name = os.path.basename(record["rel"]).replace('"', "").replace("\\", "")
    return SSEResponse(
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(data)),
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
        event_iterator=iter([data]),
    )


# ---------------------------------------------------------------------- #
# Traces (A-31)
# ---------------------------------------------------------------------- #


def _attr(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    return {"key": key, "value": {"stringValue": str(value)}}


def handle_traces_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/sessions/{id}/traces`` (A-31).

    Empty unless ``ABX_AGENTS_TRACES=1``. When enabled, one trace per finished turn with a
    single span built only from the journal's start and end times. Span attributes carry
    the turn status and item count, never text, commands or arguments.
    """
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    traces: list[dict[str, Any]] = []
    if os.environ.get("ABX_AGENTS_TRACES", "") == "1":
        for turn in found.turns:
            if not turn.keep or turn.started_at is None or turn.completed_at is None:
                continue
            digest = hashlib.sha256(turn.id.encode()).hexdigest()
            span = {
                "traceId": digest[:32],
                "spanId": digest[32:48],
                "name": "agent.turn",
                "kind": 1,
                "startTimeUnixNano": str(int(turn.started_at * 1e9)),
                "endTimeUnixNano": str(int(turn.completed_at * 1e9)),
                "attributes": [
                    _attr("turn.status", turn.status),
                    _attr("turn.items", len(turn.items)),
                ],
                "status": {"code": 2 if turn.status == "failed" else 1},
            }
            traces.append(
                {
                    "id": "trace_" + digest[:24],
                    "object": "agent.session.trace",
                    "created_at": int(turn.completed_at),
                    "session_id": found.id,
                    "otlp": {
                        "resourceSpans": [
                            {
                                "resource": {
                                    "attributes": [_attr("service.name", "agent-sandbox-local")]
                                },
                                "scopeSpans": [
                                    {"scope": {"name": "agent-sandbox-agents"}, "spans": [span]}
                                ],
                            }
                        ]
                    },
                    "x_agent_sandbox": label(
                        "trace_from_journal_timing_only", compute="local_state"
                    ),
                }
            )
    return page(traces, request.query)


# ---------------------------------------------------------------------- #
# Subagents (A-32..A-37)
# ---------------------------------------------------------------------- #


def _parent_id(session: Session) -> str:
    meta = get_state().session_meta.get(session.id)
    return meta.display_id if meta else session.agent_name


def _runtime_name(session: Session) -> str:
    spec = get_agent_runtime().store.get(session.agent_name)
    return spec.runtime if spec else ""


def _redact(session: Session, value: Any) -> Any:
    spec = get_agent_runtime().store.get(session.agent_name)
    return Redactor(spec.secret_values() if spec else []).redact_obj(value)


def _subagent_label(*extra: str) -> dict[str, Any]:
    return label("ids_from_cli_only", *extra, compute="local_process")


def _subagent_object(record: dict[str, Any], session: Session) -> dict[str, Any]:
    instructions = record.get("instructions")
    return {
        "id": record["id"],
        "object": "agent.session.subagent",
        "session_id": session.id,
        "parent_agent_id": _parent_id(session),
        "name": record.get("name"),
        "instructions": [{"type": "input_text", "text": instructions}] if instructions else None,
        "opened_at": int(record["opened_at"]),
        "closed_at": None if record["closed_at"] is None else int(record["closed_at"]),
        "status": "closed" if record["closed_at"] is not None else "active",
        "x_agent_sandbox": _subagent_label(),
    }


def _find_subagent(
    request: ServerRequest,
) -> tuple[Session, dict[str, Any]] | ServerResponse:
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    sid = request.path_params["subagent_id"]
    runtime = get_agent_runtime()
    for record in collect_records(found, _runtime_name(found), runtime._environ):
        if record["id"] == sid:
            return found, record
    return err(404, f"subagent {sid!r} not found", code="resource_not_found", param="subagent_id")


def _turn_objects(
    session: Session, record: dict[str, Any], turns: list[Any], how: str
) -> list[dict[str, Any]]:
    running = session.status == "in_progress"
    out: list[dict[str, Any]] = []
    for turn in turns:
        complete = bool(turn["complete"]) or not running
        out.append(
            {
                "id": turn["id"],
                "object": "agent.session.turn",
                "agent_id": record["id"],
                "session_id": session.id,
                "status": "completed" if complete else "in_progress",
                "created_at": int(record["opened_at"]),
                "started_at": int(record["opened_at"]),
                "completed_at": None
                if not complete
                else int(record["closed_at"] or record["opened_at"]),
                "error": None,
                "subagent_id": record["id"],
                "usage": None,
                "x_agent_sandbox": _subagent_label(how),
            }
        )
    return out


def _item_objects(
    session: Session, record: dict[str, Any], turns: list[Any], how: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for turn in turns:
        for position, entry in enumerate(_redact(session, turn["entries"]), start=1):
            base = {
                "id": f"item_{position}_{turn['id']}",
                "turn_id": turn["id"],
                "x_agent_sandbox": _subagent_label(how),
            }
            kind = entry.get("kind")
            if kind == "message":
                role = entry.get("role") or "assistant"
                items.append(
                    {
                        **base,
                        "type": "message",
                        "role": role,
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text" if role == "assistant" else "input_text",
                                "text": entry.get("text") or "",
                            }
                        ],
                    }
                )
            elif kind == "reasoning":
                items.append(
                    {
                        **base,
                        "type": "reasoning",
                        "status": "completed",
                        "summary": [{"type": "summary_text", "text": entry.get("text") or ""}],
                    }
                )
            elif kind == "tool_call":
                ok = entry.get("ok")
                items.append(
                    {
                        **base,
                        "type": "tool_call",
                        "status": "in_progress"
                        if ok is None
                        else ("completed" if ok else "failed"),
                        "tool_name": entry.get("name"),
                        "arguments": entry.get("arguments"),
                        "output": entry.get("output"),
                    }
                )
    return items


def handle_subagents_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/sessions/{id}/subagents`` (A-32)."""
    found = session_or_error(request, request.path_params["id"])
    if isinstance(found, ServerResponse):
        return found
    runtime = get_agent_runtime()
    records = collect_records(found, _runtime_name(found), runtime._environ)
    return page([_subagent_object(r, found) for r in records], request.query)


def handle_subagent_get(request: ServerRequest) -> ServerResponse:
    """``GET .../subagents/{subagent_id}`` (A-33)."""
    located = _find_subagent(request)
    if isinstance(located, ServerResponse):
        return located
    session, record = located
    return ServerResponse.ok(_subagent_object(record, session))


def _turns(
    request: ServerRequest,
) -> tuple[Session, dict[str, Any], list[Any], str] | ServerResponse:
    located = _find_subagent(request)
    if isinstance(located, ServerResponse):
        return located
    session, record = located
    turns, how = turns_for(record, get_agent_runtime()._environ)
    return session, record, turns, how


def handle_subagent_items(request: ServerRequest) -> ServerResponse:
    """``GET .../subagents/{subagent_id}/items`` (A-34)."""
    result = _turns(request)
    if isinstance(result, ServerResponse):
        return result
    session, record, turns, how = result
    return page(_item_objects(session, record, turns, how), request.query)


def handle_subagent_turns(request: ServerRequest) -> ServerResponse:
    """``GET .../subagents/{subagent_id}/turns`` (A-35)."""
    result = _turns(request)
    if isinstance(result, ServerResponse):
        return result
    session, record, turns, how = result
    return page(_turn_objects(session, record, turns, how), request.query)


def _one_turn(
    request: ServerRequest,
) -> tuple[Session, dict[str, Any], list[Any], str, str] | ServerResponse:
    result = _turns(request)
    if isinstance(result, ServerResponse):
        return result
    session, record, turns, how = result
    turn_id = request.path_params["turn_id"]
    chosen = [t for t in turns if t["id"] == turn_id]
    if not chosen:
        return err(404, f"turn {turn_id!r} not found", code="resource_not_found", param="turn_id")
    return session, record, chosen, how, turn_id


def handle_subagent_turn_get(request: ServerRequest) -> ServerResponse:
    """``GET .../subagents/{subagent_id}/turns/{turn_id}`` (A-36)."""
    result = _one_turn(request)
    if isinstance(result, ServerResponse):
        return result
    session, record, chosen, how, _ = result
    return ServerResponse.ok(_turn_objects(session, record, chosen, how)[0])


def handle_subagent_turn_items(request: ServerRequest) -> ServerResponse:
    """``GET .../subagents/{subagent_id}/turns/{turn_id}/items`` (A-37)."""
    result = _one_turn(request)
    if isinstance(result, ServerResponse):
        return result
    session, record, chosen, how, _ = result
    return page(_item_objects(session, record, chosen, how), request.query)
