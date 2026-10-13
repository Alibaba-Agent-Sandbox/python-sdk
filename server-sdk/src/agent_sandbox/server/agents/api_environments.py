"""Environments, environment files, reduced templates and the local blob store.

A-06..A-08  an environment is a directory binding (``type: self_hosted``); nothing is
            provisioned. ``env`` and inline files are applied when it is created.
A-09, A-10  files are written under the environment's workspace directory and are never
            overwritten; listings read regular files only.
A-11..A-15  a template is ``{name, env, files}`` and nothing else. Fields that need a
            hosted environment (network, packages, setup commands, plugins, skills,
            desktop, capability directories) are 400.
O-03        ``POST /v1/files`` keeps ``purpose=user_data`` blobs in memory so ``file_id``
            works for environment and template files.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from typing import Any

from ..types import ServerRequest, ServerResponse
from .api_common import (
    body_of,
    check_env_map,
    decode_base64,
    err,
    first,
    label,
    page,
    principal_of,
)
from .errors import LocalApiError
from .local_state import Record, get_state
from .workspace_files import (
    check_workspace_root,
    list_files,
    normalize_relative,
    refused_location,
    write_new_file,
)

__all__ = [
    "environment_object",
    "handle_blobs_create",
    "handle_environment_files_create",
    "handle_environment_files_list",
    "handle_environments_create",
    "handle_environments_get",
    "handle_environments_list",
    "handle_templates_create",
    "handle_templates_delete",
    "handle_templates_get",
    "handle_templates_list",
    "handle_templates_update",
]

_HOSTED_ONLY = (
    "network",
    "packages",
    "setup_commands",
    "plugins",
    "skills",
    "desktop",
    "container_size",
    "capability_directories",
)
_DEFAULT_MAX_FILE = 10 * 1024 * 1024
_MAX_FILES = 100
_MAX_OWNER_BLOB_BYTES = 256 * 1024 * 1024


def _max_file_bytes() -> int:
    try:
        value = int(os.environ.get("ABX_AGENTS_MAX_FILE_BYTES", ""))
    except ValueError:
        return _DEFAULT_MAX_FILE
    return value if value > 0 else _DEFAULT_MAX_FILE


def admit_path(request: ServerRequest, path: str, op: str) -> None:
    """Run the active policy's path guard on *path* (a no-op without a policy)."""
    ctx = request.context.get("policy")
    resolve = getattr(ctx, "resolve_path", None)
    if resolve is not None:
        resolve(path, op, field="path")


def _env_not_found(environment_id: str) -> ServerResponse:
    return err(
        404,
        f"environment {environment_id!r} not found",
        code="resource_not_found",
        param="environment_id",
    )


def _refuse_hosted_fields(src: dict[str, Any], prefix: str) -> None:
    for key in _HOSTED_ONLY:
        value = src.get(key)
        if value in (None, [], {}):
            continue
        if key == "desktop" and isinstance(value, dict) and not value.get("enabled"):
            continue
        raise LocalApiError(
            f"{prefix}{key}: needs a hosted environment and is not available locally",
            param=f"{prefix}{key}",
        )


# ---------------------------------------------------------------------- #
# Files (inline bytes or a local blob)
# ---------------------------------------------------------------------- #


def _parse_file(raw: Any, field: str, owner: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise LocalApiError(f"{field}: expected an object", param=field)
    kind = raw.get("type")
    rel = normalize_relative(raw.get("path"), f"{field}.path")
    if not rel:
        raise LocalApiError(f"{field}.path: names the workspace directory itself", param=field)
    why = refused_location(rel)
    if why:
        raise LocalApiError(
            f"{field}.path: {why}", param=f"{field}.path", code="agents.path_refused"
        )
    limit = _max_file_bytes()
    if kind == "inline":
        data = decode_base64(raw.get("data"), f"{field}.data", limit=limit)
        return {"type": "inline", "rel": rel, "data": data}
    if kind == "file_id":
        file_id = raw.get("file_id")
        blob = get_state().blobs.get(owner, file_id) if isinstance(file_id, str) else None
        if blob is None:
            raise LocalApiError(
                f"{field}.file_id: this server did not mint that file id; upload it with "
                "POST /v1/files and purpose=user_data",
                param=f"{field}.file_id",
                code="agents.file_not_found",
            )
        return {"type": "file_id", "rel": rel, "data": blob.private["data"], "file_id": file_id}
    raise LocalApiError(f"{field}.type: must be inline or file_id", param=f"{field}.type")


def _parse_files(raw: Any, field: str, owner: str) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > _MAX_FILES:
        raise LocalApiError(f"{field}: expected a list of up to {_MAX_FILES} files", param=field)
    return [_parse_file(item, f"{field}[{i}]", owner) for i, item in enumerate(raw)]


def _file_wire(item: dict[str, Any]) -> dict[str, Any]:
    path = "/workspace/" + item["rel"]
    if item["type"] == "file_id":
        return {"type": "file_id", "file_id": item["file_id"], "path": path}
    return {"type": "inline", "path": path, "size_bytes": len(item["data"])}


def _install(root: str, files: list[dict[str, Any]], request: ServerRequest) -> list[str]:
    created: list[str] = []
    try:
        for item in files:
            admit_path(request, os.path.join(root, item["rel"]), "write")
            if write_new_file(root, item["rel"], item["data"]):
                created.append(os.path.join(root, item["rel"]))
    except Exception:
        for path in created:
            with contextlib.suppress(OSError):
                os.unlink(path)
        raise
    return created


# ---------------------------------------------------------------------- #
# O-03 local blob store
# ---------------------------------------------------------------------- #


def handle_blobs_create(request: ServerRequest) -> ServerResponse:
    """``POST /v1/files`` (O-03): ``purpose=user_data`` bytes kept in server memory.

    The file is base64 in ``data`` (or ``file``) of a JSON body, or raw ``bytes`` in ``file``
    when the dispatcher parsed a ``multipart/form-data`` upload; ``filename`` is optional.
    """
    body = body_of(request)
    for key in body:
        if key not in ("purpose", "filename", "data", "file"):
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    if body.get("purpose") != "user_data":
        raise LocalApiError("purpose: only user_data is supported", param="purpose")
    raw = body.get("data", body.get("file"))
    if isinstance(raw, bytes):
        if len(raw) > _max_file_bytes():
            raise LocalApiError(
                f"file: larger than {_max_file_bytes()} bytes",
                param="file",
                code="agents.file_too_large",
            )
        data = raw
    else:
        data = decode_base64(raw, "data", limit=_max_file_bytes())
    filename = body.get("filename")
    if filename is not None and (not isinstance(filename, str) or len(filename) > 255):
        raise LocalApiError("filename: expected a string up to 255 characters", param="filename")
    owner = principal_of(request)
    state = get_state()
    used = sum(len(b.private["data"]) for b in state.blobs.list(owner))
    if used + len(data) > _MAX_OWNER_BLOB_BYTES:
        raise LocalApiError("blob storage is full", param="data", code="agents.limit_exceeded")
    record = state.blobs.create(
        owner,
        {"filename": filename or "upload", "bytes": len(data)},
        {"data": data},
    )
    return ServerResponse.ok(
        {
            "id": record.id,
            "object": "file",
            "bytes": len(data),
            "created_at": record.created_at,
            "filename": record.data["filename"],
            "purpose": "user_data",
            "status": "processed",
            "expires_at": None,
            "x_agent_sandbox": label("local_blob", compute="local_state"),
        }
    )


# ---------------------------------------------------------------------- #
# Environments
# ---------------------------------------------------------------------- #


def environment_object(record: Record) -> dict[str, Any]:
    """``agent.environment`` for a directory binding. Env values are never returned."""
    d = record.data
    differences = ["local_workspace", "nothing_provisioned"]
    if d.get("converted"):
        differences.append("hosted_request_converted")
    return {
        "id": record.id,
        "object": "agent.environment",
        "type": "self_hosted",
        "status": "ready",
        "files": list(d["files"]),
        "plugins": [],
        "skills": [],
        "capability_directories": [],
        "workspace_directory": d["workspace_directory"],
        "vault_ids": list(d["vault_ids"]),
        "created_at": record.created_at,
        "x_agent_sandbox": label(*differences, compute="local_state"),
    }


def _owned_vault_ids(owner: str, raw: Any, field: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw) or len(raw) > 16:
        raise LocalApiError(f"{field}: expected up to 16 vault ids", param=field)
    state = get_state()
    for i, vault_id in enumerate(raw):
        if state.vaults.get(owner, vault_id) is None:
            raise LocalApiError(
                f"vault {vault_id!r} not found",
                param=f"{field}[{i}]",
                code="resource_not_found",
                status=404,
            )
    return list(dict.fromkeys(raw))


def handle_environments_create(request: ServerRequest) -> ServerResponse:
    """``POST /v1/agents/environments`` (A-06)."""
    body = body_of(request)
    for key in body:
        if key not in ("environment", "vault_ids"):
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    env = body.get("environment")
    if not isinstance(env, dict):
        raise LocalApiError("environment: required", param="environment")
    owner = principal_of(request)
    state = get_state()
    kind = env.get("type") or "self_hosted"
    configured = {k: v for k, v in env.items() if k != "type" and v not in (None, [], {})}
    converted = False
    if kind == "openai_hosted":
        if configured:
            raise LocalApiError(
                "environment.type: a configured openai_hosted environment cannot be provisioned "
                "locally; send an empty request or type self_hosted",
                param="environment.type",
            )
        converted = True
    elif kind != "self_hosted":
        raise LocalApiError(
            "environment.type: must be openai_hosted (empty) or self_hosted",
            param="environment.type",
        )
    allowed = {"type", "workspace_directory", "env", "files", "environment_template_id"}
    _refuse_hosted_fields(env, "environment.")
    for key in env:
        if key not in allowed and key not in _HOSTED_ONLY:
            raise LocalApiError(
                f"environment.{key}: unknown or unsupported parameter", param=f"environment.{key}"
            )
    template: Record | None = None
    template_id = env.get("environment_template_id")
    if template_id is not None:
        template = state.templates.get(owner, template_id) if isinstance(template_id, str) else None
        if template is None:
            raise LocalApiError(
                f"environment template {template_id!r} not found",
                param="environment.environment_template_id",
                code="resource_not_found",
                status=404,
            )
    raw_dir = env.get("workspace_directory") or "/workspace"
    workspace = raw_dir.strip() if isinstance(raw_dir, str) else raw_dir
    root = check_workspace_root(workspace)
    merged_env = dict(template.private["env"]) if template else {}
    merged_env.update(check_env_map(env.get("env"), "environment.env"))
    files = list(template.private["files"]) if template else []
    files += _parse_files(env.get("files"), "environment.files", owner)
    vault_ids = _owned_vault_ids(owner, body.get("vault_ids"), "vault_ids")
    _install(root, files, request)
    listing = [
        {
            "id": "envfile_" + hashlib.sha1(f["rel"].encode()).hexdigest()[:20],  # noqa: S324
            "type": "inline",
            "path": "/workspace/" + f["rel"],
            "size_bytes": len(f["data"]),
        }
        for f in files
    ]
    record = state.environments.create(
        owner,
        {
            "workspace_directory": workspace,
            "files": listing,
            "vault_ids": vault_ids,
            "converted": converted,
        },
        {"env": merged_env, "root": root},
    )
    return ServerResponse.ok(environment_object(record))


def handle_environments_get(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/environments/{environment_id}`` (A-07)."""
    environment_id = request.path_params["environment_id"]
    record = get_state().environments.get(principal_of(request), environment_id)
    if record is None:
        return _env_not_found(environment_id)
    return ServerResponse.ok(environment_object(record))


def handle_environments_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/environments`` (A-08)."""
    wanted = first(request.query, "type")
    rows = get_state().environments.list(principal_of(request))
    if wanted not in (None, "self_hosted"):
        rows = []
    return page([environment_object(r) for r in rows], request.query)


# ---------------------------------------------------------------------- #
# Environment files
# ---------------------------------------------------------------------- #


def handle_environment_files_create(request: ServerRequest) -> ServerResponse:
    """``POST /v1/agents/environments/{environment_id}/files`` (A-09)."""
    environment_id = request.path_params["environment_id"]
    owner = principal_of(request)
    record = get_state().environments.get(owner, environment_id)
    if record is None:
        return _env_not_found(environment_id)
    body = body_of(request)
    for key in body:
        if key not in ("type", "data", "file_id", "path"):
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    item = _parse_file(body, "file", owner)
    root = record.private["root"]
    admit_path(request, os.path.join(root, item["rel"]), "write")
    write_new_file(root, item["rel"], item["data"])
    return ServerResponse.ok(
        {
            "object": "agent.environment.file",
            "environment_id": environment_id,
            "path": "/workspace/" + item["rel"],
            "size_bytes": len(item["data"]),
            "x_agent_sandbox": label("local_workspace", "no_overwrite", compute="local_state"),
        }
    )


def handle_environment_files_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/environments/{environment_id}/files`` (A-10)."""
    environment_id = request.path_params["environment_id"]
    record = get_state().environments.get(principal_of(request), environment_id)
    if record is None:
        return _env_not_found(environment_id)
    query = request.query
    prefix = ""
    raw_path = first(query, "path")
    if raw_path is not None:
        prefix = normalize_relative(raw_path, "path")
    limit = 20
    raw_limit = first(query, "limit")
    if raw_limit is not None:
        if not raw_limit.isdigit() or not 1 <= int(raw_limit) <= 100:
            raise LocalApiError("limit: must be between 1 and 100", param="limit")
        limit = int(raw_limit)
    order = first(query, "order") or "desc"
    if order not in ("asc", "desc"):
        raise LocalApiError("order: must be asc or desc", param="order")
    offset = 0
    token = first(query, "page")
    if token is not None:
        if not (token.startswith("o") and token[1:].isdigit()):
            raise LocalApiError("page: not a token this server issued", param="page")
        offset = int(token[1:])
    root = record.private["root"]
    admit_path(request, os.path.join(root, prefix) if prefix else root, "read")
    rows = list_files(root, prefix)
    if order == "desc":
        rows.reverse()
    chunk = rows[offset : offset + limit]
    more = offset + limit < len(rows)
    data = [
        {
            "object": "agent.environment.file",
            "environment_id": environment_id,
            "path": "/workspace/" + rel,
            "size_bytes": size,
        }
        for rel, size in chunk
    ]
    return ServerResponse.ok(
        {
            "object": "list",
            "data": data,
            "has_more": more,
            "next": f"o{offset + limit}" if more else None,
            "x_agent_sandbox": label("local_workspace", compute="local_state"),
        }
    )


# ---------------------------------------------------------------------- #
# Reduced templates
# ---------------------------------------------------------------------- #


def _template_label() -> dict[str, Any]:
    return label("not_hosted_template", "applies_env_and_files_only", compute="local_state")


def template_object(record: Record) -> dict[str, Any]:
    """Template without env values or file bodies (``size_bytes`` only)."""
    return {
        "id": record.id,
        "object": "agent.environment.template",
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "name": record.data.get("name"),
        "files": [_file_wire(f) for f in record.private["files"]],
        "capability_directories": [],
        "network": {"access": "enabled", "allowed_domains": []},
        "packages": {"npm": [], "python": [], "system": []},
        "plugins": [],
        "skills": [],
        "desktop": None,
        "x_agent_sandbox": _template_label(),
    }


def _parse_template(body: dict[str, Any], owner: str, *, create: bool) -> dict[str, Any]:
    allowed = {"name", "env", "files", *_HOSTED_ONLY}
    for key in body:
        if key not in allowed:
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    _refuse_hosted_fields(body, "")
    out: dict[str, Any] = {}
    if "name" in body:
        name = body["name"]
        if name is not None and (not isinstance(name, str) or len(name) > 256):
            raise LocalApiError("name: expected a string up to 256 characters", param="name")
        out["name"] = name
    if "env" in body or create:
        out["env"] = check_env_map(body.get("env"), "env")
    if "files" in body or create:
        out["files"] = _parse_files(body.get("files"), "files", owner)
    return out


def _template_not_found(template_id: str) -> ServerResponse:
    return err(
        404,
        f"environment template {template_id!r} not found",
        code="resource_not_found",
        param="environment_template_id",
    )


def handle_templates_create(request: ServerRequest) -> ServerResponse:
    """``POST /v1/agents/environments/templates`` (A-11)."""
    owner = principal_of(request)
    fields = _parse_template(body_of(request), owner, create=True)
    record = get_state().templates.create(
        owner,
        {"name": fields.get("name")},
        {"env": fields["env"], "files": fields["files"]},
    )
    return ServerResponse.ok(template_object(record))


def handle_templates_get(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/environments/templates/{environment_template_id}`` (A-12)."""
    template_id = request.path_params["environment_template_id"]
    record = get_state().templates.get(principal_of(request), template_id)
    if record is None:
        return _template_not_found(template_id)
    return ServerResponse.ok(template_object(record))


def handle_templates_update(request: ServerRequest) -> ServerResponse:
    """``POST /v1/agents/environments/templates/{environment_template_id}`` (A-13)."""
    template_id = request.path_params["environment_template_id"]
    owner = principal_of(request)
    record = get_state().templates.get(owner, template_id)
    if record is None:
        return _template_not_found(template_id)
    fields = _parse_template(body_of(request), owner, create=False)
    if "name" in fields:
        record.data["name"] = fields["name"]
    if "env" in fields:
        record.private["env"] = fields["env"]
    if "files" in fields:
        record.private["files"] = fields["files"]
    get_state().templates.touch(record)
    return ServerResponse.ok(template_object(record))


def handle_templates_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/agents/environments/templates`` (A-14)."""
    rows = get_state().templates.list(principal_of(request))
    return page([template_object(r) for r in rows], request.query)


def handle_templates_delete(request: ServerRequest) -> ServerResponse:
    """``DELETE /v1/agents/environments/templates/{environment_template_id}`` (A-15)."""
    template_id = request.path_params["environment_template_id"]
    record = get_state().templates.delete(principal_of(request), template_id)
    if record is None:
        return _template_not_found(template_id)
    record.private.clear()
    return ServerResponse.ok(
        {
            "id": template_id,
            "object": "agent.environment.template.deleted",
            "deleted": True,
            "x_agent_sandbox": _template_label(),
        }
    )
