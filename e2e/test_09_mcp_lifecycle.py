"""Real-cloud Python MCP handlers, including metadata ownership boundaries."""

from __future__ import annotations

import e2e_helpers as helpers


def test_mcp_lifecycle_and_external_inspection(run, tracker):  # type: ignore[no-untyped-def]
    from agent_sandbox.agent.mcp import SandboxManager
    from agent_sandbox.agent.tools import dispatch_tool

    owner = SandboxManager(template=helpers.OFFICIAL_BASE)
    observer = SandboxManager()
    metadata_fields = {
        "sandbox_id",
        "template",
        "status",
        "region",
        "started_at",
        "end_at",
        "cpu_count",
        "memory_mb",
        "disk_size_mb",
    }

    async def scenario() -> str:
        empty = await dispatch_tool("get_sandbox", {}, observer)
        assert "error" in empty
        assert not observer._sandboxes
        try:
            created = await dispatch_tool(
                "create_sandbox",
                {
                    "template": helpers.OFFICIAL_BASE,
                    "timeout": 600,
                },
                owner,
            )
            assert "error" not in created
            sandbox_id = created["sandbox_id"]
            tracker.sandbox(sandbox_id)
            info = await dispatch_tool("get_sandbox", {}, owner)
            assert set(info) == metadata_fields
            assert info["sandbox_id"] == sandbox_id
            before = info["end_at"]
            external = await dispatch_tool("get_sandbox", {"sandbox_id": sandbox_id}, observer)
            assert set(external) == metadata_fields
            assert external["sandbox_id"] == sandbox_id
            assert not observer._sandboxes
            renewed = await dispatch_tool(
                "set_sandbox_timeout",
                {
                    "sandbox_id": sandbox_id,
                    "timeout": 720,
                },
                observer,
            )
            assert renewed.get("success") is True
            assert not observer._sandboxes
            await observer.shutdown()
            owner_sandbox = await owner.get_sandbox(refresh_lifetime=False)
            refreshed = await owner_sandbox.refresh_info()
            assert refreshed.status.value == "running"
            assert refreshed.end_at is not None and refreshed.end_at.isoformat() != before
            updated = await dispatch_tool("set_sandbox_timeout", {"timeout": 600}, owner)
            assert updated.get("success") is True
            assert owner._lifetimes[owner._sandbox_key(owner_sandbox)] == 600
            path = helpers.unique_dir() + "-mcp.txt"
            written = await dispatch_tool("write_file", {"path": path, "content": "mcp-e2e"}, owner)
            assert written.get("success") is True
            read = await dispatch_tool("read_file", {"path": path}, owner)
            assert read.get("content") == "mcp-e2e"
            result = await dispatch_tool(
                "run_command",
                {
                    "command": "python3 -c 'print(6 * 7)'",
                    "timeout": 30,
                },
                owner,
            )
            assert result.get("exit_code") == 0
            assert result.get("stdout", "").strip() == "42"
            return sandbox_id
        finally:
            await observer.shutdown()
            # Only resources created by this manager are registered for shutdown.
            await owner.shutdown()

    run(scenario())


def test_mcp_list_eventually_includes_created_sandbox(run, sandbox_factory):  # type: ignore[no-untyped-def]
    from agent_sandbox.agent.mcp import SandboxManager
    from agent_sandbox.agent.tools import dispatch_tool

    sandbox = sandbox_factory(helpers.OFFICIAL_BASE)
    observer = SandboxManager()

    def listed() -> bool:
        result = run(dispatch_tool("list_sandboxes", {"limit": 100, "offset": 0}, observer))
        assert "error" not in result
        assert not observer._sandboxes
        assert observer._default_sandbox is None
        return any(info["sandbox_id"] == sandbox.id for info in result["sandboxes"])

    # Existing lifecycle tests document this control-plane operation as eventually
    # consistent; retry only the list visibility assertion, never creation.
    helpers.eventually(listed, timeout=40, interval=2, what="MCP sandbox list visibility")


def test_mcp_borrower_shutdown_preserves_other_session_sandbox(run, tracker):  # type: ignore[no-untyped-def]
    import pytest

    from agent_sandbox import ProviderSandbox
    from agent_sandbox.agent.mcp import SandboxManager
    from agent_sandbox.agent.tools import dispatch_tool
    from agent_sandbox.models.errors import SandboxNotFoundError

    owner = SandboxManager(template=helpers.OFFICIAL_BASE)
    borrower = SandboxManager()

    async def scenario() -> None:
        sandbox_id = None
        try:
            created = await dispatch_tool("create_sandbox", {"timeout": 300}, owner)
            assert "error" not in created
            sandbox_id = created["sandbox_id"]
            tracker.sandbox(sandbox_id)
            borrowed = await dispatch_tool(
                "run_command",
                {"sandbox_id": sandbox_id, "command": "printf borrowed-ok"},
                borrower,
            )
            assert borrowed.get("stdout") == "borrowed-ok"
            assert borrower._sandboxes
            await borrower.shutdown()
            # This command must still reach the original cloud sandbox after
            # the other session has closed its borrowed client connection.
            surviving = await dispatch_tool("run_command", {"command": "printf owner-alive"}, owner)
            assert surviving.get("stdout") == "owner-alive"
        finally:
            await borrower.shutdown()
            await owner.shutdown()
        with pytest.raises(SandboxNotFoundError):
            await ProviderSandbox.get_info_by_id(sandbox_id)

    run(scenario())


def test_mcp_task_qualified_handle_survives_session_replacement(run, tracker):  # type: ignore[no-untyped-def]
    import pytest

    from agent_sandbox import ProviderSandbox
    from agent_sandbox.agent.mcp import SandboxManager
    from agent_sandbox.agent.tools import dispatch_tool
    from agent_sandbox.models.errors import SandboxNotFoundError

    owner = SandboxManager(template=helpers.OFFICIAL_BASE)
    observer = SandboxManager()

    async def scenario() -> None:
        sandbox_id = None
        qualified_id = None
        try:
            created = await dispatch_tool("create_sandbox", {"timeout": 300}, owner)
            assert "error" not in created
            sandbox_id = created["sandbox_id"]
            tracker.sandbox(sandbox_id)
            sandbox = await owner.get_sandbox(refresh_lifetime=False)
            qualified_id = sandbox.provider + ":" + sandbox_id
            started = await dispatch_tool(
                "start_task",
                {"command": "printf before; sleep 2; printf after", "timeout": 15},
                owner,
            )
            assert "error" not in started and started["retained_until_sandbox_ttl"]
            assert started["sandbox_id"] == qualified_id
            handle = {key: started[key] for key in ("sandbox_id", "task_id")}
            await owner.shutdown()

            async def completed():
                result = await dispatch_tool("get_task", handle, observer)
                assert "error" not in result
                return result if result["state"] != "running" else None

            result = await helpers.eventually_async(completed, timeout=30, interval=1)
            assert result["state"] == "succeeded" and result["exit_code"] == 0
            assert result["stdout"] == "beforeafter"
            assert not observer._sandboxes and observer._default_sandbox is None
        finally:
            await observer.shutdown()
            await owner.shutdown()
            if sandbox_id is not None:
                await ProviderSandbox.kill_by_id(qualified_id or sandbox_id)
        with pytest.raises(SandboxNotFoundError):
            await ProviderSandbox.get_info_by_id(qualified_id or sandbox_id)

    run(scenario())


def test_mcp_explicit_resources_verified_or_new_sandbox_rolled_back(run, tracker):  # type: ignore[no-untyped-def]
    """The base template currently fixes resources; verify actual matching and rejection."""
    from agent_sandbox import ProviderSandbox
    from agent_sandbox.agent.mcp import SandboxManager
    from agent_sandbox.agent.tools import dispatch_tool
    from agent_sandbox.models.errors import SandboxNotFoundError

    owner = SandboxManager(template=helpers.OFFICIAL_BASE)

    async def scenario() -> None:
        try:
            baseline = await dispatch_tool("create_sandbox", {"timeout": 300}, owner)
            assert "error" not in baseline
            tracker.sandbox(baseline["sandbox_id"])
            original = await owner.get_sandbox(refresh_lifetime=False)
            info = await original.refresh_info()
            assert type(info.cpu_count) is int and info.cpu_count > 0
            assert type(info.memory_mb) is int and info.memory_mb > 0
            matching = {"cpu": info.cpu_count, "memory": info.memory_mb, "timeout": 300}
            created = await dispatch_tool("create_sandbox", matching, owner)
            assert "error" not in created
            tracker.sandbox(created["sandbox_id"])
            actual = await owner.inspect_sandbox(created["sandbox_id"])
            assert (actual.cpu_count, actual.memory_mb) == (info.cpu_count, info.memory_mb)
            # Bounded differences from this actual template; never guess a large shape.
            rejected = await dispatch_tool(
                "create_sandbox",
                {"cpu": info.cpu_count + 1, "memory": info.memory_mb + 256, "timeout": 300},
                owner,
            )
            tracker.sandbox(rejected["sandbox_id"])
            assert rejected["category"] == "resource_configuration", rejected
            assert rejected["cleanup_verified"] is True, rejected
            try:
                await ProviderSandbox.get_info_by_id(rejected["sandbox_id"])
            except SandboxNotFoundError:
                pass
            else:
                raise AssertionError("Mismatched new sandbox still exists")
            assert (
                await original.commands.run("printf existing-survives")
            ).stdout == "existing-survives"
        finally:
            await owner.shutdown()

    run(scenario())
