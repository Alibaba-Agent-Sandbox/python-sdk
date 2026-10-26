"""MCP creation must verify requested resources before reporting success."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent_sandbox.agent.mcp import SandboxManager
from agent_sandbox.agent.tools import dispatch_tool
from agent_sandbox.models.errors import SandboxNotFoundError
from agent_sandbox.models.sandbox import SandboxInfo, SandboxStatus
from agent_sandbox.transport.config import TransportConfig


def sandbox(sid):
    result = AsyncMock()
    result.id = sid
    result.provider = "alicloud-express"
    result.status = SandboxStatus.RUNNING
    result.url = "https://example.invalid"
    result._config = TransportConfig(sandbox_base_url="https://example.invalid")
    result.refresh_info.return_value = SandboxInfo(
        sandbox_id=sid, status=SandboxStatus.RUNNING, cpu_count=2, memory_mb=1024
    )
    return result


async def test_matching_resources_require_actual_metadata_read():
    manager = SandboxManager()
    created = sandbox("new")
    with patch("agent_sandbox.api.sandbox.Sandbox.create", return_value=created):
        result = await dispatch_tool("create_sandbox", {"cpu": 2, "memory": 1024}, manager)
    assert "error" not in result
    created.refresh_info.assert_awaited_once_with()
    created.kill.assert_not_awaited()
    await manager.shutdown()


async def test_mismatch_rolls_back_only_new_sandbox_and_reports_observation():
    manager = SandboxManager()
    existing = sandbox("existing")
    created = sandbox("new")
    with (
        patch("agent_sandbox.api.sandbox.Sandbox.create", side_effect=[existing, created]),
        patch(
            "agent_sandbox.agent.create_resources._read_created_metadata",
            return_value=True,
        ),
    ):
        await manager.create_sandbox()
        result = await dispatch_tool("create_sandbox", {"cpu": 3, "memory": 1280}, manager)
    assert result["category"] == "resource_configuration"
    assert result["requested_resources"] == {"cpu": 3, "memory": 1280}
    assert result["observed_resources"] == {"cpu": 2, "memory": 1024}
    assert result["cleanup_verified"] is True
    created.kill.assert_awaited_once_with()
    existing.kill.assert_not_awaited()
    assert manager._sandboxes == {"alicloud-express:existing": existing}
    await manager.shutdown()


async def test_unknown_metadata_is_not_success_and_does_not_expose_provider_error():
    manager = SandboxManager()
    created = sandbox("new")
    created.refresh_info.side_effect = RuntimeError("secret-provider-token")
    with (
        patch("agent_sandbox.api.sandbox.Sandbox.create", return_value=created),
        patch(
            "agent_sandbox.agent.create_resources._read_created_metadata",
            return_value=True,
        ),
    ):
        result = await dispatch_tool("create_sandbox", {"cpu": 2}, manager)
    assert result["category"] == "resource_configuration"
    assert result["observed_resources"] == {"cpu": None, "memory": None}
    assert result["cleanup_verified"] is True
    assert "secret-provider-token" not in str(result)
    created.kill.assert_awaited_once_with()
    await manager.shutdown()


@pytest.mark.parametrize("deleted", [False, True])
async def test_ambiguous_delete_requires_independent_absence_and_preserves_recovery_id(deleted):
    manager = SandboxManager()
    created = sandbox("new")
    created.kill.side_effect = RuntimeError("secret-delete-response")
    with (
        patch("agent_sandbox.api.sandbox.Sandbox.create", return_value=created),
        patch(
            "agent_sandbox.agent.create_resources._read_created_metadata", return_value=deleted
        ) as observe,
    ):
        result = await dispatch_tool("create_sandbox", {"memory": 2048}, manager)
    assert result["category"] == "resource_configuration"
    assert result["cleanup_verified"] is deleted
    assert result["sandbox_id"] == "alicloud-express:new"
    if not deleted:
        assert result["recovery_sandbox_id"] == "alicloud-express:new"
    observe.assert_awaited_once()
    assert observe.call_args.args[0] is created
    assert observe.call_args.args[1].sandbox_base_url == "https://example.invalid"
    assert "secret-" not in str(result)
    await manager.shutdown()


async def test_cleanup_never_uses_default_endpoint_after_regional_delete_failure():
    manager = SandboxManager()
    created = sandbox("new-region")
    created._config = TransportConfig(
        region="cn-shanghai",
        sandbox_base_url="https://shanghai.example.invalid",
        sandbox_api_key="private-config-key",
        provider_options={"scope": "private-options"},
    )
    created.kill.side_effect = TimeoutError("delete outcome unknown")
    fresh_protocol = SimpleNamespace(
        get_info=AsyncMock(return_value=created.refresh_info.return_value)
    )
    fresh = SimpleNamespace(sandbox_protocol=fresh_protocol, close=AsyncMock())
    provider = SimpleNamespace(build_infra=AsyncMock(return_value=fresh))
    with (
        patch("agent_sandbox.api.sandbox.Sandbox.create", return_value=created),
        patch(
            "agent_sandbox.api.sandbox.Sandbox.get_info_by_id",
            side_effect=SandboxNotFoundError("default region has no such sandbox"),
        ) as default_read,
        patch("agent_sandbox.providers.registry.get_provider", return_value=provider),
    ):
        result = await dispatch_tool("create_sandbox", {"cpu": 3, "region": "cn-shanghai"}, manager)
    assert result["cleanup_verified"] is False
    assert result["recovery_sandbox_id"] == "alicloud-express:new-region"
    default_read.assert_not_awaited()
    observed_config = provider.build_infra.call_args.args[0]
    assert observed_config is not created._config
    assert observed_config.region == "cn-shanghai"
    assert observed_config.sandbox_base_url == "https://shanghai.example.invalid"
    assert observed_config.sandbox_api_key == "private-config-key"
    assert observed_config.provider_options == {"scope": "private-options"}
    fresh_protocol.get_info.assert_awaited_once_with("new-region")
    fresh.close.assert_awaited_once_with()
    assert "private-" not in str(result)
    await manager.shutdown()


@pytest.mark.parametrize("phase", ["setup", "query", "close"])
async def test_non_query_not_found_does_not_claim_sandbox_absence(phase):
    from agent_sandbox.agent.create_resources import verify_created_resources

    created = sandbox("new")
    manager = SandboxManager()
    error = SandboxNotFoundError("not a sandbox read")
    fresh = SimpleNamespace(
        sandbox_protocol=SimpleNamespace(
            get_info=AsyncMock(
                return_value=created.refresh_info.return_value,
                side_effect=error if phase == "query" else None,
            )
        ),
        close=AsyncMock(side_effect=error if phase == "close" else None),
    )
    provider = SimpleNamespace(
        build_infra=AsyncMock(return_value=fresh, side_effect=error if phase == "setup" else None)
    )
    with (
        patch("agent_sandbox.providers.registry.get_provider", return_value=provider),
    ):
        result = await verify_created_resources(manager, created, {"cpu": 3})
    assert result["cleanup_verified"] is (phase == "query")
    if phase != "query":
        assert result["recovery_sandbox_id"] == "alicloud-express:new"
    await manager.shutdown()


@pytest.mark.parametrize("replacement", [False, True])
async def test_rollback_keeps_new_handle_identity_after_metadata_await(replacement):
    """Session cleanup/cache replacement cannot redirect deletion to a default endpoint."""
    manager = SandboxManager()
    created = sandbox("regional-new")
    created._config = TransportConfig(
        region="cn-shanghai", sandbox_base_url="https://shanghai.example.invalid"
    )
    other = sandbox("regional-new")
    key = manager._sandbox_key(created)

    async def metadata_after_concurrent_cleanup(*args):
        async with manager._state_lock:
            manager._sandboxes.clear()
            manager._lifetimes.clear()
            manager._owned_sandbox_ids.clear()
            manager._default_sandbox = None
            if replacement:
                manager._sandboxes[key] = other
                manager._lifetimes[key] = 900
                manager._owned_sandbox_ids.add(key)
                manager._default_sandbox = other
        return created.refresh_info.return_value

    with (
        patch("agent_sandbox.api.sandbox.Sandbox.create", return_value=created),
        patch.object(
            created,
            "refresh_info",
            side_effect=metadata_after_concurrent_cleanup,
            return_value=created.refresh_info.return_value,
        ),
        patch("agent_sandbox.api.sandbox.Sandbox.kill_by_id") as fallback,
        patch("agent_sandbox.agent.create_resources._read_created_metadata", return_value=True),
    ):
        result = await dispatch_tool("create_sandbox", {"cpu": 3, "region": "cn-shanghai"}, manager)
    created.kill.assert_awaited_once_with()
    other.kill.assert_not_awaited()
    fallback.assert_not_awaited()
    assert result["cleanup_verified"] is True
    if replacement:
        assert manager._sandboxes[key] is other
        assert manager._lifetimes[key] == 900
        assert key in manager._owned_sandbox_ids
        assert manager._default_sandbox is other
    else:
        assert not manager._sandboxes
    await manager.shutdown()


@pytest.mark.parametrize("replacement", [False, True])
async def test_initial_verification_cannot_accept_other_handle_or_default_endpoint(replacement):
    manager = SandboxManager()
    created = sandbox("regional-new")
    other = sandbox("regional-new")
    other.refresh_info.return_value.cpu_count = 3
    key = manager._sandbox_key(created)
    actual_create = manager.create_sandbox

    async def create_then_concurrent_cleanup(**kwargs):
        result = await actual_create(**kwargs)
        async with manager._state_lock:
            manager._sandboxes.clear()
            manager._lifetimes.clear()
            manager._owned_sandbox_ids.clear()
            manager._default_sandbox = None
            if replacement:
                manager._sandboxes[key] = other
                manager._owned_sandbox_ids.add(key)
        return result

    with (
        patch("agent_sandbox.api.sandbox.Sandbox.create", return_value=created),
        patch.object(manager, "create_sandbox", side_effect=create_then_concurrent_cleanup),
        patch(
            "agent_sandbox.api.sandbox.Sandbox.get_info_by_id",
            return_value=other.refresh_info.return_value,
        ) as fallback,
        patch("agent_sandbox.agent.create_resources._read_created_metadata", return_value=True),
    ):
        result = await dispatch_tool("create_sandbox", {"cpu": 3}, manager)
    assert result["category"] == "resource_configuration"
    assert result["observed_resources"]["cpu"] == 2
    created.refresh_info.assert_awaited_once_with()
    other.refresh_info.assert_not_awaited()
    fallback.assert_not_awaited()
    other.kill.assert_not_awaited()
    await manager.shutdown()
