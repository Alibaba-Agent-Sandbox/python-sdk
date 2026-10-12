"""The operation pipeline (design 02, section 6, steps 3-10).

Transport checks (step 0) and byte parsing (steps 1-2) stay with the HTTP listener of the v1
dispatcher; this module is HTTP-agnostic and can be driven in-process (``Pipeline.call``).

Order, as designed: authenticate (401 before any 404) -> resolve the ID or alias -> mounted?
(one ``404 op.not_enabled`` for unknown and not-granted) -> args -> policy admission (403/429)
-> run -> audit.  Operations bound to a v1 route run that route's existing handler, so their
statuses and bodies are exactly what the legacy route returns (the legacy renderer).
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import TYPE_CHECKING, Any

from ..policy import PolicyDenied
from ..types import ServerRequest, ServerResponse, SSEResponse
from .context import OpContext, Principal
from .errors import OpError
from .legacy import build_registry, path_param_names
from .policy import Admission, OpNotEnabled, Policy

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from ..registry import CommandRegistry
    from ..router import RouteInfo, RouteTable
    from .registry import Operation, Registry

__all__ = ["Call", "Outcome", "Pipeline", "Rejected"]

_LOG = logging.getLogger(__name__)

#: A plain mapping or the ``http.client.HTTPMessage`` of a live request (kept as is so duplicate
#: credential headers stay detectable by the policy engine).
Headers = Any

_QUERY_METHODS = frozenset({"GET", "DELETE"})
_BODY_METHODS = frozenset({"POST", "PUT", "DELETE"})

_PY_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


@dataclasses.dataclass
class Outcome:
    """Result of one pipeline run: a JSON response or an SSE stream, plus cleanup."""

    status: int
    body: Any = dataclasses.field(default_factory=dict)
    headers: dict[str, str] = dataclasses.field(default_factory=dict)
    stream: SSEResponse | None = None
    code: str = ""
    admission: Admission | None = None

    def close(self) -> None:
        """Release the concurrency slot; call once the response has been written."""
        if self.admission is not None:
            self.admission.close()


@dataclasses.dataclass
class Call:
    """An authenticated, resolved and admitted call, ready to run."""

    operation: Operation
    principal: Principal
    admission: Admission
    op_id: str


class Rejected(Exception):  # noqa: N818
    """Raised by :meth:`Pipeline.begin` when the call is refused; carries the response."""

    def __init__(self, outcome: Outcome) -> None:
        super().__init__(outcome.code)
        self.outcome = outcome


def _denied_outcome(exc: PolicyDenied, endpoint: str = "") -> Outcome:
    if endpoint and not exc.endpoint:
        exc.endpoint = endpoint
    headers: dict[str, str] = {}
    retry_after = exc.extra.get("retry_after")
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return Outcome(exc.status, exc.to_body(), headers, code=exc.code)


def not_enabled_outcome(op_id: str) -> Outcome:
    """The single answer for unknown, disabled and not-granted operations (no oracle)."""
    return Outcome(
        404,
        {
            "error": f"Operation {op_id!r} is not enabled",
            "type": "ValueError",
            "code": "op.not_enabled",
        },
        code="op.not_enabled",
    )


def unauthorized_outcome() -> Outcome:
    """The v1 policy-mode 401 body."""
    return Outcome(
        401,
        {"error": "unauthorized", "type": "AuthError", "code": "unauthorized"},
        code="unauthorized",
    )


def _query_values(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        if isinstance(item, bool):
            out.append("true" if item else "false")
        elif isinstance(item, (dict, list)):
            out.append(json.dumps(item, separators=(",", ":")))
        else:
            out.append(str(item))
    return out


class Pipeline:
    """Serves operations for one server: registry, policy bridge, route table, commands."""

    def __init__(
        self,
        table: RouteTable,
        policy: Policy,
        commands: CommandRegistry | None = None,
        *,
        registry: Registry | None = None,
    ) -> None:
        self.table = table
        self.policy = policy
        self.commands = commands
        self._fixed = registry
        self._built: Registry | None = None
        self._fingerprint: tuple[Any, ...] | None = None

    # -- registry ---------------------------------------------------------- #

    @property
    def registry(self) -> Registry:
        """The operation registry; rebuilt when routes or commands were added since."""
        if self._fixed is not None:
            return self._fixed
        fingerprint = (
            tuple(route.name for route in self.table._routes),
            tuple(self.commands.list_all()) if self.commands is not None else (),
        )
        if self._built is None or fingerprint != self._fingerprint:
            self._built = build_registry(self.table, self.commands)
            self._fingerprint = fingerprint
        return self._built

    # -- stages -------------------------------------------------------------- #

    def authenticate(self, op_id: str, headers: Headers) -> Principal:
        """Step 3.  Operations without authentication (``core.health``) get an anonymous caller."""
        operation = self.registry.resolve(op_id)
        if operation is not None and not operation.auth_required:
            return Principal("anonymous", authenticated=False, scopes=frozenset())
        try:
            principal = self.policy.authenticate(headers)
        except PolicyDenied as exc:
            raise Rejected(_denied_outcome(exc)) from exc
        if principal is None:
            raise Rejected(unauthorized_outcome())
        return principal

    def begin(self, op_id: str, headers: Headers, *, principal: Principal | None = None) -> Call:
        """Steps 3-5 and 7 (admission).  Raises an internal rejection carrying the outcome."""
        try:
            if principal is None:
                principal = self.authenticate(op_id, headers)
            operation = self.registry.resolve(op_id)
            if operation is None:
                raise OpNotEnabled(op_id)
            admission = self.policy.admit(operation, principal)
        except Rejected as rejected:
            self._audit(None, principal, rejected.outcome, op_id)
            raise
        except OpNotEnabled as exc:
            outcome = not_enabled_outcome(op_id)
            self._audit(None, principal, outcome, op_id, self.registry.resolve(op_id))
            raise Rejected(outcome) from exc
        except PolicyDenied as exc:
            operation = self.registry.resolve(op_id)
            outcome = _denied_outcome(
                exc, operation.legacy_route or operation.id if operation else ""
            )
            self._audit(operation, principal, outcome, op_id)
            raise Rejected(outcome) from exc
        return Call(operation, principal, admission, op_id)

    def run(self, call: Call, args: Mapping[str, Any] | None, headers: Headers) -> Outcome:
        """Steps 6, 9 and 10: bind arguments, run the handler, audit."""
        arguments = dict(args or {})
        operation = call.operation
        try:
            if operation.legacy_route is not None:
                outcome = self._run_legacy(call, arguments, headers)
            else:
                outcome = self._run_native(call, arguments, headers)
        except OpError as exc:
            outcome = Outcome(exc.status, exc.to_body(), code=exc.code)
        except PolicyDenied as exc:
            outcome = _denied_outcome(exc, operation.legacy_route or operation.id)
        except Exception as exc:
            _LOG.exception("Unhandled exception in operation %s: %s", operation.id, exc)
            outcome = Outcome(500, {"error": str(exc), "type": type(exc).__name__}, code="error")
        outcome.admission = call.admission
        self.finish(call, outcome)
        return outcome

    def call(
        self,
        op_id: str,
        args: Mapping[str, Any] | None = None,
        *,
        headers: Headers | None = None,
        principal: Principal | None = None,
    ) -> Outcome:
        """In-process call through every stage; a stream keeps its slot until ``close()``."""
        headers = headers or {}
        try:
            call = self.begin(op_id, headers, principal=principal)
        except Rejected as rejected:
            return rejected.outcome
        outcome = self.run(call, args, headers)
        if outcome.stream is None:
            outcome.close()
        return outcome

    # -- execution ------------------------------------------------------------ #

    def _route(self, name: str) -> RouteInfo:
        route = self.policy.route(name)
        if route is None:
            raise OpError("op.not_callable", f"Route {name!r} is not served here", status=501)
        return route

    def _run_legacy(self, call: Call, args: dict[str, Any], headers: Headers) -> Outcome:
        operation = call.operation
        assert operation.legacy_route is not None
        if not operation.http:
            raise OpError(
                "op.not_callable",
                f"{operation.id} is a {operation.stream} operation; use its own transport",
                status=400,
            )
        route = self._route(operation.legacy_route)
        method = route.method
        path_params: dict[str, str] = dict(operation.fixed_path_params)
        for name in path_param_names(route.path_pattern):
            if name in path_params:
                continue
            value = args.pop(name, None)
            if value is None or value == "":
                raise OpError("args.missing", f"Missing required argument {name!r}")
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise OpError("args.type", f"Argument {name!r} must be a string")
            path_params[name] = str(value)
        path = route.path_pattern
        for name, value in path_params.items():
            path = path.replace("{" + name + "}", value)
        query: dict[str, list[str]] = {}
        body: dict[str, Any] | None = None
        if method in _QUERY_METHODS:
            query = {k: _query_values(v) for k, v in args.items() if v is not None}
        if method in _BODY_METHODS:
            body = {} if method in _QUERY_METHODS else args
        context: dict[str, Any] = {
            "registry": self.commands,
            "route_table": self.table,
            "operation": operation.id,
        }
        if call.admission.ctx is not None:
            context["policy"] = call.admission.ctx
        request = ServerRequest(
            method=method,
            path=path,
            query=query,
            headers=dict(headers),
            body=body,
            path_params=path_params,
            context=context,
        )
        result = route.handler(request)
        if isinstance(result, SSEResponse):
            return Outcome(result.status, {}, dict(result.headers), stream=result)
        assert isinstance(result, ServerResponse)
        return Outcome(result.status, result.body, dict(result.headers))

    def _run_native(self, call: Call, args: dict[str, Any], headers: Headers) -> Outcome:
        operation = call.operation
        handler: Callable[..., Any] | None = operation.handler
        if handler is None:
            raise OpError("op.not_callable", f"{operation.id} has no handler", status=501)
        known = {p.name: p for p in operation.params}
        unknown = sorted(set(args) - set(known))
        if unknown:
            raise OpError("args.unknown", f"Unknown argument(s): {', '.join(unknown)}")
        for param in operation.params:
            if param.name not in args:
                if param.required:
                    raise OpError("args.missing", f"Missing required argument {param.name!r}")
                continue
            value = args[param.name]
            if value is None and not param.required:
                del args[param.name]
                continue
            allowed = _PY_TYPES.get(param.type)
            bad_bool = param.type in ("integer", "number") and isinstance(value, bool)
            if allowed is not None and (bad_bool or not isinstance(value, allowed)):
                raise OpError("args.type", f"Argument {param.name!r} must be {param.type}")
        ctx = OpContext(operation, call.principal, self, dict(headers))
        result = handler(ctx, **args) if operation.wants_ctx else handler(**args)
        return Outcome(200, result)

    # -- audit ----------------------------------------------------------------- #

    def finish(self, call: Call, outcome: Outcome) -> None:
        """Audit the outcome of an admitted call."""
        self._audit(call.operation, call.principal, outcome, call.op_id, admission=call.admission)

    def _audit(
        self,
        operation: Operation | None,
        principal: Principal | None,
        outcome: Outcome,
        op_id: str,
        resolved: Operation | None = None,
        *,
        admission: Admission | None = None,
    ) -> None:
        code = outcome.code
        status = outcome.status
        if not code and status >= 400:
            code = "error"
        self.policy.audit(
            operation or resolved,
            principal,
            status=status,
            code=code,
            admission=admission,
            op_id=op_id,
        )
