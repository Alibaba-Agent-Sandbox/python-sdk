"""Policy enforcement runtime: binds a :class:`ServerPolicy` to a :class:`RouteTable`.

The :class:`PolicyEngine` resolves one :class:`EffectiveRule` per route, authenticates
callers into :class:`~easy_sandbox.server.policy.Identity` objects, applies rate and
concurrency limits, emits audit events and produces the discovery document served by
``GET /capabilities``.  Handlers receive an :class:`EndpointContext` under
``request.context["policy"]``.

The module is stdlib-only and has no import-time side effects.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from typing import TYPE_CHECKING, Any

from ._version import __version__
from .guard import OP_DELETE, OP_EXEC, OP_READ, OP_WRITE, PathGuard
from .policy import (
    _COMMON_LIMITS,
    _UNION_PARAMS,
    CORE_ENDPOINTS,
    DEFAULTS_SELECTOR,
    ENDPOINT_CATALOG,
    EndpointSpec,
    Identity,
    PolicyConfigError,
    PolicyDenied,
    ServerPolicy,
    _selector_kind,
    scope_granted,
    selector_matches,
)
from .router import CapabilityGroup, RouteInfo

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from .router import RouteTable

__all__ = [
    "EffectiveRule",
    "EndpointContext",
    "PolicyEngine",
    "apply_groups",
    "child_env",
    "context_of",
]

AUDIT_LOGGER = "easy_sandbox.server.audit"
_BASE_DIR_ENV_VAR = "EBX_SERVER_BASE_DIR"
_DEFAULT_BASE_DIR = "/home/user"
_DISABLED_GROUPS_ENV_VAR = "EBX_SERVER_DISABLED_GROUPS"

#: Default operation class per path-bearing endpoint.
DEFAULT_OPS: dict[str, str] = {
    "upload": OP_WRITE,
    "files_mkdir": OP_WRITE,
    "files_upload_stream": OP_WRITE,
    "files_delete": OP_DELETE,
    "files_move": OP_DELETE,
    "shell": OP_EXEC,
    "shell_stream": OP_EXEC,
    "process_start": OP_EXEC,
}

#: Endpoints that are not HTTP routes but are governed by the policy (PTY WebSocket).
_VIRTUAL_ENDPOINTS: dict[str, tuple[str, str, CapabilityGroup]] = {
    "pty_connect": ("WS", "/pty", CapabilityGroup.TERMINAL),
}

_SECRET_ENV_NAMES = ("EBX_SERVER_TOKEN", "EBX_SERVER_POLICY", "EBX_SERVER_POLICY_FILE")


@dataclasses.dataclass(frozen=True)
class EffectiveRule:
    """The fully merged rule for one endpoint."""

    endpoint: str
    enabled: bool = True
    scopes: tuple[str, ...] = ()
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    read_only: bool = False
    symlinks: str = "within"
    limits: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    params: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    audit: str = "deny"


def apply_groups(table: RouteTable, policy: ServerPolicy) -> None:
    """Apply the policy's group toggles to *table* (``EBX_SERVER_DISABLED_GROUPS`` wins)."""
    env_disabled = {
        part.strip()
        for part in os.environ.get(_DISABLED_GROUPS_ENV_VAR, "").split(",")
        if part.strip()
    }
    for name, enabled in policy.preset_groups().items():
        group = CapabilityGroup(name)
        if group == CapabilityGroup.CORE:
            continue
        if enabled and name not in env_disabled:
            table.enable_group(group)
        elif not enabled:
            table.disable_group(group)


class _Bucket:
    __slots__ = ("capacity", "rate", "stamp", "tokens")

    def __init__(self, per_minute: int) -> None:
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self.tokens = self.capacity
        self.stamp = time.monotonic()

    def take(self) -> float:
        """Take one token; return 0.0 on success or seconds until one is available."""
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.stamp) * self.rate)
        self.stamp = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        return (1.0 - self.tokens) / self.rate


class EndpointContext:
    """Per-request view of the policy handed to handlers (``request.context['policy']``)."""

    def __init__(self, engine: PolicyEngine, rule: EffectiveRule, identity: Identity) -> None:
        self.engine = engine
        self.rule = rule
        self.identity = identity
        self.endpoint = rule.endpoint
        self.paths_touched: list[str] = []

    def base_dir(self) -> str:
        """Effective boundary root when ``paths.allow`` is unset."""
        return self.engine.policy.base_dir or os.environ.get(_BASE_DIR_ENV_VAR) or _DEFAULT_BASE_DIR

    def guard(self) -> PathGuard:
        """Build the :class:`PathGuard` for this endpoint."""
        rule = self.rule
        return PathGuard(
            self.base_dir(),
            allow=rule.allow,
            deny=rule.deny,
            read_only=rule.read_only,
            symlinks=rule.symlinks,
            relative_to_root=bool(rule.allow),
        )

    def resolve_path(self, raw: object, op: str | None = None, *, field: str = "") -> str:
        """Resolve and authorise *raw*; records the resolved path for the audit log."""
        resolved = self.guard().resolve(
            raw, op or DEFAULT_OPS.get(self.endpoint, OP_READ), field=field
        )
        if len(self.paths_touched) < 8:
            self.paths_touched.append(resolved[:512])
        return resolved

    def limit(self, key: str, default: Any = None) -> Any:
        """Return the configured limit *key* or *default*."""
        return self.rule.limits.get(key, default)

    def param(self, key: str, default: Any = None) -> Any:
        """Return the configured param *key* or *default*."""
        return self.rule.params.get(key, default)

    def require_scope(self, scope: str) -> None:
        """Raise ``missing_scope`` unless the identity holds *scope* (custom commands)."""
        if not self.identity.can(scope):
            raise PolicyDenied(
                "missing_scope",
                f"Missing required scope {scope!r}",
                endpoint=self.endpoint,
                scope=scope,
            )


class _Release:
    """Concurrency slot released when the response is fully written."""

    def __init__(self, fn: Callable[[], None] | None) -> None:
        self._fn = fn

    def __call__(self) -> None:
        fn, self._fn = self._fn, None
        if fn is not None:
            fn()


class PolicyEngine:
    """A :class:`ServerPolicy` bound to a route table (immutable after construction)."""

    def __init__(
        self,
        policy: ServerPolicy,
        table: RouteTable,
        *,
        legacy_token: str | None = None,
        registry: Any = None,
    ) -> None:
        self.policy = policy
        self.table = table
        self.registry = registry
        self._routes: dict[str, RouteInfo] = {}
        for route in table._routes:
            self._routes.setdefault(route.name, route)
        for name, (method, pattern, group) in _VIRTUAL_ENDPOINTS.items():
            self._routes.setdefault(
                name,
                RouteInfo(method, pattern, lambda _r: None, group, name=name, streaming=True),
            )
        self._rules: dict[str, EffectiveRule] = {}
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._inflight: dict[tuple[str, str], int] = {}
        self._audit_log = logging.getLogger(AUDIT_LOGGER)
        self.secret_env_names: set[str] = set(_SECRET_ENV_NAMES)
        self._tokens: list[tuple[str, frozenset[str], bytes]] = []
        self._legacy: tuple[Identity, bytes] | None = None
        self._setup_auth(legacy_token)
        self._compile_rules()

    # -- authentication ------------------------------------------------- #

    def _setup_auth(self, legacy_token: str | None) -> None:
        auth = self.policy.auth
        for entry in auth.get("tokens", []):
            if "token_env" in entry:
                value = os.environ.get(entry["token_env"], "")
                if not value:
                    raise PolicyConfigError(
                        f"policy.auth.tokens[{entry['id']}]: environment variable "
                        f"{entry['token_env']!r} is not set"
                    )
                digest = hashlib.sha256(value.encode()).digest()
                self.secret_env_names.add(entry["token_env"])
            else:
                digest = bytes.fromhex(entry["token_sha256"])
            self._tokens.append((entry["id"], frozenset(entry["scopes"]), digest))
        if legacy_token:
            scopes = frozenset(auth.get("legacy_scopes", ["*"]))
            self._legacy = (
                Identity("legacy", scopes),
                hashlib.sha256(legacy_token.encode()).digest(),
            )
        self._auth_required = bool(self._tokens) or self._legacy is not None
        self._anonymous: Identity | None = None
        if not self._auth_required or auth.get("allow_anonymous"):
            scopes = frozenset(auth.get("anonymous_scopes", ["*"]))
            self._anonymous = Identity("anonymous", scopes)

    @property
    def uses_identities(self) -> bool:
        """Whether per-identity tokens are configured (enables env scrubbing, etc.)."""
        return bool(self._tokens)

    def authenticate(self, headers: Any) -> Identity | None:
        """Return the caller's identity, or ``None`` for 401.

        Raises:
            PolicyDenied: ``ambiguous_credentials`` (400) for conflicting credential headers.
        """
        access = _header_values(headers, "X-Access-Token")
        if len(set(access)) > 1:
            raise PolicyDenied(
                "ambiguous_credentials",
                "Multiple distinct credential headers",
                status=400,
                error_type="ValueError",
            )
        candidates: list[str] = []
        for value in _header_values(headers, "Authorization"):
            scheme, _, rest = value.partition(" ")
            if scheme.lower() == "bearer" and rest.strip():
                candidates.append(rest.strip())
        candidates.extend(v for v in access if v)
        if not candidates:
            return self._anonymous if self._anonymous is not None else None
        for candidate in candidates:
            identity = self._match_token(candidate)
            if identity is not None:
                return identity
        return None

    def _match_token(self, presented: str) -> Identity | None:
        digest = hashlib.sha256(presented.encode()).digest()
        found: Identity | None = None
        for ident, scopes, expected in self._tokens:
            if hmac.compare_digest(digest, expected) and found is None:
                found = Identity(ident, scopes)
        if (
            self._legacy is not None
            and hmac.compare_digest(digest, self._legacy[1])
            and found is None
        ):
            found = self._legacy[0]
        return found

    # -- rule resolution ------------------------------------------------ #

    def _spec_for(self, route: RouteInfo) -> EndpointSpec:
        spec = ENDPOINT_CATALOG.get(route.name)
        if spec is not None:
            return spec
        scopes = tuple(getattr(route, "scopes", ()) or ())
        return EndpointSpec(scopes=scopes, limits=_COMMON_LIMITS)

    def _compile_rules(self) -> None:
        self.default_audit = "deny"
        for sel, _src, rule in self.policy.layers():
            if sel == DEFAULTS_SELECTOR and "audit" in rule:
                self.default_audit = rule["audit"]
        layers = [(sel, src, rule, _selector_kind(sel)) for sel, src, rule in self.policy.layers()]
        for sel, _src, _rule, kind in layers:
            if kind == 3 and sel not in self._routes:
                import difflib

                near = difflib.get_close_matches(sel, list(self._routes), n=1)
                hint = f" (did you mean {near[0]!r}?)" if near else ""
                raise PolicyConfigError(f"policy.endpoints.{sel}: unknown endpoint{hint}")
            if kind == 1 and sel[6:] not in {g.value for g in CapabilityGroup}:
                raise PolicyConfigError(f"policy.endpoints.{sel}: unknown group")
        order = sorted(
            range(len(layers)),
            key=lambda i: (layers[i][3], layers[i][1], len(layers[i][0].split("*")[0]), i),
        )
        for name, route in self._routes.items():
            spec = self._spec_for(route)
            self._rules[name] = self._merge(name, route, spec, [layers[i] for i in order])

    def _merge(
        self,
        name: str,
        route: RouteInfo,
        spec: EndpointSpec,
        ordered: list[tuple[str, int, dict[str, Any], int]],
    ) -> EffectiveRule:
        scopes: tuple[str, ...] = spec.scopes
        enabled = True
        allow: tuple[str, ...] = ()
        deny: list[str] = []
        read_only = False
        symlinks = "within"
        limits: dict[str, Any] = {}
        params: dict[str, Any] = {}
        audit = "deny"
        buckets: dict[tuple[int, int], list[bool]] = {}
        order_keys: list[tuple[int, int]] = []
        for sel, src, rule, kind in ordered:
            if not selector_matches(sel, name, route.group.value):
                continue
            exact = kind == 3
            if "enabled" in rule:
                key = (kind, src)
                if key not in buckets:
                    buckets[key] = []
                    order_keys.append(key)
                buckets[key].append(rule["enabled"])
            if "scopes" in rule:
                scopes = tuple(rule["scopes"])
            if "audit" in rule:
                audit = rule["audit"]
            if "paths" in rule:
                self._check_applicable(exact, sel, "paths", spec.paths, name)
                if spec.paths:
                    p = rule["paths"]
                    if "allow" in p:
                        allow = tuple(p["allow"])
                    deny.extend(x for x in p.get("deny", []) if x not in deny)
                    read_only = p.get("read_only", read_only)
                    symlinks = p.get("symlinks", symlinks)
            for section, target, allowed_keys in (
                ("limits", limits, spec.limits),
                ("params", params, spec.params),
            ):
                for key, value in rule.get(section, {}).items():
                    if key not in allowed_keys:
                        self._check_applicable(exact, sel, f"{section}.{key}", False, name)
                        continue
                    if section == "params" and key in _UNION_PARAMS:
                        merged = list(target.get(key, []))
                        merged.extend(v for v in value if v not in merged)
                        target[key] = merged
                    else:
                        target[key] = value
        for key in order_keys:
            values = buckets[key]
            enabled = False not in values
        if name in CORE_ENDPOINTS:
            enabled = True
        return EffectiveRule(
            endpoint=name,
            enabled=enabled,
            scopes=scopes,
            allow=allow,
            deny=tuple(deny),
            read_only=read_only,
            symlinks=symlinks,
            limits=limits,
            params=params,
            audit=audit,
        )

    @staticmethod
    def _check_applicable(exact: bool, selector: str, what: str, ok: bool, endpoint: str) -> None:
        if exact and not ok:
            raise PolicyConfigError(
                f"policy.endpoints.{selector}.{what}: not applicable to endpoint {endpoint!r}"
            )

    def rule_for(self, endpoint: str) -> EffectiveRule:
        """Return the effective rule for *endpoint* (permissive default for unknown names)."""
        return self._rules.get(endpoint) or EffectiveRule(endpoint=endpoint)

    # -- admission ------------------------------------------------------ #

    def admit(self, route: RouteInfo, identity: Identity) -> tuple[EndpointContext, _Release]:
        """Run the rule gate (enabled, scopes, rate, concurrency) for *route*.

        Raises:
            PolicyDenied: with status 404/403/429.
        """
        rule = self.rule_for(route.name)
        if not rule.enabled:
            raise PolicyDenied(
                "endpoint_disabled",
                f"Endpoint {route.name!r} is disabled",
                status=404,
                endpoint=route.name,
                error_type="ValueError",
            )
        for scope in rule.scopes:
            if not identity.can(scope):
                raise PolicyDenied(
                    "missing_scope",
                    f"Missing required scope {scope!r}",
                    endpoint=route.name,
                    scope=scope,
                )
        release = self._take_slots(identity.id, rule)
        return EndpointContext(self, rule, identity), release

    def _take_slots(self, identity_id: str, rule: EffectiveRule) -> _Release:
        key = (identity_id, rule.endpoint)
        per_minute = rule.limits.get("rate_per_minute")
        max_conc = rule.limits.get("max_concurrency")
        with self._lock:
            if per_minute:
                bucket = self._buckets.get(key)
                if bucket is None:
                    bucket = self._buckets[key] = _Bucket(int(per_minute))
                wait = bucket.take()
                if wait > 0:
                    raise PolicyDenied(
                        "rate_limited",
                        "Rate limit exceeded",
                        status=429,
                        endpoint=rule.endpoint,
                        error_type="RateLimited",
                        retry_after=max(1, int(wait + 0.999)),
                    )
            if max_conc:
                if self._inflight.get(key, 0) >= int(max_conc):
                    raise PolicyDenied(
                        "concurrency_limited",
                        "Too many concurrent requests",
                        status=429,
                        endpoint=rule.endpoint,
                        error_type="RateLimited",
                        retry_after=1,
                    )
                self._inflight[key] = self._inflight.get(key, 0) + 1
                return _Release(lambda: self._free(key))
        return _Release(None)

    def _free(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._inflight[key] = max(0, self._inflight.get(key, 0) - 1)

    # -- audit ----------------------------------------------------------- #

    def audit(
        self,
        *,
        rule: EffectiveRule | None,
        identity: Identity | None,
        endpoint: str,
        method: str,
        status: int,
        code: str = "",
        paths: list[str] | None = None,
    ) -> None:
        """Emit one JSON audit line when the rule's ``audit`` mode asks for it."""
        mode = rule.audit if rule is not None else self.default_audit
        denied = status in (401, 403, 404, 413, 429) or bool(code)
        if mode == "off" or (mode == "deny" and not denied):
            return
        event = {
            "ts": round(time.time(), 3),
            "identity": identity.id if identity else None,
            "endpoint": endpoint,
            "method": method,
            "decision": "deny" if denied else "allow",
            "status": status,
            "code": code or None,
            "paths": [p[:512] for p in (paths or [])][:8],
        }
        self._audit_log.info(json.dumps(event, separators=(",", ":")))

    # -- discovery -------------------------------------------------------- #

    def _entry(self, route: RouteInfo, identity: Identity) -> dict[str, Any]:
        rule = self.rule_for(route.name)
        group_on = self.table.is_group_enabled(route.group)
        reason: str | None = None
        if not group_on:
            reason = "group_disabled"
        elif not rule.enabled:
            reason = "endpoint_disabled"
        else:
            for scope in rule.scopes:
                if not identity.can(scope):
                    reason = "missing_scope"
                    break
        allowed = reason is None
        entry: dict[str, Any] = {
            "method": route.method,
            "path": route.path_pattern,
            "group": route.group.value,
            "streaming": route.streaming,
            "enabled": group_on and rule.enabled,
            "allowed": allowed,
            "reason": reason,
            "scopes": list(rule.scopes),
        }
        if allowed:
            entry["limits"] = dict(rule.limits)
            entry["params"] = {k: v for k, v in rule.params.items()}
            if self._spec_for(route).paths:
                entry["paths"] = {
                    "allow": list(rule.allow),
                    "read_only": rule.read_only,
                    "deny_count": len(rule.deny),
                    "symlinks": rule.symlinks,
                }
        return entry

    def describe(self, identity: Identity) -> dict[str, Any]:
        """Return the discovery v2 document for *identity*."""
        endpoints = {name: self._entry(route, identity) for name, route in self._routes.items()}
        warnings: list[str] = []
        if "*" in identity.scopes and self.uses_identities:
            warnings.append("identity holds the wildcard scope '*'")
        return {
            "api_version": 2,
            "server_version": __version__,
            "groups": self.table.list_groups(),
            "identity": {"id": identity.id, "scopes": sorted(identity.scopes)},
            "policy": {
                "preset": self.policy.preset_name,
                "revision": self.policy.revision,
                "configured": True,
            },
            "endpoints": endpoints,
            "warnings": warnings,
        }

    def check(
        self,
        identity: Identity,
        endpoint: str,
        *,
        path: str | None = None,
        paths: list[str] | None = None,
        op: str | None = None,
    ) -> dict[str, Any]:
        """Return the authoritative decision for a hypothetical call (no I/O beyond realpath)."""
        route = self._routes.get(endpoint)
        if route is None:
            return {
                "endpoint": endpoint,
                "allowed": False,
                "code": "unknown_endpoint",
                "reason": "Unknown endpoint",
            }
        entry = self._entry(route, identity)
        if not entry["allowed"]:
            code = {"group_disabled": "endpoint_disabled"}.get(entry["reason"], entry["reason"])
            return {"endpoint": endpoint, "allowed": False, "code": code, "reason": entry["reason"]}
        rule = self.rule_for(endpoint)
        ctx = EndpointContext(self, rule, identity)
        to_check = list(paths or [])
        if path is not None:
            to_check.insert(0, path)
        for raw in to_check:
            try:
                ctx.resolve_path(raw, op)
            except PolicyDenied as exc:
                return {
                    "endpoint": endpoint,
                    "allowed": False,
                    "code": exc.code,
                    "reason": exc.message,
                }
        return {"endpoint": endpoint, "allowed": True, "code": None, "reason": None}

    def explain(
        self,
        endpoint: str,
        *,
        scopes: list[str] | None = None,
        path: str | None = None,
        op: str | None = None,
    ) -> dict[str, Any]:
        """Debug aid: decision for a synthetic identity holding *scopes* (default ``*``)."""
        identity = Identity("explain", frozenset(scopes if scopes is not None else ["*"]))
        return self.check(identity, endpoint, path=path, op=op)

    # -- environment hygiene --------------------------------------------- #

    def child_env(self) -> dict[str, str] | None:
        """Environment for child processes; ``None`` means "inherit" (unconfigured mode)."""
        if not self.uses_identities:
            return None
        return {k: v for k, v in os.environ.items() if k not in self.secret_env_names}

    def is_secret_env(self, name: str) -> bool:
        """Whether *name* must never be exposed through ``/env``."""
        return name in self.secret_env_names or name.upper().startswith("EBX_SERVER_")

    # -- lint --------------------------------------------------------------- #

    def lint(self) -> list[str]:
        """Return human-readable configuration warnings."""
        warnings: list[str] = []
        identities: list[Identity] = [Identity(i, s) for i, s, _ in self._tokens]
        if self._legacy:
            identities.append(self._legacy[0])
        if self._anonymous:
            identities.append(self._anonymous)
        scoped = [
            n
            for n, r in self._rules.items()
            if r.enabled
            and (r.allow or r.deny or r.read_only or r.symlinks == "never")
            and ENDPOINT_CATALOG.get(n, EndpointSpec()).paths
        ]
        execs = [
            n
            for n, r in self._rules.items()
            if r.enabled
            and ENDPOINT_CATALOG.get(n, EndpointSpec()).exec
            and self.table.is_group_enabled(self._routes[n].group)
        ]
        for ident in identities:
            reach_scoped = [n for n in scoped if all(ident.can(s) for s in self._rules[n].scopes)]
            reach_exec = [n for n in execs if all(ident.can(s) for s in self._rules[n].scopes)]
            if reach_scoped and reach_exec:
                warnings.append(
                    f"L1: identity {ident.id!r} can use path-scoped endpoints "
                    f"({', '.join(sorted(reach_scoped)[:3])}...) and also execute programs via "
                    f"{', '.join(sorted(reach_exec)[:3])}; path rules can be bypassed"
                )
        for name, rule in self._rules.items():
            if any(os.path.normpath(a) == os.sep for a in rule.allow):
                warnings.append(f"L2: endpoint {name!r} allows the filesystem root '/'")
            if rule.params.get("overwrite") is False and not rule.allow:
                warnings.append(f"L4: endpoint {name!r} sets overwrite=false without paths.allow")
        if self._tokens and any("*" in s for _, s, _ in self._tokens) and len(self._tokens) > 1:
            warnings.append("L3: a wildcard-scope token coexists with other tokens")
        return sorted(set(warnings))


def _header_values(headers: Any, name: str) -> list[str]:
    """Return every value of header *name* from an ``http.client.HTTPMessage`` or dict."""
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        return [str(v) for v in (get_all(name) or [])]
    lowered = name.lower()
    return [str(v) for k, v in dict(headers).items() if k.lower() == lowered]


def context_of(request: Any) -> EndpointContext | None:
    """Return the :class:`EndpointContext` attached to *request*, if any."""
    ctx = request.context.get("policy") if getattr(request, "context", None) else None
    return ctx if isinstance(ctx, EndpointContext) else None


def child_env(request: Any) -> dict[str, str] | None:
    """Environment for subprocesses started on behalf of *request* (``None`` = inherit)."""
    ctx = context_of(request)
    return ctx.engine.child_env() if ctx is not None else None


def check_scope(identity: Identity, scopes: tuple[str, ...]) -> bool:
    """Return whether *identity* holds every scope in *scopes*."""
    return all(scope_granted(identity.scopes, s) for s in scopes)
