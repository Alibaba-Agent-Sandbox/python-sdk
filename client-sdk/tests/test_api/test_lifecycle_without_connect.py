"""Direct control-plane dispatch never reaches a provider's side-effecting connect."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent_sandbox import ProviderSandbox as Sandbox
from agent_sandbox.agent.mcp import SandboxManager
from agent_sandbox.models.sandbox import SandboxInfo, SandboxStatus


@pytest.mark.parametrize("operation", ["inspect", "timeout"])
@pytest.mark.parametrize("fail", [False, True])
async def test_provider_lifecycle_never_connects_or_resumes(operation, fail):
    protocol = SimpleNamespace(
        get_info=AsyncMock(
            return_value=SandboxInfo(sandbox_id="paused", status=SandboxStatus.PAUSED)
        ),
        set_timeout=AsyncMock(),
        connect=AsyncMock(side_effect=AssertionError("must never resume")),
        create=AsyncMock(),
        kill=AsyncMock(),
    )
    closer = AsyncMock()
    infra = SimpleNamespace(sandbox_protocol=protocol, close=closer)
    provider = SimpleNamespace(id="paused-fixture")
    manager = SandboxManager()
    target = protocol.get_info if operation == "inspect" else protocol.set_timeout
    if fail:
        target.side_effect = RuntimeError("operation failed")
    with (
        patch("agent_sandbox.api.sandbox._select_provider", return_value=(provider, "paused")),
        patch(
            "agent_sandbox.api.sandbox._provider_infra", new_callable=AsyncMock, return_value=infra
        ),
    ):

        async def run():
            if operation == "inspect":
                return await manager.inspect_sandbox("paused-fixture:paused")
            return await manager.set_sandbox_timeout(700, "paused-fixture:paused")

        if fail:
            with pytest.raises(RuntimeError, match="operation failed"):
                await run()
        else:
            result = await run()
            if operation == "inspect":
                assert result.status == SandboxStatus.PAUSED
                protocol.get_info.assert_awaited_once_with("paused")
                protocol.set_timeout.assert_not_awaited()
            else:
                protocol.set_timeout.assert_awaited_once_with("paused", 700)
                protocol.get_info.assert_not_awaited()
    closer.assert_awaited_once_with()
    protocol.connect.assert_not_awaited()
    protocol.create.assert_not_awaited()
    await manager.shutdown()
    protocol.kill.assert_not_awaited()
    assert not manager._sandboxes and not manager._lifetimes


@pytest.mark.parametrize("operation", ["inspect", "timeout"])
@pytest.mark.parametrize("fail", [False, True])
async def test_builtin_direct_lifecycle_closes_http_without_connect(operation, fail):
    protocol = AsyncMock()
    protocol.get_info.return_value = SandboxInfo(sandbox_id="existing")
    http = AsyncMock()
    target = protocol.get_info if operation == "inspect" else protocol.set_timeout
    if fail:
        target.side_effect = RuntimeError("operation failed")
    with (
        patch("agent_sandbox.api.sandbox._select_provider", return_value=(None, "existing")),
        patch("agent_sandbox.api.sandbox._build_infra", return_value=(None, None, http, protocol)),
    ):

        async def run():
            if operation == "inspect":
                return await Sandbox.get_info_by_id("existing")
            return await Sandbox.set_timeout_by_id("existing", 600)

        if fail:
            with pytest.raises(RuntimeError, match="operation failed"):
                await run()
        else:
            await run()
        if operation == "inspect":
            protocol.get_info.assert_awaited_once_with("existing")
        else:
            protocol.set_timeout.assert_awaited_once_with("existing", 600)
    http.close.assert_awaited_once_with()
    protocol.connect.assert_not_awaited()


@pytest.mark.parametrize("operation", ["inspect", "timeout"])
@pytest.mark.parametrize("fail", [False, True])
def test_sync_classmethod_aliases_dispatch_and_close(operation, fail):
    protocol = AsyncMock()
    protocol.get_info.return_value = SandboxInfo(sandbox_id="existing")
    target = protocol.get_info if operation == "inspect" else protocol.set_timeout
    if fail:
        target.side_effect = RuntimeError("operation failed")
    http = AsyncMock()
    with (
        patch("agent_sandbox.api.sandbox._select_provider", return_value=(None, "existing")),
        patch("agent_sandbox.api.sandbox._build_infra", return_value=(None, None, http, protocol)),
    ):

        def run():
            if operation == "inspect":
                return Sandbox.get_info_by_id_sync(
                    "existing", sandbox_domain="unused.example.invalid"
                )
            return Sandbox.set_timeout_by_id_sync(
                "existing", 600, sandbox_domain="unused.example.invalid"
            )

        if fail:
            with pytest.raises(RuntimeError, match="operation failed"):
                run()
        elif operation == "inspect":
            assert run().sandbox_id == "existing"
        else:
            run()
    if operation == "inspect":
        protocol.get_info.assert_awaited_once_with("existing")
    else:
        protocol.set_timeout.assert_awaited_once_with("existing", 600)
    protocol.connect.assert_not_awaited()
    http.close.assert_awaited_once_with()
