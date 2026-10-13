"""Plumbing shared by the local Agents API handlers (codex and qwen-code slice).

Holds the label contract (``x_easy_sandbox`` plus ``X-Easy-Sandbox-Local: 1``), the OpenAI
error envelope, paging, adapter selection and the process-wide runtime. Handlers live in the
``api_*`` modules and are registered in :mod:`easy_sandbox.server.routes_agents`.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import os
import re
import threading
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from ..types import ServerRequest, ServerResponse, SSEResponse
from .adapters import default_adapters
from .config import AgentSpec
from .errors import AgentConfigError, AgentNotFoundError, AgentRuntimeError, LocalApiError
from .local_state import get_state, reset_state
from .runtime import AgentRuntime

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "DIFFERENCES",
    "LOCAL_HEADER",
    "SLICE",
    "SLICE_LABEL",
    "body_of",
    "build_spec",
    "cannot",
    "check_env_map",
    "decode_base64",
    "err",
    "explicit_adapter",
    "first",
    "from_agent_exc",
    "get_agent_runtime",
    "header",
    "label",
    "local",
    "metadata_strict",
    "page",
    "principal_of",
    "reset_agent_runtime",
    "DEFAULT_AGENT_ORDER",
    "default_runtime_name",
    "select_adapter",
    "select_or_response",
    "text_of",
    "url_check",
    "workspace_of",
]

LOCAL_HEADER = "X-Easy-Sandbox-Local"

# Canonical runtimes served by this slice. Aliases resolve through the registry.
SLICE = frozenset({"codex", "qwen-code"})
SLICE_LABEL = "codex, qwen-code"
# Product order. The first entry is the default when the request does not name one.
DEFAULT_AGENT_ORDER = ("codex", "qwen-code")

#: The one table of stable difference codes carried in ``x_easy_sandbox.differences``.
DIFFERENCES: dict[str, str] = {
    "queued_not_steered": "input sent during a turn queues a new turn; no mid-turn steering",
    "usage_adapter_best_effort": "usage is whatever the CLI reported; null when it reported none",
    "redaction_best_effort": "output redaction covers registered secrets and common token shapes",
    "update_in_place": "updates apply in place; running sessions keep their snapshot",
    "snapshot_at_session_start": "a session copies the definition when it is created",
    "hosted_request_converted": "an empty openai_hosted request was converted to self_hosted",
    "nothing_provisioned": "the environment is a directory binding; nothing is provisioned",
    "local_workspace": "paths are interpreted relative to the environment workspace directory",
    "no_overwrite": "an existing file with different bytes is refused",
    "local_blob": "file ids are blobs held in server memory, not an OpenAI Files API",
    "not_hosted_template": "a reduced local record, not a hosted environment template",
    "applies_env_and_files_only": "a template applies env and inline files only",
    "memory_only": "secrets live in server memory and are lost on restart",
    "secret_in_agent_env": "agent-executed code can read the secret from the CLI environment",
    "snapshot_copy": "an immutable copy taken when the turn completed",
    "reported_paths_only": "only paths the CLI reported as written; the workdir is never scanned",
    "delete_removes_snapshot_only": "deleting removes the snapshot, not the file on disk",
    "trace_from_journal_timing_only": "spans come from journal timestamps; no text or arguments",
    "ids_from_cli_only": "subagent ids are those the CLI itself emitted",
    "turns_grouped_from_parent_stream": "turns are groups of the tagged parent stream",
    "turns_from_rollout": "turns come from the child rollout the session names",
    "summary_not_encrypted_compaction": "a local summary, not an encrypted compaction item",
    "response_is_cli_turn": "the response is one turn of a local CLI process",
    "stream_replayed_after_turn": "the stream replays the stored turn after it finished",
    "model_passthrough": "the model string is handed to the CLI, not served by OpenAI",
    "local_signer": "this server signs and delivers the event",
    "queued_steer": "response.steer queues a successor turn; it does not steer a running one",
    "not_implemented_locally": "no local capability exists for this operation",
}

_ERR_TYPES = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    409: "invalid_request_error",
    429: "rate_limit_error",
}


def label(*differences: str, compute: str = "local_process", **extra: Any) -> dict[str, Any]:
    """The ``x_easy_sandbox`` object. Never claims ``openai_hosted`` compute."""
    unknown = [d for d in differences if d not in DIFFERENCES]
    if unknown:
        raise ValueError(f"unknown difference codes: {unknown}")
    if compute not in ("local_process", "local_state", "none"):
        raise ValueError(f"invalid compute {compute!r}")
    return {"local": True, "compute": compute, "differences": list(differences), **extra}


def err(
    status: int,
    message: str,
    *,
    code: str,
    param: str | None = None,
    type_: str | None = None,
) -> ServerResponse:
    """OpenAI error envelope. Permanent 4xx responses are not retried."""
    headers = {"x-should-retry": "false"} if status < 500 else {}
    return ServerResponse(
        status=status,
        body={
            "error": {
                "message": message,
                "type": type_ or _ERR_TYPES.get(status, "server_error"),
                "param": param,
                "code": code,
            }
        },
        headers=headers,
    )


def cannot(message: str) -> ServerResponse:
    """Route refusal for a CANNOT operation: 404 ``not_found_error``, never 501."""
    response = err(
        404,
        message,
        code="agents.not_implemented_locally",
        type_="not_found_error",
    )
    response.body["error"]["x_easy_sandbox"] = label("not_implemented_locally", compute="none")
    return response


def from_agent_exc(exc: AgentRuntimeError) -> ServerResponse:
    """Map a runtime exception onto the error envelope."""
    code = "resource_not_found" if isinstance(exc, AgentNotFoundError) else exc.code
    type_ = "not_found_error" if exc.status == 404 else "invalid_request_error"
    return err(exc.status, exc.message, code=code, param=exc.param, type_=type_)


def local(handler: Callable[[ServerRequest], Any]) -> Callable[[ServerRequest], Any]:
    """Stamp ``X-Easy-Sandbox-Local: 1`` on every response of *handler*, errors included."""

    def wrapper(request: ServerRequest) -> Any:
        try:
            result = handler(request)
        except AgentRuntimeError as exc:
            result = from_agent_exc(exc)
        if isinstance(result, (ServerResponse, SSEResponse)):
            result.headers[LOCAL_HEADER] = "1"
        return result

    wrapper.__name__ = getattr(handler, "__name__", "handler")
    wrapper.__doc__ = handler.__doc__
    return wrapper


# ---------------------------------------------------------------------- #
# Request helpers
# ---------------------------------------------------------------------- #


def header(request: ServerRequest, name: str) -> str | None:
    """Case-insensitive request header (stripped, ``None`` when empty)."""
    target = name.lower()
    for key, value in request.headers.items():
        if key.lower() == target and value:
            return value.strip()
    return None


def first(query: dict[str, list[str]], name: str) -> str | None:
    """First query value of *name* (``None`` when absent or empty)."""
    values = query.get(name) or []
    if not values or values[0] == "":
        return None
    return values[0]


def body_of(request: ServerRequest) -> dict[str, Any]:
    """JSON object body (empty mapping otherwise)."""
    body = request.body
    return body if isinstance(body, dict) else {}


def principal_of(request: ServerRequest) -> str:
    """Owner key of the caller: the policy identity id, else ``local``."""
    ctx = request.context.get("policy")
    identity = getattr(ctx, "identity", None)
    return str(getattr(identity, "id", None) or "local")


def page(objects: list[dict[str, Any]], query: dict[str, list[str]]) -> ServerResponse:
    """OpenAI list envelope with ``after``/``limit``/``order`` paging."""
    limit_raw = first(query, "limit")
    limit = 20
    if limit_raw is not None:
        if not limit_raw.isdigit() or not 1 <= int(limit_raw) <= 100:
            return err(
                400,
                "limit must be an integer between 1 and 100",
                code="invalid_request",
                param="limit",
            )
        limit = int(limit_raw)
    order = first(query, "order") or "desc"
    if order not in ("asc", "desc"):
        return err(400, "order must be 'asc' or 'desc'", code="invalid_request", param="order")
    seq = list(objects) if order == "asc" else list(reversed(objects))
    after = first(query, "after")
    if after:
        ids = [str(obj.get("id")) for obj in seq]
        if after not in ids:
            return err(404, "after cursor not found", code="agents.cursor_not_found", param="after")
        seq = seq[ids.index(after) + 1 :]
    data = seq[:limit]
    return ServerResponse.ok(
        {
            "object": "list",
            "data": data,
            "first_id": data[0]["id"] if data else None,
            "last_id": data[-1]["id"] if data else None,
            "has_more": len(seq) > limit,
        }
    )


def text_of(value: Any) -> str:
    """Flatten an Agents ``input`` value (string, message, or content parts) to text."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "text" in value and not isinstance(value.get("text"), (dict, list)):
            nested = value.get("content")
            if nested is None:
                return str(value.get("text") or "")
        content = value.get("content", value.get("text", value.get("input")))
        return text_of(content)
    if isinstance(value, list):
        parts = [text_of(item) for item in value]
        return "\n".join(part for part in parts if part)
    return ""


# ---------------------------------------------------------------------- #
# Validation helpers
# ---------------------------------------------------------------------- #

_META_KEY_MAX = 64
_META_VALUE_MAX = 512
_META_MAX = 16


def metadata_strict(raw: Any, field: str = "metadata") -> dict[str, str]:
    """Official metadata limits: up to 16 string pairs, keys to 64, values to 512 chars."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise LocalApiError(f"{field}: expected a mapping of strings", param=field)
    if len(raw) > _META_MAX:
        raise LocalApiError(f"{field}: at most {_META_MAX} pairs", param=field)
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not 1 <= len(key) <= _META_KEY_MAX:
            raise LocalApiError(f"{field}: keys are 1 to {_META_KEY_MAX} characters", param=field)
        if not isinstance(value, str) or len(value) > _META_VALUE_MAX:
            raise LocalApiError(
                f"{field}.{key}: values are strings up to {_META_VALUE_MAX} characters",
                param=f"{field}.{key}",
            )
        out[key] = value
    return out


_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_ENV_DENY_EXACT = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "IFS",
        "ENV",
        "BASH_ENV",
        "PS4",
        "PROMPT_COMMAND",
        "TMPDIR",
        "TERM",
        "LANG",
        "LANGUAGE",
        "TZ",
        "NODE_OPTIONS",
        "NODE_PATH",
        "NODE_EXTRA_CA_CERTS",
        "NPM_CONFIG_REGISTRY",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "RUBYOPT",
        "PERL5OPT",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_ORG_ID",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
    }
)
_ENV_DENY_PREFIXES = (
    "LD_",
    "DYLD_",
    "CODEX_",
    "QWEN_",
    "EBX_",
    "GIT_",
    "XDG_",
    "LC_",
    "BASH_FUNC_",
    "NPM_CONFIG_",
    "OPENAI_",
    "ANTHROPIC_",
)
_ENV_MAX_ENTRIES = 64
_ENV_MAX_VALUE = 32 * 1024


def check_env_map(raw: Any, field: str) -> dict[str, str]:
    """Validate an ``env`` map against a deny list far wider than the spec parser's.

    The LLM endpoint, provider keys, proxies, loader and interpreter hooks, ``PATH``,
    ``HOME``, and every ``CODEX_*``, ``GIT_*`` and ``EBX_*`` name are refused.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise LocalApiError(f"{field}: expected a mapping of strings", param=field)
    if len(raw) > _ENV_MAX_ENTRIES:
        raise LocalApiError(f"{field}: at most {_ENV_MAX_ENTRIES} entries", param=field)
    out: dict[str, str] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not _ENV_NAME_RE.match(name):
            raise LocalApiError(f"{field}: invalid environment variable name", param=field)
        upper = name.upper()
        if (
            upper in _ENV_DENY_EXACT
            or upper.startswith(_ENV_DENY_PREFIXES)
            or upper.endswith("_PROXY")
        ):
            raise LocalApiError(
                f"{field}: environment variable {name} is not allowed", param=f"{field}.{name}"
            )
        if not isinstance(value, str) or "\x00" in value or len(value) > _ENV_MAX_VALUE:
            raise LocalApiError(
                f"{field}.{name}: expected a string without NUL up to {_ENV_MAX_VALUE} bytes",
                param=f"{field}.{name}",
            )
        out[name] = value
    return out


def _private_name(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    if lowered == "localhost" or lowered.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        addr = ipaddress.ip_address(lowered.strip("[]"))
    except ValueError:
        return False
    return not addr.is_global


def url_check(
    url: Any, field: str, *, https_only: bool = True, allow_private: bool | None = None
) -> tuple[str, str, int]:
    """Admit a URL and return ``(scheme, host, port)``.

    Userinfo, query strings and fragments are refused: they are the common places a token
    ends up on ``argv`` or in a response. Private, loopback and link-local hosts are refused
    unless ``EBX_AGENTS_ALLOW_PRIVATE_URLS=1``.
    """
    if not isinstance(url, str) or not url:
        raise LocalApiError(f"{field}: expected a URL string", param=field)
    parts = urlsplit(url)
    schemes = ("https",) if https_only else ("http", "https")
    if parts.scheme not in schemes or not parts.hostname:
        raise LocalApiError(f"{field}: must be an {' or '.join(schemes)} URL", param=field)
    if parts.username is not None or parts.password is not None:
        raise LocalApiError(f"{field}: must not contain credentials", param=field)
    if parts.query or parts.fragment:
        raise LocalApiError(f"{field}: must not contain a query string or fragment", param=field)
    if allow_private is None:
        allow_private = os.environ.get("EBX_AGENTS_ALLOW_PRIVATE_URLS", "") == "1"
    if not allow_private and _private_name(parts.hostname):
        raise LocalApiError(f"{field}: private and loopback hosts are not allowed", param=field)
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise LocalApiError(f"{field}: invalid port", param=field) from None
    return parts.scheme, parts.hostname.lower(), port


def decode_base64(data: Any, field: str, *, limit: int) -> bytes:
    """Strict base64 decode with a size cap."""
    if not isinstance(data, str):
        raise LocalApiError(f"{field}: expected a base64 string", param=field)
    if len(data) > (limit * 4) // 3 + 8:
        raise LocalApiError(
            f"{field}: larger than {limit} bytes", param=field, code="agents.file_too_large"
        )
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise LocalApiError(f"{field}: not valid base64", param=field) from None
    if len(raw) > limit:
        raise LocalApiError(
            f"{field}: larger than {limit} bytes", param=field, code="agents.file_too_large"
        )
    return raw


# ---------------------------------------------------------------------- #
# Adapter selection and spec building
# ---------------------------------------------------------------------- #


def _agent_block(body: dict[str, Any]) -> dict[str, Any]:
    agent = body.get("agent")
    return agent if isinstance(agent, dict) else {}


def _config_default() -> str | None:
    """``agents.default`` from ``EBX_AGENTS_DEFAULT`` or ``EBX_AGENTS_CONFIG``."""
    env = os.environ.get("EBX_AGENTS_DEFAULT", "").strip()
    if env:
        return env
    path = os.environ.get("EBX_AGENTS_CONFIG", "").strip()
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    direct = data.get("default")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    agents = data.get("agents")
    if isinstance(agents, dict):
        nested = agents.get("default")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def model_field(body: dict[str, Any]) -> str | None:
    """The ``model`` of an inline ``agent`` block or of the body itself."""
    for source in (_agent_block(body), body):
        value = source.get("model")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def explicit_adapter(request: ServerRequest, body: dict[str, Any]) -> str | None:
    """Adapter named by the caller, or ``None`` when the body only carries a model id."""
    named = header(request, "X-EBX-Adapter")
    if named:
        return named
    for source in (body, _agent_block(body)):
        for key in ("adapter", "runtime"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    model = model_field(body)
    if model and default_adapters().resolve_name(model) is not None:
        return model
    return None


def implicit_adapter() -> str:
    """Configured default, otherwise the first agent in :data:`DEFAULT_AGENT_ORDER`."""
    return _config_default() or DEFAULT_AGENT_ORDER[0]


def default_runtime_name() -> str | None:
    """Canonical runtime used when the request does not name one.

    ``None`` when a configured default is outside this slice.
    """
    canonical = default_adapters().resolve_name(implicit_adapter())
    if canonical in SLICE:
        return str(canonical)
    return None


def select_adapter(request: ServerRequest, body: dict[str, Any]) -> str:
    """Return the canonical runtime, or raise :class:`AgentRuntimeError`.

    An explicit adapter (header, ``adapter`` / ``runtime``, or a model string that
    is an adapter name) wins. Otherwise the configured default is used. If that
    is also unset, the first agent in :data:`DEFAULT_AGENT_ORDER` is used.
    Name another adapter in the request to select it.
    """
    raw = explicit_adapter(request, body) or implicit_adapter()
    canonical = default_adapters().resolve_name(raw)
    if canonical not in SLICE:
        raise AgentNotFoundError(
            f"adapter {raw!r} is not available in this slice ({SLICE_LABEL})",
            param="adapter",
        )
    return str(canonical)


def select_or_response(request: ServerRequest, body: dict[str, Any]) -> str | ServerResponse:
    """:func:`select_adapter` with errors rendered as responses."""
    try:
        return select_adapter(request, body)
    except AgentRuntimeError as exc:
        if isinstance(exc, AgentNotFoundError):
            return err(
                404,
                exc.message,
                code="agents.not_implemented_locally",
                param="adapter",
                type_="not_found_error",
            )
        return from_agent_exc(exc)


def workspace_of(body: dict[str, Any]) -> str:
    """Workspace directory of ``environment`` (``/workspace`` by default)."""
    env = body.get("environment")
    if env is None:
        return "/workspace"
    if not isinstance(env, dict):
        raise AgentConfigError("environment: expected a mapping")
    etype = env.get("type") or "self_hosted"
    if etype == "openai_hosted":
        raise AgentConfigError(
            "environment.type openai_hosted is not available; use self_hosted or none"
        )
    if etype not in ("self_hosted", "none"):
        raise AgentConfigError("environment.type must be self_hosted or none")
    raw = env.get("workspace_directory")
    if raw is None or raw == "":
        return "/workspace"
    if not isinstance(raw, str):
        raise AgentConfigError("environment.workspace_directory: expected a string")
    return raw


def pass_through_model(body: dict[str, Any]) -> str | None:
    """The model string for ``-m``, or ``None`` when the model names a runtime."""
    model = model_field(body)
    if not model or default_adapters().resolve_name(model) is not None:
        return None
    return model


def build_spec(body: dict[str, Any], canonical: str) -> AgentSpec:
    """Spec of an inline ``agent`` block (name, instructions, model pass-through)."""
    agent = _agent_block(body)
    raw_name = agent.get("name")
    name = raw_name if isinstance(raw_name, str) and raw_name else canonical
    data: dict[str, Any] = {
        "name": name,
        "runtime": canonical,
        "workspace": {"path": workspace_of(body)},
    }
    instructions = agent.get("instructions")
    if instructions is not None:
        if not isinstance(instructions, str):
            raise AgentConfigError("agent.instructions: expected a string")
        if instructions:
            data["instructions"] = instructions
    model = pass_through_model(body)
    if model:
        data["model"] = model
    return AgentSpec.from_dict(data)


# ---------------------------------------------------------------------- #
# Process-wide runtime
# ---------------------------------------------------------------------- #

_runtime_lock = threading.Lock()
_runtime: AgentRuntime | None = None


def get_agent_runtime() -> AgentRuntime:
    """Process-wide runtime. Created on first use so tests can set env first."""
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            runtime = AgentRuntime()
            runtime.turn_hooks.append(get_state().artifacts.on_turn_done)
            _runtime = runtime
        return _runtime


def reset_agent_runtime() -> None:
    """Drop the process-wide runtime and every local record (tests).

    In-flight turns keep the old instance.
    """
    global _runtime
    with _runtime_lock:
        _runtime = None
    reset_state()
