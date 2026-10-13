"""Tests for agent_sandbox.server.router — the declarative RouteTable.

Covers route registration + matching, path-parameter extraction, capability
group aliases (``enable_group`` / ``disable_group``), and
the decorator form of :meth:`RouteTable.route`.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_sandbox.server.router import (
    CapabilityGroup,
    RouteInfo,
    RouteTable,
    default_table,
)


def _handler(request: Any) -> str:  # pragma: no cover - trivial stub
    return "ok"


# ---------------------------------------------------------------------------
# Registration & matching
# ---------------------------------------------------------------------------


class TestRegisterAndMatch:
    """Basic registration and lookup semantics."""

    def test_register_and_match_static(self) -> None:
        table = RouteTable()
        table.register("GET", "/health", _handler, group=CapabilityGroup.CORE)
        route, params = table.match("GET", "/health")
        assert isinstance(route, RouteInfo)
        assert route.path_pattern == "/health"
        assert params == {}

    def test_method_is_normalised(self) -> None:
        table = RouteTable()
        table.register("get", "/x", _handler, group=CapabilityGroup.SYSTEM)
        route, _ = table.match("GET", "/x")
        assert route is not None
        assert route.method == "GET"

    def test_no_match_returns_none_none(self) -> None:
        table = RouteTable()
        table.register("GET", "/x", _handler, group=CapabilityGroup.SYSTEM)
        route, params = table.match("GET", "/does-not-exist")
        assert route is None
        assert params is None

    def test_method_mismatch_returns_none(self) -> None:
        table = RouteTable()
        table.register("POST", "/x", _handler, group=CapabilityGroup.SYSTEM)
        route, params = table.match("GET", "/x")
        assert route is None
        assert params is None

    def test_first_registered_wins(self) -> None:
        table = RouteTable()
        table.register("GET", "/dup", _handler, group=CapabilityGroup.SYSTEM, name="first")
        table.register("GET", "/dup", _handler, group=CapabilityGroup.SYSTEM, name="second")
        route, _ = table.match("GET", "/dup")
        assert route is not None
        assert route.name == "first"

    def test_default_name(self) -> None:
        table = RouteTable()
        table.register("get", "/y", _handler, group=CapabilityGroup.SYSTEM)
        route, _ = table.match("GET", "/y")
        assert route is not None
        assert route.name == "GET /y"


# ---------------------------------------------------------------------------
# Path parameters
# ---------------------------------------------------------------------------


class TestPathParams:
    """``{param}`` placeholders are compiled and extracted."""

    def test_single_param(self) -> None:
        table = RouteTable()
        table.register("POST", "/commands/{name}", _handler, group=CapabilityGroup.COMMANDS)
        route, params = table.match("POST", "/commands/greet")
        assert route is not None
        assert params == {"name": "greet"}

    def test_multiple_params(self) -> None:
        table = RouteTable()
        table.register(
            "POST", "/process/{pid}/signal/{sig}", _handler, group=CapabilityGroup.PROCESS
        )
        route, params = table.match("POST", "/process/123/signal/TERM")
        assert route is not None
        assert params == {"pid": "123", "sig": "TERM"}

    def test_param_does_not_span_slash(self) -> None:
        table = RouteTable()
        table.register("POST", "/commands/{name}", _handler, group=CapabilityGroup.COMMANDS)
        # An extra path segment must not match a single {name} param.
        route, params = table.match("POST", "/commands/greet/extra")
        assert route is None
        assert params is None

    def test_static_not_matched_by_param_route(self) -> None:
        table = RouteTable()
        table.register("GET", "/commands/{name}", _handler, group=CapabilityGroup.COMMANDS)
        route, params = table.match("GET", "/commands")
        assert route is None
        assert params is None


# ---------------------------------------------------------------------------
# Group aliases (policy inputs recorded by the table, expanded by the policy engine)
# ---------------------------------------------------------------------------


class TestGroupAliases:
    """``enable_group`` / ``disable_group`` only record an alias; the policy engine expands it."""

    def test_no_aliases_by_default(self) -> None:
        assert RouteTable().group_overrides == {}

    def test_disable_then_enable(self) -> None:
        table = RouteTable()
        table.disable_group(CapabilityGroup.FILE_OPS)
        assert table.group_overrides == {CapabilityGroup.FILE_OPS: False}
        table.enable_group(CapabilityGroup.FILE_OPS)
        assert table.group_overrides == {CapabilityGroup.FILE_OPS: True}

    def test_changes_bump_the_revision(self) -> None:
        table = RouteTable()
        before = table.revision
        table.enable_group(CapabilityGroup.AGENTS)
        assert table.revision > before

    def test_enable_core_is_a_no_op(self) -> None:
        table = RouteTable()
        before = table.revision
        table.enable_group(CapabilityGroup.CORE)
        assert table.group_overrides == {}
        assert table.revision == before

    def test_cannot_disable_core(self) -> None:
        table = RouteTable()
        with pytest.raises(ValueError, match="Cannot disable CORE"):
            table.disable_group(CapabilityGroup.CORE)

    def test_clear_and_copy(self) -> None:
        table = RouteTable()
        table.enable_group(CapabilityGroup.BROWSER)
        clone = table.copy()
        table.clear_group_overrides()
        assert table.group_overrides == {}
        assert clone.group_overrides == {CapabilityGroup.BROWSER: True}


class TestMount:
    """Built-in routes are declared once in ``ENDPOINTS`` and mounted by name."""

    def test_mount_takes_the_declared_binding(self) -> None:
        table = RouteTable()
        table.mount("files_list", _handler)
        route, _ = table.match("GET", "/files/list")
        assert route is not None
        assert route.name == "files_list"
        assert route.group is CapabilityGroup.FILE_OPS
        assert route.spec.scopes == ("files:read",)

    def test_mount_unknown_or_virtual_endpoint_fails(self) -> None:
        table = RouteTable()
        with pytest.raises(KeyError):
            table.mount("nope", _handler)
        with pytest.raises(KeyError, match="another transport"):
            table.mount("pty_connect", _handler)


# ---------------------------------------------------------------------------
# Decorator form
# ---------------------------------------------------------------------------


class TestRouteDecorator:
    """The ``@table.route(...)`` decorator registers and returns the fn."""

    def test_decorator_registers(self) -> None:
        table = RouteTable()

        @table.route("GET", "/deco", group=CapabilityGroup.SYSTEM, name="deco")
        def handler(request: Any) -> str:
            return "deco"

        route, _ = table.match("GET", "/deco")
        assert route is not None
        assert route.name == "deco"
        # Decorator returns the function unchanged.
        assert handler(None) == "deco"


# ---------------------------------------------------------------------------
# Default table singleton
# ---------------------------------------------------------------------------


class TestDefaultTable:
    """The module-level default table is a populated singleton."""

    def test_default_table_is_singleton(self) -> None:
        assert default_table() is default_table()

    def test_builtin_routes_registered(self) -> None:
        table = default_table()
        # Routes registered by routes.py import side-effect.
        health, _ = table.match("GET", "/health")
        assert health is not None
        assert health.auth_required is False
        run, params = table.match("POST", "/commands/add")
        assert run is not None
        assert params == {"name": "add"}
