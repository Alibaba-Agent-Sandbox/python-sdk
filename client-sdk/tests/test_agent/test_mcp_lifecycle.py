"""MCP lifecycle orchestration, API delegation, and metadata disclosure tests."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from agent_sandbox.agent.mcp import SandboxManager, SandboxMCPServer
from agent_sandbox.agent.tools import dispatch_tool
from agent_sandbox.models.errors import InvalidAPIKeyError, SandboxError
from agent_sandbox.models.sandbox import SandboxInfo, SandboxStatus


def _info(sandbox_id: str = "sandbox-one") -> SandboxInfo:
    return SandboxInfo(
        sandbox_id=sandbox_id,
        template="base",
        status=SandboxStatus.RUNNING,
        started_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
        cpu_count=2,
        memory_mb=1024,
        envd_access_token="placeholder-private-token",
        metadata={"password": "placeholder-private-metadata"},
        lifecycle={"credentials": "placeholder-private-lifecycle"},
        envd_url="https://example.invalid/?token=placeholder-private-url",
        account_id="placeholder-private-account",
    )


def _sandbox(sandbox_id: str = "sandbox-one") -> AsyncMock:
    sandbox = AsyncMock()
    sandbox.id = sandbox_id
    sandbox.status = SandboxStatus.RUNNING
    sandbox.url = "https://example.invalid"
    sandbox.refresh_info.return_value = _info(sandbox_id)
    return sandbox


@pytest.mark.parametrize("tool", ["get_sandbox", "set_sandbox_timeout"])
async def test_existing_default_required_without_implicit_creation(tool):
    manager = SandboxManager()
    with patch("agent_sandbox.api.sandbox.Sandbox.create", new_callable=AsyncMock) as create:
        result = await dispatch_tool(
            tool, {"timeout": 500} if tool.startswith("set_") else {}, manager
        )
    assert "No default sandbox" in result["error"]
    create.assert_not_awaited()


async def test_list_delegates_filters_without_adopting_or_changing_default():
    manager = SandboxManager(
        api_key="placeholder-api-key",
        api_url="https://api.example.invalid",
        domain="example.invalid",
    )
    default = _sandbox("existing-default")
    manager._default_sandbox = default
    with patch(
        "agent_sandbox.api.sandbox.Sandbox.list", new_callable=AsyncMock, return_value=[_info()]
    ) as listing:
        result = await dispatch_tool(
            "list_sandboxes",
            {
                "status": "running",
                "limit": 10,
                "offset": 20,
                "provider": "example-provider",
                "region": "cn-shanghai",
            },
            manager,
        )
    listing.assert_awaited_once_with(
        api_key="placeholder-api-key",
        api_url="https://api.example.invalid",
        status=SandboxStatus.RUNNING,
        limit=10,
        offset=20,
        provider="example-provider",
        region="cn-shanghai",
    )
    assert result["limit"] == 10 and result["offset"] == 20
    assert result["sandboxes"][0]["sandbox_id"] == "sandbox-one"
    assert manager._default_sandbox is default
    assert manager._sandboxes == {}
    default.set_timeout.assert_not_awaited()


async def test_get_default_refreshes_real_api_without_renewing():
    manager = SandboxManager()
    sandbox = _sandbox()
    manager._default_sandbox = sandbox
    result = await dispatch_tool("get_sandbox", {}, manager)
    sandbox.refresh_info.assert_awaited_once_with()
    sandbox.set_timeout.assert_not_awaited()
    assert result["started_at"] == "2026-10-16T00:00:00+00:00"
    assert result["cpu_count"] == 2


@pytest.mark.parametrize("tool", ["get_sandbox", "list_sandboxes"])
async def test_metadata_allowlist_omits_nested_and_url_secrets(tool):
    manager = SandboxManager()
    manager._default_sandbox = _sandbox()
    with patch(
        "agent_sandbox.api.sandbox.Sandbox.list", new_callable=AsyncMock, return_value=[_info()]
    ):
        result = await dispatch_tool(tool, {}, manager)
    serialized = json.dumps(result)
    assert "placeholder-private" not in serialized
    item = result["sandboxes"][0] if tool == "list_sandboxes" else result
    assert set(item) == {
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


async def test_explicit_get_uses_direct_metadata_without_replacing_default():
    manager = SandboxManager(api_key="placeholder-api-key", api_url="https://api.example.invalid")
    default = _sandbox("default")
    manager._default_sandbox = default
    with (
        patch(
            "agent_sandbox.api.sandbox.Sandbox.get_info_by_id",
            new_callable=AsyncMock,
            return_value=_info("other"),
        ) as get,
        patch("agent_sandbox.api.sandbox.Sandbox.connect", new_callable=AsyncMock) as connect,
    ):
        result = await dispatch_tool("get_sandbox", {"sandbox_id": "other"}, manager)
    get.assert_awaited_once_with(
        sandbox_id="other", api_key="placeholder-api-key", api_url="https://api.example.invalid"
    )
    connect.assert_not_awaited()
    assert result["sandbox_id"] == "other"
    assert manager._default_sandbox is default
    assert manager._sandboxes == {}


async def test_explicit_get_failure_does_not_adopt_or_connect():
    manager = SandboxManager()
    with (
        patch(
            "agent_sandbox.api.sandbox.Sandbox.get_info_by_id",
            new_callable=AsyncMock,
            side_effect=RuntimeError("platform unavailable"),
        ),
        patch("agent_sandbox.api.sandbox.Sandbox.connect", new_callable=AsyncMock) as connect,
    ):
        result = await dispatch_tool("get_sandbox", {"sandbox_id": "other"}, manager)
    assert result["error"] == "Sandbox lifecycle operation failed."
    connect.assert_not_awaited()
    assert manager._sandboxes == {}


async def test_explicit_get_reuses_managed_instance_without_closing_it():
    manager = SandboxManager()
    target = _sandbox("managed")
    manager._sandboxes[target.id] = target
    result = await dispatch_tool("get_sandbox", {"sandbox_id": target.id}, manager)
    assert result["sandbox_id"] == target.id
    target.close.assert_not_awaited()
    target.refresh_info.assert_awaited_once_with()


async def test_timeout_update_is_single_api_call_and_controls_future_renewal():
    manager = SandboxManager()
    sandbox = _sandbox()
    manager._default_sandbox = sandbox
    manager._sandboxes[sandbox.id] = sandbox
    manager._lifetimes[sandbox.id] = 300
    result = await dispatch_tool("set_sandbox_timeout", {"timeout": 725}, manager)
    assert result == {"success": True, "sandbox_id": sandbox.id, "timeout": 725}
    sandbox.set_timeout.assert_awaited_once_with(725)
    await manager.get_sandbox()
    assert sandbox.set_timeout.await_args_list[-1].args == (725,)
    assert sandbox.set_timeout.await_count == 2


async def test_failed_timeout_update_preserves_previous_renewal_policy():
    manager = SandboxManager()
    sandbox = _sandbox()
    sandbox.set_timeout.side_effect = RuntimeError("platform unavailable")
    manager._default_sandbox = sandbox
    manager._lifetimes[sandbox.id] = 300
    result = await dispatch_tool("set_sandbox_timeout", {"timeout": 725}, manager)
    assert result["error"] == "Sandbox lifecycle operation failed."
    assert manager._lifetimes[sandbox.id] == 300
    sandbox.set_timeout.assert_awaited_once_with(725)


@pytest.mark.parametrize("fail", [False, True])
async def test_external_timeout_uses_direct_api_without_connect_or_adoption(fail):
    manager = SandboxManager()
    with (
        patch(
            "agent_sandbox.api.sandbox.Sandbox.set_timeout_by_id", new_callable=AsyncMock
        ) as update,
        patch("agent_sandbox.api.sandbox.Sandbox.connect", new_callable=AsyncMock) as connect,
    ):
        if fail:
            update.side_effect = RuntimeError("platform unavailable")
        result = await dispatch_tool(
            "set_sandbox_timeout", {"sandbox_id": "external", "timeout": 600}, manager
        )
    if fail:
        assert result["error"] == "Sandbox lifecycle operation failed."
    else:
        assert result == {"success": True, "sandbox_id": "external", "timeout": 600}
    update.assert_awaited_once_with(sandbox_id="external", timeout=600)
    connect.assert_not_awaited()
    assert manager._sandboxes == {}
    assert manager._lifetimes == {}
    assert manager._default_sandbox is None
    await manager.shutdown()


async def test_create_passes_only_real_sdk_resource_options():
    manager = SandboxManager(template="base")
    sandbox = _sandbox()
    with patch(
        "agent_sandbox.api.sandbox.Sandbox.create", new_callable=AsyncMock, return_value=sandbox
    ) as create:
        result = await dispatch_tool(
            "create_sandbox",
            {
                "region": "cn-shanghai",
                "cpu": 2,
                "memory": 1024,
                "provider": "example-provider",
                "timeout": 600,
            },
            manager,
        )
    create.assert_awaited_once_with(
        template="base",
        timeout=600,
        envs={},
        region="cn-shanghai",
        cpu=2,
        memory=1024,
        provider="example-provider",
    )
    assert result["sandbox_id"] == sandbox.id
    assert manager._default_sandbox is sandbox


@pytest.mark.parametrize(
    "tool, params",
    [
        ("list_sandboxes", {"limit": 0}),
        ("list_sandboxes", {"limit": 101}),
        ("list_sandboxes", {"limit": True}),
        ("list_sandboxes", {"offset": -1}),
        ("list_sandboxes", {"offset": 0.5}),
        ("list_sandboxes", {"status": "made-up"}),
        ("list_sandboxes", {"provider": ""}),
        ("get_sandbox", {"sandbox_id": None}),
        ("get_sandbox", {"sandbox_id": 42}),
        ("set_sandbox_timeout", {}),
        ("set_sandbox_timeout", {"timeout": 0}),
        ("set_sandbox_timeout", {"timeout": 86401}),
        ("set_sandbox_timeout", {"timeout": True}),
        ("set_sandbox_timeout", {"timeout": "300"}),
        ("create_sandbox", {"timeout": -1}),
        ("create_sandbox", {"cpu": 0}),
        ("create_sandbox", {"memory": 1.5}),
        ("create_sandbox", {"region": None}),
        ("create_sandbox", {"team": "unsupported"}),
        ("create_sandbox", {"envs": {"secret": 1}}),
        ("create_sandbox", {"envs": []}),
    ],
)
async def test_invalid_inputs_fail_before_any_platform_calls(tool, params):
    manager = AsyncMock()
    result = await dispatch_tool(tool, params, manager)
    assert "error" in result
    assert manager.mock_calls == []


@pytest.mark.parametrize("timeout", [1, 86400])
async def test_timeout_boundaries_are_accepted(timeout):
    manager = AsyncMock()
    manager.set_sandbox_timeout.return_value = "sandbox-one"
    result = await dispatch_tool("set_sandbox_timeout", {"timeout": timeout}, manager)
    assert result["timeout"] == timeout
    manager.set_sandbox_timeout.assert_awaited_once_with(timeout, None)


async def test_mcp_protocol_marks_validation_failure_as_tool_error():
    server = SandboxMCPServer()
    server._manager.set_sandbox_timeout = AsyncMock()
    response = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "set_sandbox_timeout",
                "arguments": {"timeout": 0},
            },
        }
    )
    assert response["result"]["isError"] is True
    assert "timeout" in json.loads(response["result"]["content"][0]["text"])["error"]
    server._manager.set_sandbox_timeout.assert_not_awaited()


def _private_exception(kind: str) -> Exception:
    """Synthetic private values never come from environment or real credentials."""
    secret = "SYNTHETIC_TEST_PRIVATE_TOKEN"
    url = f"https://example.invalid/sandboxes?token={secret}"
    request = httpx.Request("GET", url)
    if kind == "http":
        response = httpx.Response(500, request=request)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return exc
    if kind == "validation":
        try:
            SandboxInfo.model_validate({"envdAccessToken": secret})
        except Exception as exc:
            return exc
    if kind == "timeout":
        return httpx.ReadTimeout(f"private request {url}", request=request)
    if kind == "transport":
        return httpx.ConnectError(f"private request {url}", request=request)
    if kind == "sdk":
        return InvalidAPIKeyError(f"private credential {secret}", suggestion=f"Visit {url}")
    if kind == "sdk-code":
        return SandboxError(secret, code=f"E0000 {secret}", suggestion=url)
    if kind == "value":
        return ValueError(f"private input {secret}")
    return RuntimeError(f"private provider response {url}")


@pytest.mark.parametrize(
    "tool, method, params",
    [
        ("create_sandbox", "create_sandbox", {"envs": {"PRIVATE": "SYNTHETIC_TEST_PRIVATE_TOKEN"}}),
        ("list_sandboxes", "list_sandboxes", {}),
        ("get_sandbox", "inspect_sandbox", {}),
        ("set_sandbox_timeout", "set_sandbox_timeout", {"timeout": 600}),
    ],
)
@pytest.mark.parametrize(
    "kind", ["http", "validation", "timeout", "transport", "sdk", "sdk-code", "value", "unknown"]
)
async def test_lifecycle_failures_never_disclose_private_values_in_results_or_logs(
    tool, method, params, kind, caplog
):
    manager = AsyncMock()
    getattr(manager, method).side_effect = _private_exception(kind)
    result = await dispatch_tool(tool, params, manager)
    assert "error" in result
    serialized = json.dumps(result)
    for text in (serialized, caplog.text):
        assert "SYNTHETIC_TEST_PRIVATE_TOKEN" not in text
        assert "example.invalid" not in text
        assert "envdAccessToken" not in text
        assert "Traceback" not in text
    assert caplog.records
    assert all(record.exc_info is None for record in caplog.records)
    if kind == "http":
        assert "HTTP 500" in result["error"]
    elif kind == "sdk":
        assert result["error"] == "[E1001] Sandbox authentication failed."
        assert result["suggestion"] == "Check the authorized provider credential configuration."


async def test_lifecycle_input_validation_does_not_echo_private_argument_names(caplog):
    manager = AsyncMock()
    result = await dispatch_tool(
        "create_sandbox", {"SYNTHETIC_TEST_PRIVATE_TOKEN": "private value"}, manager
    )
    assert "Unsupported argument" in result["error"]
    assert "SYNTHETIC_TEST_PRIVATE_TOKEN" not in json.dumps(result)
    assert "SYNTHETIC_TEST_PRIVATE_TOKEN" not in caplog.text
    assert manager.mock_calls == []


async def test_late_managed_timeout_after_shutdown_does_not_restore_renewal_state():
    manager = SandboxManager()
    sandbox = _sandbox("managed")
    manager._sandboxes[sandbox.id] = sandbox
    manager._default_sandbox = sandbox
    manager._lifetimes[sandbox.id] = 300
    started = asyncio.Event()
    release = asyncio.Event()

    async def pending_timeout(_seconds):
        started.set()
        await release.wait()

    sandbox.set_timeout.side_effect = pending_timeout
    operation = asyncio.create_task(manager.set_sandbox_timeout(700))
    await started.wait()
    await manager.shutdown()
    release.set()
    await operation
    assert manager._sandboxes == {}
    assert manager._lifetimes == {}
    assert manager._default_sandbox is None
