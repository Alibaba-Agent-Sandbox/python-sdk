"""Declarative per-endpoint policy for the sandbox HTTP server — stdlib-only.

A :class:`ServerPolicy` is an immutable, validated description of *which endpoints
are exposed, to whom, and under which restrictions* (path scoping, size limits,
parameter allow-lists, rate limits, audit).  It is pure data: it never touches the
filesystem or the route table.  Enforcement lives in :mod:`easy_sandbox.server.runtime`
(request pipeline) and :mod:`easy_sandbox.server.guard` (path checks).

Design: ``docs/en/design/fine-grained-capabilities.md``.

Example::

    policy = ServerPolicy.from_dict({
        "preset": "transfer-only",
        "endpoints": {"files_download_stream": {"paths": {"allow": ["/home/user/out"]}}},
    })
    SandboxServer(policy=policy).serve(9000)
"""

from __future__ import annotations

import copy
import dataclasses
import difflib
import fnmatch
import hashlib
import json
import os
import re
from typing import TYPE_CHECKING, Any

from .router import CapabilityGroup

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "ENDPOINT_CATALOG",
    "PRESETS",
    "EndpointSpec",
    "Identity",
    "PolicyConfigError",
    "PolicyDenied",
    "ServerPolicy",
    "parse_size",
    "scope_granted",
]

POLICY_VERSION = 1

#: Environment variables / files consulted by :meth:`ServerPolicy.from_environment`.
POLICY_ENV_VAR = "EBX_SERVER_POLICY"
POLICY_FILE_ENV_VAR = "EBX_SERVER_POLICY_FILE"
DEFAULT_POLICY_FILE = "/etc/easy-sandbox/server-policy.json"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PolicyConfigError(ValueError):
    """The policy document is invalid (the server refuses to start)."""


class PolicyDenied(Exception):  # noqa: N818  (public name fixed by the design doc)
    """Raised by enforcement code to deny a request with a stable machine code.

    Attributes:
        code: Stable machine string (``missing_scope``, ``path_not_allowed``, ...).
        message: Human-readable text (never contains secrets).
        status: HTTP status for the response (403 by default).
        endpoint: Endpoint ID (filled by the dispatcher when missing).
        extra: Additional JSON fields merged into the error body.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 403,
        endpoint: str = "",
        error_type: str = "PolicyDenied",
        **extra: Any,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.endpoint = endpoint
        self.error_type = error_type
        self.extra = extra

    def to_body(self) -> dict[str, Any]:
        """Return the JSON error body (superset of the legacy ``{error, type}``)."""
        body: dict[str, Any] = {"error": self.message, "type": self.error_type, "code": self.code}
        if self.endpoint:
            body["endpoint"] = self.endpoint
        body.update(self.extra)
        return body


@dataclasses.dataclass(frozen=True)
class Identity:
    """An authenticated caller."""

    id: str
    scopes: frozenset[str]

    def can(self, scope: str) -> bool:
        """Return whether this identity holds *scope* (``core:read`` is implicit)."""
        return scope == "core:read" or scope_granted(self.scopes, scope)


def scope_granted(granted: Iterable[str], required: str) -> bool:
    """Return whether *required* is covered by *granted* (``*`` / ``ns:*`` wildcards)."""
    granted_set = set(granted)
    if "*" in granted_set or required in granted_set:
        return True
    ns, _, _ = required.partition(":")
    return f"{ns}:*" in granted_set


# ---------------------------------------------------------------------------
# Endpoint catalogue
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class EndpointSpec:
    """Built-in knowledge about one endpoint (default scopes, tunable knobs)."""

    scopes: tuple[str, ...] = ()
    limits: frozenset[str] = frozenset()
    params: frozenset[str] = frozenset()
    paths: bool = False
    #: ``True`` when the endpoint can execute arbitrary programs / code.
    exec: bool = False


_COMMON_LIMITS = frozenset({"max_request_bytes", "rate_per_minute", "max_concurrency"})


def _spec(
    scopes: tuple[str, ...] = (),
    *,
    limits: Iterable[str] = (),
    params: Iterable[str] = (),
    paths: bool = False,
    exec: bool = False,  # noqa: A002
) -> EndpointSpec:
    return EndpointSpec(
        scopes=scopes,
        limits=_COMMON_LIMITS | frozenset(limits),
        params=frozenset(params),
        paths=paths,
        exec=exec,
    )


_UPLOAD_PARAMS = ("overwrite", "allow_extensions", "deny_extensions")
_EXEC_PARAMS = ("allow_commands", "deny_commands")
_EXEC_LIMITS = ("timeout_seconds", "max_output_bytes", "max_processes")

#: Every built-in endpoint ID -> defaults.  A unit test asserts that every route
#: registered by the built-in modules has an entry here.
ENDPOINT_CATALOG: dict[str, EndpointSpec] = {
    "health": _spec(),
    "capabilities": _spec(("core:read",)),
    "capabilities_check": _spec(("core:read",)),
    "list_commands": _spec(("commands:list",)),
    "run_command": _spec(("commands:run",)),
    "upload": _spec(("files:write",), limits=("max_bytes",), params=_UPLOAD_PARAMS, paths=True),
    "download": _spec(("files:read",), limits=("max_bytes",), paths=True),
    "files_list": _spec(("files:read",), limits=("max_entries", "max_depth"), paths=True),
    "files_stat": _spec(("files:read",), paths=True),
    "files_mkdir": _spec(("files:write",), paths=True),
    "files_delete": _spec(("files:delete",), paths=True),
    "files_move": _spec(("files:write", "files:delete"), paths=True),
    "files_search": _spec(
        ("files:read",),
        limits=("max_results", "max_depth", "timeout_seconds"),
        paths=True,
    ),
    "files_upload_stream": _spec(
        ("files:write",), limits=("max_bytes",), params=_UPLOAD_PARAMS, paths=True
    ),
    "files_download_stream": _spec(("files:read",), limits=("max_bytes",), paths=True),
    "files_archive": _spec(("files:read",), limits=("max_files", "max_bytes"), paths=True),
    "files_watch": _spec(("files:read",), limits=("max_duration_seconds",), paths=True),
    "shell": _spec(
        ("process:run",), limits=_EXEC_LIMITS, params=_EXEC_PARAMS, paths=True, exec=True
    ),
    "shell_stream": _spec(
        ("process:run",), limits=_EXEC_LIMITS, params=_EXEC_PARAMS, paths=True, exec=True
    ),
    "process_start": _spec(
        ("process:run",), limits=_EXEC_LIMITS, params=_EXEC_PARAMS, paths=True, exec=True
    ),
    "process_list": _spec(("process:read",)),
    "process_detail": _spec(("process:read",)),
    "process_output": _spec(("process:read",)),
    "process_signal": _spec(("process:manage",), params=("allowed_signals",)),
    "process_stdin": _spec(("process:manage",)),
    "pty_create_session": _spec(
        ("terminal:use",), limits=("max_sessions",), params=("shells", "env_deny")
    ),
    "pty_list_sessions": _spec(("terminal:use",)),
    "pty_detail": _spec(("terminal:use",)),
    "pty_resize": _spec(("terminal:use",)),
    "pty_delete_session": _spec(("terminal:use",)),
    "pty_connect": _spec(("terminal:use",)),
    "system_info": _spec(("system:read",)),
    "system_metrics": _spec(("system:read",)),
    "ports": _spec(("system:read",)),
    "packages": _spec(("system:read",)),
    "env_get": _spec(("system:read",), params=("allow_vars", "deny_vars")),
    "env_set": _spec(("system:write",), params=("allow_vars", "deny_vars")),
    "code_run": _spec(
        ("devtools:run",),
        limits=("timeout_seconds", "max_output_bytes"),
        params=("languages",),
        exec=True,
    ),
    "git_status": _spec(("devtools:read",), paths=True),
    "git_diff": _spec(("devtools:read",), paths=True),
    "browser_navigate": _spec(
        ("browser:use",),
        params=("url_allow", "url_deny", "block_private_networks"),
        exec=True,
    ),
    "browser_screenshot": _spec(("browser:use",)),
    "browser_content": _spec(("browser:use",)),
    "browser_click": _spec(("browser:use",)),
    "browser_type": _spec(("browser:use",)),
    "browser_evaluate": _spec(("browser:evaluate",), exec=True),
    "browser_pdf": _spec(("browser:use",)),
    "browser_console": _spec(("browser:use",)),
}

for _agents_endpoint in (
    "agents_sessions_create",
    "agents_sessions_list",
    "agents_sessions_get",
    "agents_sessions_update",
    "agents_sessions_delete",
    "agents_sessions_events_create",
    "agents_sessions_events_stream",
    "agents_sessions_items_list",
    "agents_sessions_turns_list",
    "agents_sessions_turns_get",
    "agents_sessions_turns_items_list",
    "agents_artifacts_list",
    "agents_artifacts_get",
    "agents_artifacts_delete",
    "agents_artifacts_content",
    "agents_traces_list",
    "agents_subagents_list",
    "agents_subagents_get",
    "agents_subagents_items_list",
    "agents_subagents_turns_list",
    "agents_subagents_turns_get",
    "agents_subagents_turns_items_list",
    "agents_runtimes_list",
    "agents_environments_create",
    "agents_environments_list",
    "agents_environments_get",
    "agents_environment_templates_create",
    "agents_environment_templates_list",
    "agents_environment_templates_get",
    "agents_environment_templates_update",
    "agents_environment_templates_delete",
    "agents_environment_files_create",
    "agents_environment_files_list",
    "agents_cannot_executor_registration",
    "agents_cannot_executor_channel",
    "agents_definitions_create",
    "agents_definitions_list",
    "agents_definitions_get",
    "agents_definitions_update",
    "agents_definitions_delete",
    "agents_vaults_create",
    "agents_vaults_list",
    "agents_vaults_get",
    "agents_vaults_update",
    "agents_vaults_delete",
    "agents_vault_credentials_create",
    "agents_vault_credentials_list",
    "agents_vault_credentials_get",
    "agents_vault_credentials_update",
    "agents_vault_credentials_delete",
    "agents_responses_create",
    "agents_responses_connect",
    "agents_cannot_responses_input_tokens",
    "agents_responses_compact",
    "agents_responses_get",
    "agents_responses_delete",
    "agents_responses_cancel",
    "agents_responses_input_items",
    "agents_models_list",
    "agents_models_get",
    "agents_cannot_models_delete",
    "agents_files_create",
    "agents_webhooks_create",
    "agents_webhooks_list",
    "agents_webhooks_get",
    "agents_webhooks_update",
    "agents_webhooks_delete",
    "agents_webhooks_rotate_secret",
    "agents_webhooks_test",
    "agents_webhook_event_types",
):
    ENDPOINT_CATALOG[_agents_endpoint] = _spec(("agents:use",))

#: Endpoints that can never be disabled / locked out.
CORE_ENDPOINTS = frozenset({"health", "capabilities", "capabilities_check"})

TRANSFER_ENDPOINTS = ("upload", "download", "files_upload_stream", "files_download_stream")

#: Every limit / param key (closed vocabulary) with its value type.
_LIMIT_TYPES: dict[str, str] = {
    "max_request_bytes": "size",
    "max_bytes": "size",
    "max_output_bytes": "size",
    "rate_per_minute": "int",
    "max_concurrency": "int",
    "max_entries": "int",
    "max_depth": "int",
    "max_results": "int",
    "max_files": "int",
    "max_processes": "int",
    "max_sessions": "int",
    "timeout_seconds": "number",
    "max_duration_seconds": "number",
}
_PARAM_TYPES: dict[str, str] = {
    "overwrite": "bool",
    "allow_extensions": "strlist",
    "deny_extensions": "strlist",
    "allow_commands": "strlist",
    "deny_commands": "strlist",
    "allowed_signals": "intlist",
    "shells": "strlist",
    "env_deny": "strlist",
    "allow_vars": "strlist",
    "deny_vars": "strlist",
    "languages": "strlist",
    "url_allow": "strlist",
    "url_deny": "strlist",
    "block_private_networks": "bool",
}
#: Params whose lists are *unioned* across layers (deny semantics).
_UNION_PARAMS = frozenset({"deny_extensions", "deny_commands", "deny_vars", "env_deny", "url_deny"})

_RULE_KEYS = frozenset({"enabled", "scopes", "paths", "limits", "params", "audit"})
_PATH_KEYS = frozenset({"allow", "deny", "read_only", "symlinks"})
_AUDIT_MODES = ("off", "deny", "all")
_TOP_KEYS = frozenset(
    {"version", "preset", "base_dir", "groups", "defaults", "auth", "endpoints", "description"}
)
_AUTH_KEYS = frozenset({"tokens", "allow_anonymous", "anonymous_scopes", "legacy_scopes"})
_TOKEN_KEYS = frozenset({"id", "scopes", "token_env", "token_sha256"})
_GROUP_NAMES = tuple(g.value for g in CapabilityGroup)

_SCOPE_RE = re.compile(r"^(\*|[a-z][a-z0-9_]*:(\*|[a-z][a-z0-9_:.\-]*)|[a-z][a-z0-9_.\-]*)$")
_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]*)\s*$")
_SIZE_UNITS = {
    "": 1,
    "b": 1,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
}


def parse_size(value: Any) -> int:
    """Parse a byte size: ints are bytes, strings accept ``KB/MB/GB`` (1000) and ``KiB/MiB/GiB``.

    Raises:
        PolicyConfigError: On malformed or non-positive input.
    """
    if isinstance(value, bool):
        raise PolicyConfigError(f"invalid size {value!r}")
    if isinstance(value, int):
        if value <= 0:
            raise PolicyConfigError(f"size must be positive, got {value}")
        return value
    if isinstance(value, str):
        m = _SIZE_RE.match(value)
        if m:
            unit = _SIZE_UNITS.get(m.group(2).lower())
            if unit is not None:
                result = int(float(m.group(1)) * unit)
                if result > 0:
                    return result
    raise PolicyConfigError(f"invalid size {value!r} (use an integer or e.g. '5MB', '1GiB')")


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

_WRITE_ENDPOINTS = ("upload", "files_mkdir", "files_delete", "files_move", "files_upload_stream")
_HARDENED_DENY = [
    "/proc",
    "/sys",
    "/dev",
    "**/.ssh",
    "**/.env",
    "**/.env.*",
    "**/*.pem",
    "**/id_rsa*",
    "**/id_ed25519*",
]


def _only_rules(ids: Iterable[str]) -> dict[str, Any]:
    rules: dict[str, Any] = {"*": {"enabled": False}}
    for endpoint in ids:
        rules[endpoint] = {"enabled": True}
    return rules


#: Preset name -> policy dict (documented in ``server-api.md``).
PRESETS: dict[str, dict[str, Any]] = {
    "default": {},
    "transfer-only": {"endpoints": _only_rules(TRANSFER_ENDPOINTS)},
    "read-only": {
        "groups": {"process": False, "terminal": False, "dev_tools": False, "browser": False},
        "endpoints": {
            **{name: {"enabled": False} for name in _WRITE_ENDPOINTS},
            "env_set": {"enabled": False},
        },
    },
    "hardened": {
        "groups": {"process": False, "terminal": False, "dev_tools": False, "browser": False},
        "endpoints": {
            "env_set": {"enabled": False},
            "files_*": {"paths": {"deny": list(_HARDENED_DENY), "symlinks": "within"}},
            "upload": {"paths": {"deny": list(_HARDENED_DENY)}},
            "download": {"paths": {"deny": list(_HARDENED_DENY)}},
        },
        "defaults": {"audit": "deny"},
    },
    "locked": {"endpoints": _only_rules(("list_commands", "run_command"))},
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _suggest(word: str, choices: Iterable[str]) -> str:
    match = difflib.get_close_matches(word, list(choices), n=1)
    return f" (did you mean {match[0]!r}?)" if match else ""


def _check_keys(obj: Any, allowed: Iterable[str], where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise PolicyConfigError(f"{where}: expected an object, got {type(obj).__name__}")
    allowed_set = set(allowed)
    for key in obj:
        if key not in allowed_set:
            raise PolicyConfigError(
                f"{where}.{key}: unknown key{_suggest(str(key), allowed_set)}; "
                f"allowed: {', '.join(sorted(allowed_set))}"
            )
    return obj


def _check_scopes(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(s, str) for s in value):
        raise PolicyConfigError(f"{where}: expected a list of scope strings")
    for scope in value:
        if not _SCOPE_RE.match(scope):
            raise PolicyConfigError(f"{where}: invalid scope {scope!r}")
    return list(value)


def _check_value(kind: str, value: Any, where: str) -> Any:
    if kind == "size":
        return parse_size(value)
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise PolicyConfigError(f"{where}: expected a positive integer, got {value!r}")
        return value
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise PolicyConfigError(f"{where}: expected a positive number, got {value!r}")
        return value
    if kind == "bool":
        if not isinstance(value, bool):
            raise PolicyConfigError(f"{where}: expected true/false, got {value!r}")
        return value
    if kind == "strlist":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise PolicyConfigError(f"{where}: expected a list of strings")
        return list(value)
    if kind == "intlist":
        if not isinstance(value, list) or not all(
            isinstance(v, int) and not isinstance(v, bool) for v in value
        ):
            raise PolicyConfigError(f"{where}: expected a list of integers")
        return list(value)
    raise AssertionError(kind)  # pragma: no cover


def _normalise_rule(rule: Any, where: str) -> dict[str, Any]:
    """Validate the *syntax* of one endpoint rule and normalise values."""
    _check_keys(rule, _RULE_KEYS, where)
    out: dict[str, Any] = {}
    if "enabled" in rule:
        if not isinstance(rule["enabled"], bool):
            raise PolicyConfigError(f"{where}.enabled: expected true/false")
        out["enabled"] = rule["enabled"]
    if "scopes" in rule:
        out["scopes"] = _check_scopes(rule["scopes"], f"{where}.scopes")
    if "audit" in rule:
        if rule["audit"] not in _AUDIT_MODES:
            raise PolicyConfigError(f"{where}.audit: expected one of {list(_AUDIT_MODES)}")
        out["audit"] = rule["audit"]
    if "paths" in rule:
        paths = _check_keys(rule["paths"], _PATH_KEYS, f"{where}.paths")
        norm_paths: dict[str, Any] = {}
        for key in ("allow", "deny"):
            if key in paths:
                val = _check_value("strlist", paths[key], f"{where}.paths.{key}")
                if key == "allow":
                    for item in val:
                        if not os.path.isabs(item):
                            raise PolicyConfigError(
                                f"{where}.paths.allow: {item!r} must be an absolute directory"
                            )
                if any("\x00" in item for item in val):
                    raise PolicyConfigError(f"{where}.paths.{key}: NUL byte in pattern")
                norm_paths[key] = val
        if "read_only" in paths:
            norm_paths["read_only"] = _check_value(
                "bool", paths["read_only"], f"{where}.paths.read_only"
            )
        if "symlinks" in paths:
            if paths["symlinks"] not in ("within", "never"):
                raise PolicyConfigError(f"{where}.paths.symlinks: expected 'within' or 'never'")
            norm_paths["symlinks"] = paths["symlinks"]
        out["paths"] = norm_paths
    for section, types in (("limits", _LIMIT_TYPES), ("params", _PARAM_TYPES)):
        if section in rule:
            sec = _check_keys(rule[section], types, f"{where}.{section}")
            out[section] = {
                key: _check_value(types[key], val, f"{where}.{section}.{key}")
                for key, val in sec.items()
            }
    return out


def _normalise_config(raw: Any) -> dict[str, Any]:
    """Validate and normalise a whole policy document (syntax only)."""
    top = _check_keys(raw, _TOP_KEYS, "policy")
    out: dict[str, Any] = {}
    version = top.get("version", POLICY_VERSION)
    if not isinstance(version, int) or isinstance(version, bool) or version != POLICY_VERSION:
        raise PolicyConfigError(
            f"policy.version: unsupported {version!r}; this server understands {POLICY_VERSION}"
        )
    out["version"] = version
    if "description" in top:
        out["description"] = str(top["description"])
    if "preset" in top:
        if top["preset"] not in PRESETS:
            raise PolicyConfigError(
                f"policy.preset: unknown {top['preset']!r}{_suggest(str(top['preset']), PRESETS)}; "
                f"allowed: {', '.join(PRESETS)}"
            )
        out["preset"] = top["preset"]
    if "base_dir" in top:
        base = top["base_dir"]
        if not isinstance(base, str) or not os.path.isabs(base) or "\x00" in base:
            raise PolicyConfigError("policy.base_dir: expected an absolute path")
        out["base_dir"] = base
    if "groups" in top:
        groups = _check_keys(top["groups"], _GROUP_NAMES, "policy.groups")
        for name, enabled in groups.items():
            if not isinstance(enabled, bool):
                raise PolicyConfigError(f"policy.groups.{name}: expected true/false")
            if name == "core" and not enabled:
                raise PolicyConfigError("policy.groups.core: the core group cannot be disabled")
        out["groups"] = dict(groups)
    if "defaults" in top:
        out["defaults"] = _normalise_rule(top["defaults"], "policy.defaults")
    if "auth" in top:
        out["auth"] = _normalise_auth(top["auth"])
    if "endpoints" in top:
        endpoints = top["endpoints"]
        if not isinstance(endpoints, dict):
            raise PolicyConfigError("policy.endpoints: expected an object")
        out["endpoints"] = {
            str(sel): _normalise_rule(rule, f"policy.endpoints.{sel}")
            for sel, rule in endpoints.items()
        }
    return out


def _normalise_auth(raw: Any) -> dict[str, Any]:
    auth = _check_keys(raw, _AUTH_KEYS, "policy.auth")
    out: dict[str, Any] = {}
    for key in ("allow_anonymous",):
        if key in auth:
            out[key] = _check_value("bool", auth[key], f"policy.auth.{key}")
    for key in ("anonymous_scopes", "legacy_scopes"):
        if key in auth:
            out[key] = _check_scopes(auth[key], f"policy.auth.{key}")
    if "tokens" in auth:
        tokens = auth["tokens"]
        if not isinstance(tokens, list):
            raise PolicyConfigError("policy.auth.tokens: expected a list")
        seen: set[str] = set()
        norm_tokens: list[dict[str, Any]] = []
        for index, tok in enumerate(tokens):
            where = f"policy.auth.tokens[{index}]"
            _check_keys(tok, _TOKEN_KEYS, where)
            ident = tok.get("id")
            if not isinstance(ident, str) or not ident or ident == "legacy":
                raise PolicyConfigError(
                    f"{where}.id: expected a non-empty string other than 'legacy'"
                )
            if ident in seen:
                raise PolicyConfigError(f"{where}.id: duplicate identity {ident!r}")
            seen.add(ident)
            has_env = "token_env" in tok
            has_hash = "token_sha256" in tok
            if has_env == has_hash:
                raise PolicyConfigError(
                    f"{where}: exactly one of 'token_env' or 'token_sha256' is required "
                    "(plain tokens are never accepted inline)"
                )
            entry: dict[str, Any] = {"id": ident}
            if "scopes" not in tok:
                raise PolicyConfigError(f"{where}.scopes: required")
            entry["scopes"] = _check_scopes(tok["scopes"], f"{where}.scopes")
            if has_env:
                if not isinstance(tok["token_env"], str) or not tok["token_env"]:
                    raise PolicyConfigError(f"{where}.token_env: expected an env var name")
                entry["token_env"] = tok["token_env"]
            else:
                digest = tok["token_sha256"]
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                    raise PolicyConfigError(f"{where}.token_sha256: expected 64 hex characters")
                entry["token_sha256"] = digest.lower()
            norm_tokens.append(entry)
        out["tokens"] = norm_tokens
    return out


# ---------------------------------------------------------------------------
# ServerPolicy
# ---------------------------------------------------------------------------


DEFAULTS_SELECTOR = "@defaults"


def _selector_kind(selector: str) -> int:
    """0 = ``defaults`` block, 1 = ``group:``, 2 = glob, 3 = exact."""
    if selector == DEFAULTS_SELECTOR:
        return 0
    if selector.startswith("group:"):
        return 1
    if any(ch in selector for ch in "*?["):
        return 2
    return 3


class ServerPolicy:
    """Immutable, validated policy document.

    Create with :meth:`from_dict`, :meth:`from_json`, :meth:`from_file`,
    :meth:`preset`, :meth:`only` or :meth:`from_environment`.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = _normalise_config(config)

    # -- constructors -------------------------------------------------- #

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServerPolicy:
        """Validate *data* (never mutated) and build a policy."""
        return cls(copy.deepcopy(data))

    @classmethod
    def from_json(cls, text: str) -> ServerPolicy:
        """Parse a JSON document."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PolicyConfigError(f"policy is not valid JSON: {exc}") from exc
        return cls(data)

    @classmethod
    def from_file(cls, path: str) -> ServerPolicy:
        """Load ``.json`` (always) or ``.yaml``/``.yml`` (only if PyYAML is importable)."""
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            raise PolicyConfigError(f"cannot read policy file {path!r}: {exc}") from exc
        if path.endswith((".yaml", ".yml")):
            try:
                import yaml  # type: ignore[import-untyped,unused-ignore]
            except ImportError as exc:
                raise PolicyConfigError(
                    "YAML policy files need PyYAML; compile to JSON instead"
                ) from exc
            return cls(yaml.safe_load(text))
        return cls.from_json(text)

    @classmethod
    def preset(cls, name: str, **overrides: Any) -> ServerPolicy:
        """Return the preset *name*; ``overrides`` are top-level keys merged on top."""
        if name not in PRESETS:
            raise PolicyConfigError(f"unknown preset {name!r}{_suggest(name, PRESETS)}")
        data: dict[str, Any] = {"preset": name}
        data.update(overrides)
        return cls(data)

    @classmethod
    def only(
        cls, *endpoint_ids: str, paths: dict[str, Any] | None = None, **rule: Any
    ) -> ServerPolicy:
        """Expose only the listed endpoints (plus the always-on core ones).

        ``"transfer"`` expands to the upload/download endpoints.  ``paths`` and
        any other rule keys (``limits=...``) are applied to every listed endpoint.
        """
        ids: list[str] = []
        for item in endpoint_ids:
            ids.extend(TRANSFER_ENDPOINTS if item == "transfer" else (item,))
        endpoints: dict[str, Any] = {"*": {"enabled": False}}
        for endpoint in ids:
            spec = ENDPOINT_CATALOG.get(endpoint)
            ep_rule: dict[str, Any] = {"enabled": True}
            if paths and (spec is None or spec.paths):
                ep_rule["paths"] = copy.deepcopy(paths)
            for key, value in rule.items():
                if key == "limits" and spec is not None:
                    ep_rule[key] = {k: v for k, v in value.items() if k in spec.limits}
                else:
                    ep_rule[key] = copy.deepcopy(value)
            endpoints[endpoint] = ep_rule
        return cls({"endpoints": endpoints})

    @classmethod
    def from_environment(cls) -> ServerPolicy | None:
        """Load the ambient policy (inline env, file env, well-known file) or ``None``."""
        inline = os.environ.get(POLICY_ENV_VAR)
        if inline:
            return cls.from_json(inline)
        path = os.environ.get(POLICY_FILE_ENV_VAR)
        if path:
            return cls.from_file(path)
        if os.path.isfile(DEFAULT_POLICY_FILE):
            return cls.from_file(DEFAULT_POLICY_FILE)
        return None

    # -- derivation ---------------------------------------------------- #

    def with_endpoint(self, selector: str, **rule: Any) -> ServerPolicy:
        """Return a new policy with *rule* merged into ``endpoints[selector]``."""
        data = copy.deepcopy(self._config)
        endpoints = data.setdefault("endpoints", {})
        endpoints[selector] = _deep_update(endpoints.get(selector, {}), copy.deepcopy(rule))
        return ServerPolicy(data)

    def with_options(self, **top: Any) -> ServerPolicy:
        """Return a new policy with top-level keys (``base_dir``, ``groups``, ...) replaced."""
        data = copy.deepcopy(self._config)
        data.update(copy.deepcopy(top))
        return ServerPolicy(data)

    # -- accessors ----------------------------------------------------- #

    def to_dict(self) -> dict[str, Any]:
        """Return the normalised policy document (deep copy)."""
        return copy.deepcopy(self._config)

    @property
    def base_dir(self) -> str | None:
        """Policy-level ``base_dir`` override, if any."""
        return self._config.get("base_dir")

    @property
    def groups(self) -> dict[str, bool]:
        """Group toggles requested by the policy."""
        return dict(self._config.get("groups", {}))

    @property
    def auth(self) -> dict[str, Any]:
        """The ``auth`` block."""
        return copy.deepcopy(self._config.get("auth", {}))

    @property
    def preset_name(self) -> str:
        """The preset in use (``default`` when unspecified)."""
        return str(self._config.get("preset", "default"))

    @property
    def revision(self) -> str:
        """Content hash of the normalised policy (cache invalidation key)."""
        blob = json.dumps(self._config, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(blob).hexdigest()[:16]

    def has_identities(self) -> bool:
        """Whether ``auth.tokens`` is configured (anonymous access disabled by default)."""
        return bool(self._config.get("auth", {}).get("tokens"))

    # -- rule layers (consumed by the runtime) ------------------------- #

    def layers(self) -> list[tuple[str, int, dict[str, Any]]]:
        """Return ``(selector, source_rank, rule)`` entries; source 0 = preset, 1 = user."""
        out: list[tuple[str, int, dict[str, Any]]] = []
        preset = PRESETS[self.preset_name]
        if preset.get("defaults"):
            out.append(
                (DEFAULTS_SELECTOR, 0, _normalise_rule(preset["defaults"], "preset.defaults"))
            )
        for sel, rule in preset.get("endpoints", {}).items():
            out.append((sel, 0, _normalise_rule(rule, f"preset.endpoints.{sel}")))
        if self._config.get("defaults"):
            out.append((DEFAULTS_SELECTOR, 1, self._config["defaults"]))
        for sel, rule in self._config.get("endpoints", {}).items():
            out.append((sel, 1, rule))
        return out

    def preset_groups(self) -> dict[str, bool]:
        """Groups from preset overlaid by the policy's own ``groups``."""
        groups = dict(PRESETS[self.preset_name].get("groups", {}))
        groups.update(self._config.get("groups", {}))
        return groups

    # -- binding / debugging ------------------------------------------- #

    def bind(
        self,
        table: Any = None,
        *,
        legacy_token: str | None = None,
        registry: Any = None,
    ) -> Any:
        """Bind to a route table (a *copy* of the default table when omitted).

        Returns:
            A :class:`~easy_sandbox.server.runtime.PolicyEngine`.
        """
        from . import app as _app  # noqa: F401  (registers built-in routes)
        from .router import default_table
        from .runtime import PolicyEngine, apply_groups

        bound = (table if table is not None else default_table()).copy()
        apply_groups(bound, self)
        return PolicyEngine(self, bound, legacy_token=legacy_token, registry=registry)

    def explain(
        self,
        endpoint: str,
        *,
        scopes: list[str] | None = None,
        path: str | None = None,
        op: str | None = None,
    ) -> dict[str, Any]:
        """Return the decision for *endpoint* as seen by an identity holding *scopes*."""
        return self.bind().explain(endpoint, scopes=scopes, path=path, op=op)  # type: ignore[no-any-return]

    def lint(self) -> list[str]:
        """Return configuration warnings (see design doc 3.9)."""
        return self.bind().lint()  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        return f"ServerPolicy(preset={self.preset_name!r}, revision={self.revision!r})"


def _deep_update(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_update(out[key], value)
        else:
            out[key] = value
    return out


def selector_matches(selector: str, name: str, group: str) -> bool:
    """Return whether *selector* (exact / glob / ``group:x``) selects endpoint *name*."""
    if selector == DEFAULTS_SELECTOR:
        return True
    if selector.startswith("group:"):
        return selector[6:] == group
    if any(ch in selector for ch in "*?["):
        return fnmatch.fnmatchcase(name, selector)
    return selector == name
