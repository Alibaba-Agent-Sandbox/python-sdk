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
                    "cpu": 2,
                    "memory": 1024,
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
            refreshed = await owner._sandboxes[sandbox_id].refresh_info()
            assert refreshed.status.value == "running"
            assert refreshed.end_at is not None and refreshed.end_at.isoformat() != before
            updated = await dispatch_tool("set_sandbox_timeout", {"timeout": 600}, owner)
            assert updated.get("success") is True
            assert owner._lifetimes[sandbox_id] == 600
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
