"""Agent definitions: ``/v1/agents`` create, retrieve, update, list, delete (A-01..A-05).

A definition is a stored spec for a codex or qwen-code session. Only MCP tools are real;
every other tool type, ``multi_agent.enabled`` and a ``service_tier`` outside ``auto|default``
are refused with 400 rather than accepted and ignored. Header values of an MCP tool are
write-only: they are kept in memory and never echoed.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..types import ServerRequest, ServerResponse
from .adapters import default_adapters
from .api_common import (
    body_of,
    err,
    label,
    metadata_strict,
    page,
    principal_of,
    select_or_response,
    url_check,
)
from .config import AgentSpec
from .errors import LocalApiError
from .local_state import Record, get_state

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "McpTool",
    "definition_object",
    "handle_definitions_create",
    "handle_definitions_delete",
    "handle_definitions_get",
    "handle_definitions_list",
    "handle_definitions_update",
    "parse_agent_fields",
    "parse_tools",
    "spec_from_fields",
]

_ALLOWED_KEYS = frozenset(
    {
        "model",
        "instructions",
        "metadata",
        "multi_agent",
        "name",
        "reasoning",
        "service_tier",
        "text",
        "tools",
        "adapter",
        "runtime",
    }
)
_LABEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_HEADER_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,128}$")
_MASK = "***"
_MAX_TOOLS = 32


class McpTool:
    """One validated MCP tool: public shape plus write-only headers."""

    def __init__(
        self,
        label_: str,
        url: str,
        headers: dict[str, str],
        credential_id: str | None,
    ) -> None:
        self.label = label_
        self.url = url
        self.headers = headers
        self.credential_id = credential_id

    def wire(self) -> dict[str, Any]:
        """Persisted-tool shape; header values are masked, never echoed."""
        return {
            "type": "mcp",
            "server_label": self.label,
            "transport": {
                "type": "http",
                "server_url": self.url,
                "headers": dict.fromkeys(self.headers, _MASK),
            },
            "allowed_tools": None,
            "connection_origin": "environment",
            "credential_id": self.credential_id,
            "request_metadata": {},
            "required": False,
        }


def parse_tools(raw: Any, field: str = "tools") -> list[McpTool]:
    """Validate ``tools``: only ``mcp`` over ``http`` is real; everything else is 400."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise LocalApiError(f"{field}: expected a list", param=field)
    if len(raw) > _MAX_TOOLS:
        raise LocalApiError(f"{field}: at most {_MAX_TOOLS} tools", param=field)
    tools: list[McpTool] = []
    seen: set[str] = set()
    for i, tool in enumerate(raw):
        where = f"{field}[{i}]"
        if not isinstance(tool, dict) or tool.get("type") != "mcp":
            raise LocalApiError(
                f"{where}.type: only mcp tools are supported by the local agent runtime",
                param=f"{where}.type",
            )
        label_ = tool.get("server_label")
        if not isinstance(label_, str) or not _LABEL_RE.match(label_):
            raise LocalApiError(
                f"{where}.server_label: 1 to 40 characters of [A-Za-z0-9_-]",
                param=f"{where}.server_label",
            )
        if label_ in seen:
            raise LocalApiError(f"{where}.server_label: duplicate label", param=where)
        seen.add(label_)
        transport = tool.get("transport")
        if not isinstance(transport, dict) or transport.get("type") != "http":
            raise LocalApiError(
                f"{where}.transport.type: only http MCP transports are supported",
                param=f"{where}.transport.type",
            )
        url = transport.get("server_url")
        url_check(url, f"{where}.transport.server_url", https_only=False, allow_private=True)
        headers = _headers(transport.get("headers"), f"{where}.transport.headers")
        _refuse_unenforced(tool, where)
        credential_id = tool.get("credential_id")
        if credential_id is not None and not isinstance(credential_id, str):
            raise LocalApiError(
                f"{where}.credential_id: expected a string", param=f"{where}.credential_id"
            )
        tools.append(McpTool(label_, str(url), headers, credential_id))
    return tools


def _refuse_unenforced(tool: dict[str, Any], where: str) -> None:
    if tool.get("allowed_tools"):
        raise LocalApiError(
            f"{where}.allowed_tools: neither CLI can restrict the MCP tool list",
            param=f"{where}.allowed_tools",
        )
    if tool.get("request_metadata"):
        raise LocalApiError(
            f"{where}.request_metadata: not forwarded to MCP servers locally",
            param=f"{where}.request_metadata",
        )
    if tool.get("required"):
        raise LocalApiError(
            f"{where}.required: a failing MCP connection does not fail the turn locally",
            param=f"{where}.required",
        )
    if tool.get("connection_origin") not in (None, "environment"):
        raise LocalApiError(
            f"{where}.connection_origin: there is no Managed Agents service network locally",
            param=f"{where}.connection_origin",
        )


def _headers(raw: Any, field: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise LocalApiError(f"{field}: expected a mapping of strings", param=field)
    out: dict[str, str] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not _HEADER_RE.match(name):
            raise LocalApiError(f"{field}: invalid header name", param=field)
        if (
            not isinstance(value, str)
            or not value
            or any(ch in value for ch in "\r\n\x00")
            or len(value) > 8192
        ):
            raise LocalApiError(
                f"{field}.{name}: expected a non-empty single-line string", param=f"{field}.{name}"
            )
        out[name] = value
    return out


def parse_agent_fields(
    src: Mapping[str, Any],
    adapter: str,
    *,
    create: bool,
    prefix: str = "",
    allow_keys: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Validate the official agent fields and return those that were present."""
    allowed = allow_keys if allow_keys is not None else _ALLOWED_KEYS
    for key in src:
        if key not in allowed:
            raise LocalApiError(
                f"{prefix}{key}: unknown or unsupported parameter", param=f"{prefix}{key}"
            )
    out: dict[str, Any] = {}
    if "model" in src or create:
        model = src.get("model")
        if not isinstance(model, str) or not model.strip() or len(model) > 256:
            raise LocalApiError(
                f"{prefix}model: a non-empty string is required", param=f"{prefix}model"
            )
        out["model"] = model.strip()
    if "name" in src:
        name = src["name"]
        if name is not None and (not isinstance(name, str) or len(name) > 256):
            raise LocalApiError(f"{prefix}name: expected a string", param=f"{prefix}name")
        out["name"] = name or None
    if "instructions" in src:
        text = src["instructions"]
        if text is not None and (not isinstance(text, str) or len(text) > 256 * 1024):
            raise LocalApiError(
                f"{prefix}instructions: expected a string", param=f"{prefix}instructions"
            )
        out["instructions"] = text or None
    if "metadata" in src:
        out["metadata"] = metadata_strict(src["metadata"], f"{prefix}metadata")
    if "multi_agent" in src:
        multi = src["multi_agent"]
        if multi is not None and not isinstance(multi, dict):
            raise LocalApiError(
                f"{prefix}multi_agent: expected an object", param=f"{prefix}multi_agent"
            )
        if multi and multi.get("enabled"):
            raise LocalApiError(
                f"{prefix}multi_agent.enabled: neither CLI has a switch that turns spawning on",
                param=f"{prefix}multi_agent.enabled",
            )
    if "service_tier" in src and src["service_tier"] not in (None, "auto", "default"):
        raise LocalApiError(
            f"{prefix}service_tier: only auto and default are accepted",
            param=f"{prefix}service_tier",
        )
    if "text" in src:
        _check_text(src["text"], prefix)
    if "reasoning" in src:
        out["reasoning_effort"] = _check_reasoning(src["reasoning"], adapter, prefix)
    if "tools" in src:
        out["tools"] = parse_tools(src["tools"], f"{prefix}tools")
    return out


def _check_text(text: Any, prefix: str) -> None:
    if text is None:
        return
    if not isinstance(text, dict):
        raise LocalApiError(f"{prefix}text: expected an object", param=f"{prefix}text")
    fmt = text.get("format")
    if fmt is not None and not (isinstance(fmt, dict) and fmt.get("type") == "text"):
        raise LocalApiError(
            f"{prefix}text.format: only text is supported", param=f"{prefix}text.format"
        )
    if text.get("verbosity") not in (None, "medium"):
        raise LocalApiError(
            f"{prefix}text.verbosity: the CLIs do not take a verbosity setting",
            param=f"{prefix}text.verbosity",
        )


def _check_reasoning(reasoning: Any, adapter: str, prefix: str) -> str | None:
    if reasoning is None:
        return None
    if not isinstance(reasoning, dict):
        raise LocalApiError(f"{prefix}reasoning: expected an object", param=f"{prefix}reasoning")
    if reasoning.get("summary") is not None:
        raise LocalApiError(
            f"{prefix}reasoning.summary: summaries cannot be requested from the CLI",
            param=f"{prefix}reasoning.summary",
        )
    effort = reasoning.get("effort")
    if effort is None:
        return None
    if adapter != "codex":
        raise LocalApiError(
            f"{prefix}reasoning.effort: {adapter} has no reasoning effort setting",
            param=f"{prefix}reasoning.effort",
        )
    if effort not in ("none", "minimal", "low", "medium", "high", "xhigh"):
        raise LocalApiError(
            f"{prefix}reasoning.effort: must be none|minimal|low|medium|high|xhigh",
            param=f"{prefix}reasoning.effort",
        )
    return str(effort)


def spec_from_fields(
    *,
    name: str,
    adapter: str,
    workspace: str,
    instructions: str | None,
    model: str | None,
    tools: list[McpTool],
    reasoning_effort: str | None,
    env: Mapping[str, str] | None = None,
) -> AgentSpec:
    """An :class:`AgentSpec` for one session or response."""
    data: dict[str, Any] = {
        "name": name,
        "runtime": adapter,
        "workspace": {"path": workspace},
        "mcp_servers": {
            t.label: {"url": t.url, **({"headers": dict(t.headers)} if t.headers else {})}
            for t in tools
        },
    }
    if instructions:
        data["instructions"] = instructions
    if model and default_adapters().resolve_name(model) is None:
        data["model"] = model
    if reasoning_effort:
        data["reasoning_effort"] = reasoning_effort
    if env:
        data["env"] = dict(env)
    return AgentSpec.from_dict(data)


# ---------------------------------------------------------------------- #
# Wire object
# ---------------------------------------------------------------------- #


def tools_of(record: Record) -> list[McpTool]:
    """The MCP tools stored on a definition."""
    return list(record.private.get("tools") or [])


def definition_object(record: Record) -> dict[str, Any]:
    """The ``agent`` object. Header values are masked."""
    d = record.data
    return {
        "id": record.id,
        "object": "agent",
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "name": d.get("name"),
        "model": d["model"],
        "instructions": d.get("instructions"),
        "metadata": dict(d.get("metadata") or {}),
        "multi_agent": {"enabled": False, "max_concurrent_subagents": None},
        "reasoning": {"effort": d.get("reasoning_effort"), "summary": None},
        "service_tier": "default",
        "text": {"format": {"type": "text"}, "verbosity": "medium"},
        "tools": [t.wire() for t in tools_of(record)],
        "x_easy_sandbox": label(
            "update_in_place",
            "snapshot_at_session_start",
            compute="local_state",
            runtime=d["adapter"],
        ),
    }


# ---------------------------------------------------------------------- #
# Handlers
# ---------------------------------------------------------------------- #


def _not_found(agent_id: str) -> ServerResponse:
    return err(404, f"agent {agent_id!r} not found", code="resource_not_found", param="agent_id")


def handle_definitions_create(request: ServerRequest) -> ServerResponse:
    """``POST /v1/agents`` (A-01)."""
    body = body_of(request)
    selected = select_or_response(request, body)
    if isinstance(selected, ServerResponse):
        return selected
    fields = parse_agent_fields(body, selected, create=True)
    state = get_state()
    owner = principal_of(request)
    record = state.definitions.create(
        owner,
        {
            "adapter": selected,
            "model": fields["model"],
            "name": fields.get("name"),
            "instructions": fields.get("instructions"),
            "metadata": fields.get("metadata") or {},
            "reasoning_effort": fields.get("reasoning_effort"),
        },
        {"tools": fields.get("tools") or []},
    )
    return ServerResponse.ok(definition_object(record))


def handle_definitions_get(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/{agent_id}`` (A-02)."""
    agent_id = request.path_params["agent_id"]
    record = get_state().definitions.get(principal_of(request), agent_id)
    if record is None:
        return _not_found(agent_id)
    return ServerResponse.ok(definition_object(record))


def handle_definitions_update(request: ServerRequest) -> ServerResponse:
    """``POST /v1/agents/{agent_id}`` (A-03): in place, omitted fields stay unchanged."""
    agent_id = request.path_params["agent_id"]
    record = get_state().definitions.get(principal_of(request), agent_id)
    if record is None:
        return _not_found(agent_id)
    body = body_of(request)
    if "adapter" in body or "runtime" in body:
        raise LocalApiError("adapter: a definition cannot change runtime", param="adapter")
    fields = parse_agent_fields(body, record.data["adapter"], create=False)
    for key in ("model", "name", "instructions", "metadata", "reasoning_effort"):
        if key in fields:
            record.data[key] = fields[key]
    if "tools" in fields:
        record.private["tools"] = fields["tools"]
    get_state().definitions.touch(record)
    return ServerResponse.ok(definition_object(record))


def handle_definitions_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents`` (A-04)."""
    rows = get_state().definitions.list(principal_of(request))
    return page([definition_object(r) for r in rows], request.query)


def handle_definitions_delete(request: ServerRequest) -> ServerResponse:
    """``DELETE /v1/agents/{agent_id}`` (A-05): sessions keep the snapshot they started with."""
    agent_id = request.path_params["agent_id"]
    record = get_state().definitions.delete(principal_of(request), agent_id)
    if record is None:
        return _not_found(agent_id)
    return ServerResponse.ok(
        {
            "id": agent_id,
            "object": "agent.deleted",
            "deleted": True,
            "x_easy_sandbox": label(
                "snapshot_at_session_start", compute="local_state", runtime=record.data["adapter"]
            ),
        }
    )
