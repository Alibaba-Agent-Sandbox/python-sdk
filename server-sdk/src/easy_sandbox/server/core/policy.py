"""``Policy``: the decision source of the operation pipeline.

In stage S1 there is exactly one decision engine, the in-flight
:class:`~easy_sandbox.server.runtime.PolicyEngine` that the v1 dispatcher already consults.
``Policy.from_engine`` wraps it so the v1 dispatcher and ``POST /ops/{id}`` are answered by the
same rules, scopes, rate buckets and concurrency slots.  Without an engine the v1 behaviour is
reproduced: authentication by the legacy token and the capability-group gate.

The allow/deny rule model of design 03 (selectors, scopes, presets, hooks) is a later work
package (WP-2); this class deliberately has no ``allow``/``deny`` builders yet.
"""

from __future__ import annotations

import dataclasses
import hmac
from typing import TYPE_CHECKING, Any

from ..policy import Identity, PolicyDenied
from ..router import CapabilityGroup
from .context import Principal

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..router import RouteInfo, RouteTable
    from ..runtime import EffectiveRule, EndpointContext, PolicyEngine
    from .registry import Operation

__all__ = ["Admission", "OpNotEnabled", "Policy", "Verdict"]

#: Native operations (no v1 route behind them) that every authenticated caller may use.
#: Any other native operation stays unmounted until the v2 rule model lands (WP-2): the legacy
#: engine has no rule for it, so mounting it would bypass policy.
NATIVE_OPEN_IDS = frozenset({"core.describe"})


class OpNotEnabled(Exception):  # noqa: N818  (mirrors PolicyDenied naming)
    """The operation is unknown, disabled or not granted: always one 404 ``op.not_enabled``."""

    def __init__(self, op_id: str) -> None:
        super().__init__(op_id)
        self.op_id = op_id


@dataclasses.dataclass(frozen=True)
class Verdict:
    """Side-effect-free answer to "may this principal use this operation?"."""

    allowed: bool
    reason: str | None = None


@dataclasses.dataclass
class Admission:
    """A granted call: the endpoint context (engine mode) and the slot to release."""

    ctx: EndpointContext | None = None
    release: Callable[[], None] | None = None

    def close(self) -> None:
        """Release the concurrency slot (idempotent)."""
        release, self.release = self.release, None
        if release is not None:
            release()


class Policy:
    """Decides, for one server, which principal may call which operation."""

    def __init__(
        self,
        table: RouteTable,
        engine: PolicyEngine | None = None,
        *,
        auth_token: str | None = None,
    ) -> None:
        self.table = table
        self.engine = engine
        self.auth_token = auth_token

    @classmethod
    def from_engine(cls, engine: PolicyEngine) -> Policy:
        """Bridge the in-flight ``PolicyEngine``: one decision source answers both dispatchers."""
        return cls(engine.table, engine)

    @classmethod
    def open(cls, table: RouteTable, *, auth_token: str | None = None) -> Policy:
        """The v1 behaviour with no policy: legacy token (if any) plus the group gate."""
        return cls(table, None, auth_token=auth_token)

    @property
    def configured(self) -> bool:
        """Whether a policy engine is active."""
        return self.engine is not None

    # -- authentication --------------------------------------------------- #

    def authenticate(self, headers: Any) -> Principal | None:
        """Credentials -> principal, ``None`` for 401.  May raise :class:`PolicyDenied` (400)."""
        if self.engine is not None:
            identity = self.engine.authenticate(headers)
            return _principal(identity) if identity is not None else None
        if self.auth_token is None:
            return Principal.anonymous()
        presented = _credentials(headers)
        if presented is None or not hmac.compare_digest(presented, self.auth_token):
            return None
        return Principal(id="token", roles=("admin",), scopes=frozenset({"*"}))

    # -- decisions --------------------------------------------------------- #

    def _group(self, operation: Operation) -> CapabilityGroup | None:
        if operation.group is None:
            return None
        try:
            return CapabilityGroup(operation.group)
        except ValueError:
            return None

    def _rule(self, operation: Operation) -> EffectiveRule | None:
        if self.engine is None or operation.legacy_route is None:
            return None
        return self.engine.rule_for(operation.legacy_route)

    def peek(self, operation: Operation, principal: Principal) -> Verdict:
        """Would :meth:`admit` grant this call?  Takes no rate or concurrency slot."""
        if operation.legacy_route is None:
            ok = operation.id in NATIVE_OPEN_IDS
            return Verdict(ok, None if ok else "not_mounted")
        group = self._group(operation)
        if group is not None and not self.table.is_group_enabled(group):
            return Verdict(False, "group_disabled")
        rule = self._rule(operation)
        if rule is not None:
            if not rule.enabled:
                return Verdict(False, "endpoint_disabled")
            identity = _identity(principal)
            for scope in rule.scopes:
                if not identity.can(scope):
                    return Verdict(False, "missing_scope")
        return Verdict(True)

    def admit(self, operation: Operation, principal: Principal) -> Admission:
        """Run the same gate the v1 dispatcher runs for the operation's route.

        Raises:
            OpNotEnabled: unknown to this caller (group off, rule disabled, unmounted native op).
            PolicyDenied: missing scope (403) or rate/concurrency limit (429).
        """
        if operation.legacy_route is None:
            if operation.id not in NATIVE_OPEN_IDS:
                raise OpNotEnabled(operation.id)
            return Admission()
        group = self._group(operation)
        if group is not None and not self.table.is_group_enabled(group):
            raise OpNotEnabled(operation.id)
        if self.engine is None:
            return Admission()
        route = self.engine._routes.get(operation.legacy_route)
        if route is None:
            raise OpNotEnabled(operation.id)
        try:
            ctx, release = self.engine.admit(route, _identity(principal))
        except PolicyDenied as exc:
            if exc.status == 404:
                raise OpNotEnabled(operation.id) from exc
            raise
        return Admission(ctx, release)

    def limits_of(self, operation: Operation) -> dict[str, Any]:
        """Effective limits and scopes of the operation's rule (empty without an engine)."""
        rule = self._rule(operation)
        if rule is None:
            return {}
        return {"limits": dict(rule.limits), "scopes": list(rule.scopes)}

    @property
    def revision(self) -> str:
        """The policy revision hash (empty when no policy is configured)."""
        return str(self.engine.policy.revision) if self.engine is not None else ""

    @property
    def preset(self) -> str | None:
        """The configured preset name, if any."""
        return self.engine.policy.preset_name if self.engine is not None else None

    # -- audit ------------------------------------------------------------- #

    def audit(
        self,
        operation: Operation | None,
        principal: Principal | None,
        *,
        status: int,
        code: str = "",
        admission: Admission | None = None,
        op_id: str = "",
    ) -> None:
        """Emit the engine's audit line (a no-op without an engine)."""
        if self.engine is None:
            return
        ctx = admission.ctx if admission is not None else None
        endpoint = (operation.legacy_route if operation is not None else None) or (
            operation.id if operation is not None else op_id
        )
        self.engine.audit(
            rule=ctx.rule if ctx is not None else None,
            identity=_identity(principal) if principal is not None else None,
            endpoint=endpoint,
            method="POST",
            status=status,
            code=code,
            paths=ctx.paths_touched if ctx is not None else None,
        )

    def route(self, name: str) -> RouteInfo | None:
        """The first route of that name in the serving table."""
        for route in self.table._routes:
            if route.name == name:
                return route
        return None


def _identity(principal: Principal) -> Identity:
    return Identity(principal.id, principal.scopes)


def _principal(identity: Identity) -> Principal:
    return Principal(
        id=identity.id,
        authenticated=identity.id != "anonymous",
        scopes=frozenset(identity.scopes),
    )


def _credentials(headers: Any) -> str | None:
    """The single credential of a request; ``None`` if absent or conflicting."""
    values: dict[str, str] = {}
    for key, value in dict(headers).items():
        values[str(key).lower()] = str(value)
    access = values.get("x-access-token", "").strip()
    bearer = ""
    authorization = values.get("authorization", "")
    if authorization[:7].lower() == "bearer ":
        bearer = authorization[7:].strip()
    if access and bearer and access != bearer:
        return None
    return bearer or access or None
