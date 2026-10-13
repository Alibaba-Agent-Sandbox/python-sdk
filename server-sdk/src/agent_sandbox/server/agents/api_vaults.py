"""Memory-only vaults and write-only credentials (A-38..A-47).

A vault holds ``static_bearer`` and access-token ``mcp_oauth`` credentials. At each turn a
credential is injected into the MCP server of the session whose URL has the same scheme,
host and port, through the child-environment carrier (never argv). Secrets are never
returned: no value, prefix, length or hash. They are lost on restart.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from ..types import ServerRequest, ServerResponse
from .api_common import (
    body_of,
    err,
    label,
    metadata_strict,
    page,
    principal_of,
    url_check,
)
from .config import McpServerSpec
from .errors import LocalApiError
from .local_state import Record, SessionMeta, get_state

if TYPE_CHECKING:
    from .api_definitions import McpTool
    from .config import AgentSpec

__all__ = [
    "bind_credentials",
    "credential_object",
    "handle_credentials_create",
    "handle_credentials_delete",
    "handle_credentials_get",
    "handle_credentials_list",
    "handle_credentials_update",
    "handle_vaults_create",
    "handle_vaults_delete",
    "handle_vaults_get",
    "handle_vaults_list",
    "handle_vaults_update",
    "turn_mcp_servers",
    "vault_object",
]

_NAME_MAX_BYTES = 256
_TOKEN_MAX = 8192


def _vault_label() -> dict[str, Any]:
    return label("memory_only", compute="local_state")


def _credential_label() -> dict[str, Any]:
    return label("memory_only", "secret_in_agent_env", compute="local_state")


def vault_object(record: Record) -> dict[str, Any]:
    """``id``, ``name``, ``metadata``, ``created_at`` only."""
    return {
        "id": record.id,
        "object": "vault",
        "created_at": record.created_at,
        "metadata": dict(record.data.get("metadata") or {}),
        "name": record.data.get("name"),
        "x_agent_sandbox": _vault_label(),
    }


def credential_object(record: Record) -> dict[str, Any]:
    """Metadata only: no field is derived from the secret."""
    return {
        "id": record.id,
        "object": "vault.credential",
        "vault_id": record.data["vault_id"],
        "name": record.data["name"],
        "metadata": dict(record.data.get("metadata") or {}),
        "auth": dict(record.data["auth"]),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "x_agent_sandbox": _credential_label(),
    }


def _name(value: Any, field: str = "name", *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise LocalApiError(f"{field}: required", param=field)
        return None
    if not isinstance(value, str):
        raise LocalApiError(f"{field}: expected a string", param=field)
    trimmed = value.strip()
    if not trimmed or len(trimmed.encode("utf-8")) > _NAME_MAX_BYTES:
        raise LocalApiError(
            f"{field}: 1 to {_NAME_MAX_BYTES} UTF-8 bytes after trimming", param=field
        )
    return trimmed


def _filters(query: dict[str, list[str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, values in query.items():
        if key.startswith("metadata[") and key.endswith("]") and values:
            out[key[9:-1]] = values[0]
    return out


def _matches(record: Record, query: dict[str, list[str]]) -> bool:
    status = [v for k, vs in query.items() if k in ("status", "status[]") for v in vs]
    if status and "active" not in status:
        return False
    meta = record.data.get("metadata") or {}
    return all(meta.get(k) == v for k, v in _filters(query).items())


def _vault_missing(vault_id: str) -> ServerResponse:
    return err(404, f"vault {vault_id!r} not found", code="resource_not_found", param="vault_id")


def _credential_missing(credential_id: str) -> ServerResponse:
    return err(
        404,
        f"credential {credential_id!r} not found",
        code="resource_not_found",
        param="credential_id",
    )


# ---------------------------------------------------------------------- #
# Vaults
# ---------------------------------------------------------------------- #


def handle_vaults_create(request: ServerRequest) -> ServerResponse:
    """``POST /v1/vaults`` (A-38)."""
    body = body_of(request)
    for key in body:
        if key not in ("name", "metadata"):
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    owner = principal_of(request)
    state = get_state()
    if state.vaults.full(owner):
        raise LocalApiError("too many vaults", param="name", code="agents.limit_exceeded")
    record = state.vaults.create(
        owner,
        {"name": _name(body.get("name")), "metadata": metadata_strict(body.get("metadata"))},
    )
    return ServerResponse.ok(vault_object(record))


def handle_vaults_get(request: ServerRequest) -> ServerResponse:
    """``GET /v1/vaults/{vault_id}`` (A-39)."""
    vault_id = request.path_params["vault_id"]
    record = get_state().vaults.get(principal_of(request), vault_id)
    return ServerResponse.ok(vault_object(record)) if record else _vault_missing(vault_id)


def handle_vaults_update(request: ServerRequest) -> ServerResponse:
    """``POST /v1/vaults/{vault_id}`` (A-40): name and metadata only."""
    vault_id = request.path_params["vault_id"]
    record = get_state().vaults.get(principal_of(request), vault_id)
    if record is None:
        return _vault_missing(vault_id)
    body = body_of(request)
    for key in body:
        if key not in ("name", "metadata"):
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    if "name" in body:
        record.data["name"] = _name(body["name"])
    if "metadata" in body:
        record.data["metadata"] = metadata_strict(body["metadata"])
    get_state().vaults.touch(record)
    return ServerResponse.ok(vault_object(record))


def handle_vaults_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/vaults`` (A-41)."""
    rows = [r for r in get_state().vaults.list(principal_of(request)) if _matches(r, request.query)]
    return page([vault_object(r) for r in rows], request.query)


def handle_vaults_delete(request: ServerRequest) -> ServerResponse:
    """``DELETE /v1/vaults/{vault_id}`` (A-42): the vault and every credential in it."""
    vault_id = request.path_params["vault_id"]
    owner = principal_of(request)
    state = get_state()
    if state.vaults.delete(owner, vault_id) is None:
        return _vault_missing(vault_id)
    for cred in state.credentials.list(owner):
        if cred.data["vault_id"] == vault_id:
            state.credentials.delete(owner, cred.id)
    return ServerResponse.ok(
        {
            "id": vault_id,
            "object": "vault.deleted",
            "deleted": True,
            "x_agent_sandbox": _vault_label(),
        }
    )


# ---------------------------------------------------------------------- #
# Credentials
# ---------------------------------------------------------------------- #


def _secret(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _TOKEN_MAX
        or any(ch in value for ch in "\r\n\x00")
    ):
        raise LocalApiError(f"{field}: expected a non-empty single-line string", param=field)
    return value


def _expires(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LocalApiError(f"{field}: expected an RFC 3339 timestamp", param=field)
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise LocalApiError(f"{field}: expected an RFC 3339 timestamp", param=field) from None
    return value


def _check_networking(auth: dict[str, Any], url: str) -> dict[str, Any] | None:
    net = auth.get("networking")
    if net is None:
        return None
    host = url_check(url, "auth.mcp_server_url")[1]
    if not isinstance(net, dict) or net.get("type") != "limited":
        raise LocalApiError(
            "auth.networking: unrestricted needs a hosted network policy; use limited",
            param="auth.networking",
        )
    hosts = net.get("allowed_hosts")
    if (
        not isinstance(hosts, list)
        or not hosts
        or any(not isinstance(h, str) or h.lower() != host for h in hosts)
    ):
        raise LocalApiError(
            "auth.networking.allowed_hosts: only the credential's own URL host is enforceable",
            param="auth.networking.allowed_hosts",
        )
    return {"type": "limited", "allowed_hosts": [host]}


def _parse_auth_create(auth: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(auth, dict):
        raise LocalApiError("auth: required", param="auth")
    kind = auth.get("type")
    if kind == "environment_variable":
        raise LocalApiError(
            "auth.type environment_variable needs an egress proxy; the only local delivery "
            "would hand the secret to code the agent runs",
            param="auth.type",
        )
    if kind not in ("static_bearer", "mcp_oauth"):
        raise LocalApiError("auth.type: must be static_bearer or mcp_oauth", param="auth.type")
    allowed = {"type", "mcp_server_url", "networking"} | (
        {"token"} if kind == "static_bearer" else {"access_token", "expires_at", "refresh"}
    )
    for key in auth:
        if key not in allowed:
            raise LocalApiError(
                f"auth.{key}: unknown or unsupported parameter", param=f"auth.{key}"
            )
    if kind == "mcp_oauth" and auth.get("refresh") is not None:
        raise LocalApiError(
            "auth.refresh: there is no refresh broker; sending a refresh token to a "
            "caller-chosen endpoint would move it off the machine",
            param="auth.refresh",
        )
    url = auth.get("mcp_server_url")
    url_check(url, "auth.mcp_server_url")
    public: dict[str, Any] = {"type": kind, "mcp_server_url": url}
    networking = _check_networking(auth, str(url))
    if networking:
        public["networking"] = networking
    if kind == "static_bearer":
        return public, {"token": _secret(auth.get("token"), "auth.token")}
    public["expires_at"] = _expires(auth.get("expires_at"), "auth.expires_at")
    public["refresh"] = None
    return public, {"token": _secret(auth.get("access_token"), "auth.access_token")}


def _vault_for(request: ServerRequest) -> Record | ServerResponse:
    vault_id = request.path_params["vault_id"]
    record = get_state().vaults.get(principal_of(request), vault_id)
    return record if record is not None else _vault_missing(vault_id)


def _credential_for(request: ServerRequest, vault: Record) -> Record | ServerResponse:
    credential_id = request.path_params["credential_id"]
    record = get_state().credentials.get(principal_of(request), credential_id)
    if record is None or record.data["vault_id"] != vault.id:
        return _credential_missing(credential_id)
    return record


def handle_credentials_create(request: ServerRequest) -> ServerResponse:
    """``POST /v1/vaults/{vault_id}/credentials`` (A-43)."""
    vault = _vault_for(request)
    if isinstance(vault, ServerResponse):
        return vault
    body = body_of(request)
    for key in body:
        if key not in ("auth", "name", "metadata"):
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    name = _name(body.get("name"), required=True)
    metadata = metadata_strict(body.get("metadata"))
    public, private = _parse_auth_create(body.get("auth"))
    record = get_state().credentials.create(
        principal_of(request),
        {"vault_id": vault.id, "name": name, "metadata": metadata, "auth": public},
        private,
    )
    return ServerResponse.ok(credential_object(record))


def handle_credentials_get(request: ServerRequest) -> ServerResponse:
    """``GET /v1/vaults/{vault_id}/credentials/{credential_id}`` (A-44)."""
    vault = _vault_for(request)
    if isinstance(vault, ServerResponse):
        return vault
    record = _credential_for(request, vault)
    if isinstance(record, ServerResponse):
        return record
    return ServerResponse.ok(credential_object(record))


def handle_credentials_update(request: ServerRequest) -> ServerResponse:
    """``POST /v1/vaults/{vault_id}/credentials/{credential_id}`` (A-45): rotate or relabel."""
    vault = _vault_for(request)
    if isinstance(vault, ServerResponse):
        return vault
    record = _credential_for(request, vault)
    if isinstance(record, ServerResponse):
        return record
    body = body_of(request)
    for key in body:
        if key not in ("auth", "metadata"):
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    new_metadata = metadata_strict(body["metadata"]) if "metadata" in body else None
    new_token: str | None = None
    new_expiry: tuple[str | None] | None = None
    auth = body.get("auth")
    if auth is not None:
        kind = record.data["auth"]["type"]
        if not isinstance(auth, dict) or auth.get("type") != kind:
            raise LocalApiError(
                f"auth.type: must stay {kind}; the type of a credential cannot change",
                param="auth.type",
            )
        allowed = (
            {"type", "token"}
            if kind == "static_bearer"
            else {
                "type",
                "access_token",
                "expires_at",
                "refresh",
            }
        )
        for key in auth:
            if key not in allowed:
                raise LocalApiError(
                    f"auth.{key}: unknown or unsupported parameter", param=f"auth.{key}"
                )
        if kind == "static_bearer":
            new_token = _secret(auth.get("token"), "auth.token")
        else:
            if auth.get("refresh") is not None:
                raise LocalApiError(
                    "auth.refresh: there is no refresh broker", param="auth.refresh"
                )
            if auth.get("access_token") is not None:
                new_token = _secret(auth["access_token"], "auth.access_token")
            if "expires_at" in auth:
                new_expiry = (_expires(auth["expires_at"], "auth.expires_at"),)
            elif new_token is not None:
                new_expiry = (None,)
    if new_metadata is not None:
        record.data["metadata"] = new_metadata
    if new_token is not None:
        record.private["token"] = new_token
    if new_expiry is not None:
        record.data["auth"]["expires_at"] = new_expiry[0]
    get_state().credentials.touch(record)
    return ServerResponse.ok(credential_object(record))


def handle_credentials_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/vaults/{vault_id}/credentials`` (A-46)."""
    vault = _vault_for(request)
    if isinstance(vault, ServerResponse):
        return vault
    rows = [
        r
        for r in get_state().credentials.list(principal_of(request))
        if r.data["vault_id"] == vault.id and _matches(r, request.query)
    ]
    return page([credential_object(r) for r in rows], request.query)


def handle_credentials_delete(request: ServerRequest) -> ServerResponse:
    """``DELETE /v1/vaults/{vault_id}/credentials/{credential_id}`` (A-47)."""
    vault = _vault_for(request)
    if isinstance(vault, ServerResponse):
        return vault
    record = _credential_for(request, vault)
    if isinstance(record, ServerResponse):
        return record
    get_state().credentials.delete(principal_of(request), record.id)
    return ServerResponse.ok(
        {
            "id": record.id,
            "object": "vault.credential.deleted",
            "deleted": True,
            "x_agent_sandbox": _credential_label(),
        }
    )


# ---------------------------------------------------------------------- #
# Injection
# ---------------------------------------------------------------------- #


def _origin(url: str) -> tuple[str, str, int] | None:
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    if not parts.hostname or parts.scheme not in ("http", "https"):
        return None
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return None
    return parts.scheme, parts.hostname.lower(), port


def bind_credentials(
    owner: str, vault_ids: list[str], tools: list[McpTool]
) -> list[dict[str, str]]:
    """Match each MCP tool to at most one credential of the attached vaults.

    A credential matches a tool only when scheme, host and port are equal. An explicit
    ``credential_id`` that does not belong to an attached vault, or whose URL does not
    match, is a 400; two matching credentials without an explicit id are ambiguous.
    """
    state = get_state()
    creds = [c for c in state.credentials.list(owner) if c.data["vault_id"] in set(vault_ids)]
    bindings: list[dict[str, str]] = []
    for i, tool in enumerate(tools):
        tool_origin = _origin(tool.url)
        if tool.credential_id:
            chosen = next((c for c in creds if c.id == tool.credential_id), None)
            if chosen is None:
                raise LocalApiError(
                    "credential_id does not belong to an attached vault",
                    param=f"tools[{i}].credential_id",
                    code="agents.credential_not_found",
                )
            if _origin(chosen.data["auth"]["mcp_server_url"]) != tool_origin:
                raise LocalApiError(
                    "the credential's mcp_server_url does not match the MCP server URL",
                    param=f"tools[{i}].credential_id",
                    code="agents.credential_mismatch",
                )
            matches = [chosen]
        else:
            matches = [c for c in creds if _origin(c.data["auth"]["mcp_server_url"]) == tool_origin]
        if len(matches) > 1:
            raise LocalApiError(
                "more than one attached credential matches this MCP server; set credential_id",
                param=f"tools[{i}].credential_id",
                code="agents.credential_ambiguous",
            )
        if matches:
            bindings.append(
                {
                    "tool": tool.label,
                    "vault_id": matches[0].data["vault_id"],
                    "credential_id": matches[0].id,
                }
            )
    return bindings


def turn_mcp_servers(
    owner: str, meta: SessionMeta | None, spec: AgentSpec | None
) -> dict[str, McpServerSpec]:
    """Per-turn MCP servers with the vault credential in an ``Authorization`` header.

    The value travels in the child environment only. A credential or vault deleted since
    the session was created fails the turn explicitly instead of running unauthenticated.
    """
    if meta is None or not meta.bindings:
        return {}
    state = get_state()
    out: dict[str, McpServerSpec] = {}
    for binding in meta.bindings:
        vault = state.vaults.get(owner, binding["vault_id"])
        cred = state.credentials.get(owner, binding["credential_id"])
        if vault is None or cred is None or cred.data["vault_id"] != vault.id:
            raise LocalApiError(
                f"the credential for MCP server {binding['tool']!r} is no longer available",
                param="vault_ids",
                code="agents.credential_unavailable",
            )
        expires = cred.data["auth"].get("expires_at")
        if expires:
            when = dt.datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=dt.timezone.utc)
            if when <= dt.datetime.now(dt.timezone.utc):
                raise LocalApiError(
                    f"the access token for MCP server {binding['tool']!r} has expired",
                    param="vault_ids",
                    code="agents.credential_expired",
                )
        base = spec.mcp_servers.get(binding["tool"]) if spec else None
        if base is None:
            continue
        headers = dict(base.headers)
        headers["Authorization"] = "Bearer " + str(cred.private["token"])
        out[base.name] = McpServerSpec(
            name=base.name, url=base.url, headers=headers, transport=base.transport
        )
    return out
