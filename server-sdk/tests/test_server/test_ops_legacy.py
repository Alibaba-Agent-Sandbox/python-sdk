"""Every v1 route is also an operation (stage S1), built from the real route tables."""

from __future__ import annotations

from typing import Any

import pytest

from easy_sandbox.server import app as _app  # noqa: F401  (registers every v1 route)
from easy_sandbox.server.core import Pipeline, Policy, build_registry, default_op_registry
from easy_sandbox.server.core.ids import is_valid_id
from easy_sandbox.server.core.legacy import ALIAS_FAMILIES, LEGACY_OPS, VIRTUAL_ROUTES
from easy_sandbox.server.registry import CommandRegistry
from easy_sandbox.server.router import CapabilityGroup, RouteTable, default_table
from easy_sandbox.server.types import ServerResponse

#: The 41 legacy ids of the design that exist as v1 routes today (pinned: ids are append-only).
PINNED = {
    "health": "core.health",
    "capabilities": "core.capabilities",
    "capabilities_check": "core.check",
    "list_commands": "custom.list",
    "upload": "files.upload",
    "download": "files.download",
    "files_list": "files.list",
    "files_stat": "files.stat",
    "files_mkdir": "files.mkdir",
    "files_delete": "files.delete",
    "files_move": "files.move",
    "files_search": "files.search",
    "files_upload_stream": "files.upload_stream",
    "files_download_stream": "files.download_stream",
    "files_archive": "files.archive",
    "files_watch": "files.watch",
    "shell": "commands.run",
    "shell_stream": "commands.stream",
    "process_start": "process.start",
    "process_list": "process.list",
    "process_detail": "process.get",
    "process_signal": "process.signal",
    "process_stdin": "process.stdin",
    "process_output": "process.output",
    "pty_create_session": "terminal.create",
    "pty_list_sessions": "terminal.list",
    "pty_detail": "terminal.get",
    "pty_resize": "terminal.resize",
    "pty_delete_session": "terminal.delete",
    "system_info": "system.info",
    "system_metrics": "system.metrics",
    "env_get": "system.env.get",
    "env_set": "system.env.set",
    "ports": "system.ports",
    "packages": "system.packages",
    "code_run": "devtools.code.run",
    "git_status": "devtools.git.status",
    "git_diff": "devtools.git.diff",
    "browser_navigate": "browser.navigate",
    "browser_screenshot": "browser.screenshot",
    "browser_content": "browser.content",
    "browser_click": "browser.click",
    "browser_type": "browser.type",
    "browser_evaluate": "browser.evaluate",
    "browser_pdf": "browser.pdf",
    "browser_console": "browser.console",
}


def _route_names() -> list[str]:
    return [r.name for r in default_table()._routes]


class TestDefaultRegistry:
    def test_every_route_is_an_operation_or_an_alias_family(self) -> None:
        registry = default_op_registry()
        by_route = {o.legacy_route: o for o in registry.all().values() if o.legacy_route}
        for route in default_table()._routes:
            if route.name in ALIAS_FAMILIES:
                continue
            operation = by_route.get(route.name)
            assert operation is not None, f"route {route.name!r} has no operation"
            assert any(
                b.method == route.method and b.path == route.path_pattern for b in operation.http
            )

    def test_operation_count_follows_the_route_table(self) -> None:
        registry = default_op_registry()
        routes = [n for n in _route_names() if n not in ALIAS_FAMILIES]
        natives = {"core.describe"}
        virtual = {s.op_id for s in VIRTUAL_ROUTES.values()}
        assert len(registry) == len(routes) + len(natives) + len(virtual)

    def test_pinned_legacy_ids(self) -> None:
        registry = default_op_registry()
        for route_name, op_id in PINNED.items():
            operation = registry.get(op_id)
            assert operation is not None, op_id
            assert operation.legacy_route == route_name
            assert registry.resolve(route_name) is operation

    def test_all_ids_are_valid_and_free_of_prefix_conflicts(self) -> None:
        ids = list(default_op_registry().all())
        assert all(is_valid_id(i) for i in ids)
        for a in ids:
            assert not any(b.startswith(a + ".") for b in ids), a

    def test_mapped_names_exist_as_routes(self) -> None:
        names = set(_route_names())
        for route_name, spec in LEGACY_OPS.items():
            if spec.op_id.startswith("agents."):
                continue
            assert route_name in names, route_name

    def test_agents_routes_are_operations(self) -> None:
        registry = default_op_registry()
        agent_routes = [r for r in default_table()._routes if r.group == CapabilityGroup.AGENTS]
        assert agent_routes
        for route in agent_routes:
            operation = next(o for o in registry.all().values() if o.legacy_route == route.name)
            assert operation.group == "agents"
            assert operation.id.startswith(("agents.", "responses.", "webhooks.", "files."))
            assert operation.effects_declared, route.name
            assert route.name in LEGACY_OPS, route.name
            assert operation.effects != frozenset({"admin"}), operation.id

    def test_groups_come_from_the_routes(self) -> None:
        registry = default_op_registry()
        for route in default_table()._routes:
            if route.name in ALIAS_FAMILIES:
                continue
            operation = next(o for o in registry.all().values() if o.legacy_route == route.name)
            assert operation.group == route.group.value

    def test_effects_are_declared_and_explicit_only_set_is_right(self) -> None:
        registry = default_op_registry()
        mapped = {s.op_id for s in LEGACY_OPS.values()} | {"core.describe"}
        mapped |= {s.op_id for s in VIRTUAL_ROUTES.values()}
        for operation in registry.all().values():
            if operation.id in mapped:
                assert operation.effects_declared, operation.id
            else:
                assert operation.effects == frozenset({"admin"}), operation.id
                assert operation.explicit, operation.id
        explicit = {o.id for o in registry.all().values() if o.explicit and o.id in mapped}
        assert explicit == {"system.env.set", "process.signal", "terminal.create"}

    def test_streaming_and_ws_flags(self) -> None:
        registry = default_op_registry()
        assert registry.get("commands.stream").stream == "sse"  # type: ignore[union-attr]
        assert registry.get("files.watch").stream == "sse"  # type: ignore[union-attr]
        connect = registry.get("terminal.connect")
        assert connect is not None and connect.stream == "ws" and connect.http == ()

    def test_health_is_anonymous_and_the_rest_authenticated(self) -> None:
        registry = default_op_registry()
        for operation in registry.all().values():
            assert operation.auth_required == (operation.id != "core.health"), operation.id

    def test_legacy_ops_are_wrappers_not_copies(self) -> None:
        for operation in default_op_registry().all().values():
            if operation.legacy_route is not None:
                assert operation.handler is None


class TestExtensionRoutes:
    def _table(self) -> RouteTable:
        table = default_table().copy()

        def handler(request: Any) -> ServerResponse:
            return ServerResponse.ok({"hello": request.body})

        table.register("POST", "/my/echo", handler, group=CapabilityGroup.COMMANDS, name="my_echo")
        table.register("GET", "/Odd Name", handler, group=CapabilityGroup.COMMANDS, name="Odd-Name")
        table.register("GET", "/again", handler, group=CapabilityGroup.COMMANDS, name="my_echo")
        return table

    def test_unknown_routes_become_explicit_only_ext_ops(self) -> None:
        registry = build_registry(self._table())
        echo = registry.get("ext.my_echo")
        assert echo is not None and echo.legacy_route == "my_echo"
        assert echo.effects == frozenset({"admin"}) and echo.explicit
        assert not echo.effects_declared
        assert [(b.method, b.path) for b in echo.http] == [("POST", "/my/echo"), ("GET", "/again")]
        assert registry.get("ext.odd_name") is not None

    def test_ext_op_runs_the_route_handler(self) -> None:
        table = self._table()
        pipeline = Pipeline(table, Policy.open(table))
        outcome = pipeline.call("ext.my_echo", {"a": 1})
        assert (outcome.status, outcome.body) == (200, {"hello": {"a": 1}})

    def test_unknown_agents_routes_get_a_mechanical_id(self) -> None:
        table = default_table().copy()
        table.register(
            "POST",
            "/v1/agents/sessions/{id}/update",
            lambda r: ServerResponse.ok({}),
            group=CapabilityGroup.AGENTS,
            name="agents_sessions_update",
        )
        assert build_registry(table).get("agents.sessions.update") is not None


class TestCommandOperations:
    def _commands(self) -> CommandRegistry:
        commands = CommandRegistry()

        @commands.command("Hello-World.v2")
        def hello(name: str = "x") -> str:
            return f"hi {name}"

        @commands.command("list")
        def listing() -> str:
            return "clash"

        @commands.command("secret", hidden=True)
        def secret() -> str:
            return "s"

        return commands

    def test_command_names_are_mangled_with_alias_and_collision_suffix(self) -> None:
        registry = build_registry(default_table(), self._commands())
        hello = registry.get("custom.hello_world_v2")
        assert hello is not None
        assert registry.resolve("Hello-World.v2") is hello
        assert hello.legacy_route == "run_command"
        assert hello.fixed_path_params == {"name": "Hello-World.v2"}
        assert [(b.method, b.path) for b in hello.http] == [("POST", "/commands/Hello-World.v2")]
        assert registry.get("custom.list").legacy_route == "list_commands"  # type: ignore[union-attr]
        assert registry.get("custom.list_2") is not None

    def test_hidden_commands_are_executable_but_not_listed(self) -> None:
        registry = build_registry(default_table(), self._commands())
        assert registry.get("custom.secret") is not None
        assert "custom.secret" not in [e["id"] for e in registry.describe()]

    def test_command_params_are_described(self) -> None:
        registry = build_registry(default_table(), self._commands())
        hello = registry.get("custom.hello_world_v2")
        assert hello is not None
        assert [(p.name, p.type, p.required) for p in hello.params] == [("name", "string", False)]

    def test_pipeline_picks_up_commands_registered_later(self) -> None:
        commands = CommandRegistry()
        table = default_table()
        pipeline = Pipeline(table, Policy.open(table), commands)
        assert pipeline.call("custom.late").status == 404

        @commands.command("late")
        def late() -> str:
            return "ok"

        outcome = pipeline.call("custom.late")
        assert (outcome.status, outcome.body) == (200, {"result": "ok"})

    def test_ops_calls_equal_the_legacy_function(self) -> None:
        commands = self._commands()
        table = default_table()
        pipeline = Pipeline(table, Policy.open(table), commands)
        outcome = pipeline.call("custom.hello_world_v2", {"name": "bob"})
        assert (outcome.status, outcome.body) == (200, {"result": "hi bob"})
        bad = pipeline.call("custom.hello_world_v2", {"nope": 1})
        assert bad.status in (200, 400)
        listing = pipeline.call("custom.list")
        assert listing.status == 200
        assert {c["name"] for c in listing.body["commands"]} == {"Hello-World.v2", "list"}

    @pytest.mark.parametrize("name", ["greet", "files_list", "shell"])
    def test_command_aliases_never_steal_route_aliases(self, name: str) -> None:
        commands = CommandRegistry()
        commands.register(name, lambda: "x")
        registry = build_registry(default_table(), commands)
        if name == "greet":
            assert registry.resolve("greet").id == "custom.greet"  # type: ignore[union-attr]
        else:
            assert registry.resolve(name).legacy_route != "run_command"  # type: ignore[union-attr]
