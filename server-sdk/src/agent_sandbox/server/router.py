"""Route table of the sandbox HTTP server — stdlib-only.

A :class:`RouteTable` is the set of mounted routes.  Built-in routes are *declared* once, in
:data:`agent_sandbox.server.endpoints.ENDPOINTS`, and mounted by name with :meth:`RouteTable.mount`;
templates add their own routes with :meth:`RouteTable.register` / :meth:`RouteTable.route`.  Adding
an endpoint therefore needs no change to :mod:`agent_sandbox.server.app`.

Path patterns use ``{param}`` placeholders which are compiled to named regex groups
(``(?P<param>[^/]+)``) so path parameters can be extracted during matching.

The table decides nothing about *who may call what*: that is the endpoint policy
(:class:`agent_sandbox.server.runtime.PolicyEngine`).  :meth:`RouteTable.enable_group` and
:meth:`RouteTable.disable_group` are convenience helpers that record "expand this group to its
endpoints" as a policy input of the code that owns the table.

Example::

    table = RouteTable()

    @table.route("GET", "/status", group=CapabilityGroup.SYSTEM)
    def status(request):
        return ServerResponse.ok({"status": "ok"})

    route, params = table.match("GET", "/status")
"""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING, Any

from .endpoints import (
    COMMON_LIMITS,
    ENDPOINTS,
    CapabilityGroup,
    EndpointSpec,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "CapabilityGroup",
    "RouteInfo",
    "RouteTable",
    "default_table",
]


@dataclasses.dataclass
class RouteInfo:
    """Metadata describing a single registered route.

    Attributes:
        method: Upper-cased HTTP method (``"GET"``, ``"POST"``, ``"DELETE"``).
        path_pattern: Path template with ``{param}`` placeholders, e.g.
            ``"/process/{pid}/signal"``.
        handler: Callable invoked as ``handler(request) -> ServerResponse``
            (or ``SSEResponse`` when :attr:`streaming` is ``True``).
        group: The :class:`CapabilityGroup` alias this route belongs to.
        auth_required: Whether the request must authenticate (``/health`` sets this to ``False``).
        streaming: ``True`` for Server-Sent-Events handlers.
        name: The endpoint ID used by policies, audit lines and discovery.
        spec: Default scopes and tunable knobs of this endpoint.
        summary: One-line description for discovery.
        _regex: Pre-compiled pattern used for matching (internal).
        _param_names: Ordered list of path-parameter names (internal).
    """

    method: str
    path_pattern: str
    handler: Callable[..., Any]
    group: CapabilityGroup
    auth_required: bool = True
    streaming: bool = False
    name: str = ""
    spec: EndpointSpec = dataclasses.field(default_factory=EndpointSpec)
    summary: str = ""
    _regex: re.Pattern[str] | None = dataclasses.field(default=None, repr=False)
    _param_names: list[str] = dataclasses.field(default_factory=list, repr=False)

    @property
    def scopes(self) -> tuple[str, ...]:
        """Default permission scopes required to call this endpoint."""
        return self.spec.scopes


class RouteTable:
    """A registry of :class:`RouteInfo` records matched in registration order."""

    def __init__(self) -> None:
        """Create an empty table."""
        self._routes: list[RouteInfo] = []
        self._group_overrides: dict[CapabilityGroup, bool] = {}
        self._revision = 0

    @property
    def revision(self) -> int:
        """Bumped whenever routes or group aliases change (policy engines recompile on change)."""
        return self._revision

    def copy(self) -> RouteTable:
        """Return an independent table sharing the (immutable) routes."""
        clone = RouteTable()
        clone._routes = list(self._routes)
        clone._group_overrides = dict(self._group_overrides)
        clone._revision = self._revision
        return clone

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #

    def mount(self, name: str, handler: Callable[..., Any]) -> None:
        """Attach *handler* to the built-in endpoint *name* declared in ``ENDPOINTS``.

        Raises:
            KeyError: *name* is not a declared endpoint (or is served by another transport).
        """
        endpoint = ENDPOINTS[name]
        if endpoint.virtual:
            raise KeyError(f"endpoint {name!r} is served by another transport and has no route")
        self.register(
            endpoint.method,
            endpoint.path,
            handler,
            group=endpoint.group,
            auth_required=endpoint.auth_required,
            streaming=endpoint.streaming,
            name=name,
            spec=endpoint.spec,
            summary=endpoint.summary,
        )

    def register(
        self,
        method: str,
        path_pattern: str,
        handler: Callable[..., Any],
        *,
        group: CapabilityGroup,
        auth_required: bool = True,
        streaming: bool = False,
        name: str = "",
        scopes: tuple[str, ...] | list[str] = (),
        spec: EndpointSpec | None = None,
        summary: str = "",
    ) -> None:
        """Register *handler* for *method* + *path_pattern*.

        The pattern is compiled to a regex where each ``{param}`` placeholder
        becomes a named capture group ``(?P<param>[^/]+)``.  Built-in endpoints use
        :meth:`mount`; this is the entry point for a template's own routes.

        Args:
            method: HTTP method (case-insensitive).
            path_pattern: Path template with optional ``{param}`` placeholders.
            handler: Callable invoked with the parsed request object.
            group: The :class:`CapabilityGroup` alias this route belongs to.
            auth_required: Whether authentication is enforced (default ``True``).
            streaming: ``True`` for SSE handlers (default ``False``).
            name: Optional human-readable name (defaults to
                ``"{METHOD} {path_pattern}"``); also the endpoint ID used by policies.
            scopes: Permission scopes required to call a custom route.
            spec: Full endpoint spec (built-ins); overrides *scopes*.
            summary: One-line description for discovery.
        """
        param_names = re.findall(r"\{(\w+)\}", path_pattern)
        regex_str = "^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", path_pattern) + "$"
        compiled = re.compile(regex_str)
        route = RouteInfo(
            method=method.upper(),
            path_pattern=path_pattern,
            handler=handler,
            group=group,
            auth_required=auth_required,
            streaming=streaming,
            name=name or f"{method.upper()} {path_pattern}",
            spec=spec or EndpointSpec(scopes=tuple(scopes), limits=COMMON_LIMITS),
            summary=summary,
            _regex=compiled,
            _param_names=param_names,
        )
        self._routes.append(route)
        self._revision += 1

    def route(
        self,
        method: str,
        path_pattern: str,
        **kwargs: object,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator form of :meth:`register`.

        Example::

            @table.route("GET", "/status", group=CapabilityGroup.SYSTEM)
            def status(request):
                ...

        Args:
            method: HTTP method.
            path_pattern: Path template.
            **kwargs: Forwarded to :meth:`register` (``group``,
                ``auth_required``, ``streaming``, ``name``, ``scopes``).

        Returns:
            A decorator that registers the wrapped function and returns it
            unchanged.
        """

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.register(method, path_pattern, fn, **kwargs)  # type: ignore[arg-type]
            return fn

        return decorator

    # ------------------------------------------------------------------ #
    # Matching
    # ------------------------------------------------------------------ #

    def match(
        self,
        method: str,
        path: str,
    ) -> tuple[RouteInfo, dict[str, str]] | tuple[None, None]:
        """Find the first route matching *method* + *path*.

        Args:
            method: HTTP method (case-insensitive).
            path: Concrete request path (query string already stripped).

        Returns:
            ``(route, path_params)`` for the first match, or ``(None, None)``
            when no route matches.
        """
        upper = method.upper()
        for route in self._routes:
            if route.method != upper:
                continue
            if route._regex is None:
                continue
            m = route._regex.match(path)
            if m:
                return route, m.groupdict()
        return None, None

    def by_name(self, name: str) -> RouteInfo | None:
        """The first route registered under endpoint ID *name*."""
        for route in self._routes:
            if route.name == name:
                return route
        return None

    # ------------------------------------------------------------------ #
    # Group aliases (policy inputs, not a gate)
    # ------------------------------------------------------------------ #

    def enable_group(self, group: CapabilityGroup) -> None:
        """Expand *group* to "enabled" for every endpoint it names (no-op for ``CORE``).

        This is a policy input of the code that owns the table; a policy document, an
        ``ABX_SERVER_ENABLED_GROUPS`` entry or an exact endpoint rule still refine it.
        """
        if group is CapabilityGroup.CORE:
            return
        self._group_overrides[group] = True
        self._revision += 1

    def disable_group(self, group: CapabilityGroup) -> None:
        """Expand *group* to "disabled" for every endpoint it names.

        Raises:
            ValueError: If *group* is :data:`CapabilityGroup.CORE`.
        """
        if group is CapabilityGroup.CORE:
            raise ValueError("Cannot disable CORE capability group")
        self._group_overrides[group] = False
        self._revision += 1

    def clear_group_overrides(self) -> None:
        """Forget every :meth:`enable_group` / :meth:`disable_group` call."""
        self._group_overrides.clear()
        self._revision += 1

    @property
    def group_overrides(self) -> dict[CapabilityGroup, bool]:
        """The group aliases recorded by :meth:`enable_group` / :meth:`disable_group`."""
        return dict(self._group_overrides)


# ---------------------------------------------------------------------------
# Module-level default table
# ---------------------------------------------------------------------------

_default_table = RouteTable()


def default_table() -> RouteTable:
    """Return the module-level default :class:`RouteTable` singleton."""
    return _default_table
