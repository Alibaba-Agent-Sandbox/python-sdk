"""Policy enforcement runtime: binds a :class:`ServerPolicy` to a :class:`RouteTable`.

The :class:`PolicyEngine` resolves one :class:`EffectiveRule` per route, authenticates
callers into :class:`~agent_sandbox.server.policy.Identity` objects, applies rate and
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
from .endpoints import CORE_ENDPOINTS, ENDPOINTS, CapabilityGroup, EndpointSpec
from .guard import OP_DELETE, OP_EXEC, OP_READ, OP_WRITE, PathGuard
from .policy import (
    _UNION_PARAMS,
    DEFAULTS_SELECTOR,
    ENABLED_GROUPS_ENV_VAR,
    RANK_CODE,
    RANK_ENV,
    Identity,
    Layer,
    PolicyConfigError,
    PolicyDenied,
    ServerPolicy,
    _selector_kind,
    alias_layers,
    baseline_layers,
    parse_group_list,
    scope_granted,
    selector_matches,
)
from .router import RouteInfo

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from .router import RouteTable

__all__ = [
    "EffectiveRule",
    "EndpointContext",
    "PolicyEngine",
    "child_env",
    "context_of",
]

AUDIT_LOGGER = "agent_sandbox.server.audit"
_BASE_DIR_ENV_VAR = "ABX_SERVER_BASE_DIR"
_DEFAULT_BASE_DIR = "/home/user"

#: Default operation class per path-bearing endpoint.
DEFAULT_OPS: dict[str, str] = {
    "files_mkdir": OP_WRITE,
    "files_upload_stream": OP_WRITE,
    "files_delete": OP_DELETE,
    "files_move": OP_DELETE,
    "shell": OP_EXEC,
    "shell_stream": OP_EXEC,
    "process_start": OP_EXEC,
}

_SECRET_ENV_NAMES = ("ABX_SERVER_TOKEN", "ABX_SERVER_POLICY", "ABX_SERVER_POLICY_FILE")


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
    #: Origin of the layer that disabled the endpoint (``policy:groups.process``); empty if enabled.
    disabled_by: str = ""

    def disabled_message(self) -> str:
        """Human-readable reason this endpoint answers 404, naming the rule that decided."""
        origin = self.disabled_by or "policy"
        if origin.startswith("default:opt-in:"):
            group = origin.rsplit(":", 1)[1]
            return (
                f"Endpoint {self.endpoint!r} is disabled: group {group!r} is opt-in. Enable the "
                f"group (ABX_SERVER_ENABLED_GROUPS={group}, policy groups: [{group}]) or this "
                f"endpoint (policy endpoints.{self.endpoint}.enabled: true)"
            )
        return f"Endpoint {self.endpoint!r} is disabled by rule {origin}"


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
        from .guards.paths import path_guard_from_context

        resolved = path_guard_from_context(self).resolve(
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
    """The one decision source of a server: a :class:`ServerPolicy` bound to a route table.

    Rules are compiled per endpoint from every input (built-in defaults, the table's
    ``enable_group`` / ``disable_group`` calls, the preset, the policy document and
    ``ABX_SERVER_ENABLED_GROUPS``) and recompiled when the table changes.  Groups exist only as
    selectors inside that one rule set.
    """

    def __init__(
        self,
        policy: ServerPolicy,
        table: RouteTable,
        *,
        registry: Any = None,
        enabled_groups: str | None = None,
    ) -> None:
        self.policy = policy
        self.table = table
        self.registry = registry
        env_groups = (
            enabled_groups
            if enabled_groups is not None
            else os.environ.get(ENABLED_GROUPS_ENV_VAR, "")
        )
        self._env_groups: list[str] = parse_group_list(env_groups)
        self._compiled: tuple[int, dict[str, RouteInfo], dict[str, EffectiveRule]] | None = None
        self._compile_lock = threading.Lock()
        self.default_audit = "deny"
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._inflight: dict[tuple[str, str], int] = {}
        self._audit_log = logging.getLogger(AUDIT_LOGGER)
        self.secret_env_names: set[str] = set(_SECRET_ENV_NAMES)
        self._tokens: list[tuple[str, frozenset[str], bytes]] = []
        self._setup_auth()
        self._compile(strict=True)

    @property
    def _routes(self) -> dict[str, RouteInfo]:
        """Every governed endpoint by ID: mounted routes plus virtual ones (PTY WebSocket)."""
        return self._current()[0]

    @property
    def _rules(self) -> dict[str, EffectiveRule]:
        return self._current()[1]

    def _current(self) -> tuple[dict[str, RouteInfo], dict[str, EffectiveRule]]:
        compiled = self._compiled
        if compiled is None or compiled[0] != self.table.revision:
            compiled = self._compile(strict=False)
        return compiled[1], compiled[2]

    # -- authentication ------------------------------------------------- #

    def _setup_auth(self) -> None:
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
        self._auth_required = bool(self._tokens)
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
        # No server token is configured. A presented value that matches
        # nothing is not a login: callers sometimes send the gateway
        # ``X-Access-Token``, which this process does not own.
        if not self._auth_required and self._anonymous is not None:
            return self._anonymous
        return None

    def _match_token(self, presented: str) -> Identity | None:
        digest = hashlib.sha256(presented.encode()).digest()
        found: Identity | None = None
        for ident, scopes, expected in self._tokens:
            if hmac.compare_digest(digest, expected) and found is None:
                found = Identity(ident, scopes)
        return found

    # -- rule resolution ------------------------------------------------ #

    def _layers(self) -> list[Layer]:
        """Every rule layer, lowest rank first: defaults, code, preset, policy, environment."""
        layers = baseline_layers()
        layers += alias_layers(
            {g: on for g, on in self.table.group_overrides.items()}, RANK_CODE, "code:enable_group"
        )
        layers += self.policy.layers()
        layers += alias_layers(
            dict.fromkeys(self._env_groups, True), RANK_ENV, "env:" + ENABLED_GROUPS_ENV_VAR
        )
        return layers

    def _compile(
        self, *, strict: bool
    ) -> tuple[int, dict[str, RouteInfo], dict[str, EffectiveRule]]:
        with self._compile_lock:
            revision = self.table.revision
            if self._compiled is not None and self._compiled[0] == revision:
                return self._compiled
            routes: dict[str, RouteInfo] = {}
            for route in self.table._routes:
                routes.setdefault(route.name, route)
            for endpoint in ENDPOINTS.values():
                if endpoint.virtual:
                    routes.setdefault(
                        endpoint.name,
                        RouteInfo(
                            endpoint.method,
                            endpoint.path,
                            lambda _r: None,
                            endpoint.group,
                            name=endpoint.name,
                            streaming=True,
                            spec=endpoint.spec,
                            summary=endpoint.summary,
                        ),
                    )
            layers = self._layers()
            default_audit = "deny"
            for layer in layers:
                if layer.selector == DEFAULTS_SELECTOR and "audit" in layer.rule:
                    default_audit = layer.rule["audit"]
            kinds = [_selector_kind(layer.selector) for layer in layers]
            if strict:
                self._validate(layers, kinds, routes)
            order = sorted(
                range(len(layers)),
                key=lambda i: (
                    kinds[i],
                    layers[i].rank,
                    len(layers[i].selector.split("*")[0]),
                    i,
                ),
            )
            ordered = [(layers[i], kinds[i]) for i in order]
            rules = {
                name: self._merge(name, route, route.spec, ordered, strict)
                for name, route in routes.items()
            }
            self.default_audit = default_audit
            self._compiled = (revision, routes, rules)
            return self._compiled

    @staticmethod
    def _validate(layers: list[Layer], kinds: list[int], routes: dict[str, RouteInfo]) -> None:
        for layer, kind in zip(layers, kinds, strict=True):
            sel = layer.selector
            if kind == 3 and sel not in routes:
                import difflib

                near = difflib.get_close_matches(sel, list(routes), n=1)
                hint = f" (did you mean {near[0]!r}?)" if near else ""
                raise PolicyConfigError(f"policy.endpoints.{sel}: unknown endpoint{hint}")
            if kind == 1 and sel[6:] not in {g.value for g in CapabilityGroup}:
                raise PolicyConfigError(f"policy.endpoints.{sel}: unknown group")

    def _merge(
        self,
        name: str,
        route: RouteInfo,
        spec: EndpointSpec,
        ordered: list[tuple[Layer, int]],
        strict: bool,
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
        buckets: dict[tuple[int, int], list[tuple[bool, str]]] = {}
        order_keys: list[tuple[int, int]] = []
        for layer, kind in ordered:
            sel, rule = layer.selector, layer.rule
            if not selector_matches(sel, name, route.group.value):
                continue
            exact = kind == 3 and strict
            if "enabled" in rule:
                key = (kind, layer.rank)
                if key not in buckets:
                    buckets[key] = []
                    order_keys.append(key)
                buckets[key].append((rule["enabled"], layer.origin))
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
        disabled_by = ""
        for key in order_keys:
            votes = buckets[key]
            enabled = all(vote for vote, _origin in votes)
            disabled_by = "" if enabled else next(o for vote, o in votes if not vote)
        if name in CORE_ENDPOINTS:
            enabled, disabled_by = True, ""
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
            disabled_by=disabled_by,
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
                rule.disabled_message(),
                status=404,
                endpoint=route.name,
                error_type="ValueError",
                rule=rule.disabled_by,
            )
        for scope in rule.scopes:
            if not identity.can(scope):
                raise PolicyDenied(
                    "missing_scope",
                    f"Identity {identity.id!r} lacks scope {scope!r} required by endpoint "
                    f"{route.name!r}",
                    endpoint=route.name,
                    scope=scope,
                    identity=identity.id,
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
        reason: str | None = None
        if not rule.enabled:
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
            "summary": route.summary,
            "streaming": route.streaming,
            "enabled": rule.enabled,
            "allowed": allowed,
            "reason": reason,
            "rule": rule.disabled_by or None,
            "scopes": list(rule.scopes),
        }
        if allowed:
            entry["limits"] = dict(rule.limits)
            entry["params"] = {k: v for k, v in rule.params.items()}
            if route.spec.paths:
                entry["paths"] = {
                    "allow": list(rule.allow),
                    "read_only": rule.read_only,
                    "deny_count": len(rule.deny),
                    "symlinks": rule.symlinks,
                }
        return entry

    def group_summary(self) -> dict[str, dict[str, int]]:
        """Per group: how many of its endpoints are enabled (a derived view, not a switch)."""
        totals: dict[str, list[int]] = {g.value: [0, 0] for g in CapabilityGroup}
        rules = self._rules
        for name, route in self._routes.items():
            counts = totals[route.group.value]
            counts[1] += 1
            if rules[name].enabled:
                counts[0] += 1
        return {g: {"enabled": on, "total": total} for g, (on, total) in totals.items()}

    def groups(self) -> dict[str, bool]:
        """``{group: any endpoint of the group is enabled}`` (``core`` is always on)."""
        return {g: c["total"] == 0 or c["enabled"] > 0 for g, c in self.group_summary().items()}

    def group_enabled(self, group: CapabilityGroup) -> bool:
        """Whether at least one endpoint of *group* is enabled."""
        return self.groups()[group.value]

    def describe(self, identity: Identity) -> dict[str, Any]:
        """Return the discovery document for *identity*."""
        endpoints = {name: self._entry(route, identity) for name, route in self._routes.items()}
        warnings: list[str] = []
        if "*" in identity.scopes and self.uses_identities:
            warnings.append("identity holds the wildcard scope '*'")
        return {
            "api_version": 2,
            "server_version": __version__,
            "groups": self.groups(),
            "group_summary": self.group_summary(),
            "identity": {"id": identity.id, "scopes": sorted(identity.scopes)},
            "policy": {
                "preset": self.policy.preset_name,
                "revision": self.policy.revision,
                "configured": self.policy.configured,
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
            rule = self.rule_for(endpoint)
            reason = (
                rule.disabled_message()
                if entry["reason"] == "endpoint_disabled"
                else f"Identity {identity.id!r} lacks a scope required by endpoint {endpoint!r}"
            )
            return {
                "endpoint": endpoint,
                "allowed": False,
                "code": entry["reason"],
                "reason": reason,
                "rule": entry["rule"],
            }
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
        return name in self.secret_env_names or name.upper().startswith("ABX_SERVER_")

    # -- lint --------------------------------------------------------------- #

    def lint(self) -> list[str]:
        """Return human-readable configuration warnings."""
        warnings: list[str] = []
        identities: list[Identity] = [Identity(i, s) for i, s, _ in self._tokens]
        if self._anonymous:
            identities.append(self._anonymous)
        scoped = [
            n
            for n, r in self._rules.items()
            if r.enabled
            and (r.allow or r.deny or r.read_only or r.symlinks == "never")
            and self._routes[n].spec.paths
        ]
        execs = [n for n, r in self._rules.items() if r.enabled and self._routes[n].spec.exec]
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


def context_of(request: Any) -> EndpointContext:
    """Return the :class:`EndpointContext` the pipeline attached to *request*."""
    ctx = request.context.get("policy") if getattr(request, "context", None) else None
    if not isinstance(ctx, EndpointContext):
        raise RuntimeError("request has no policy context; route handlers run behind the pipeline")
    return ctx


def child_env(request: Any) -> dict[str, str] | None:
    """Environment for subprocesses started on behalf of *request* (``None`` = inherit)."""
    return context_of(request).engine.child_env()


def check_scope(identity: Identity, scopes: tuple[str, ...]) -> bool:
    """Return whether *identity* holds every scope in *scopes*."""
    return all(scope_granted(identity.scopes, s) for s in scopes)
