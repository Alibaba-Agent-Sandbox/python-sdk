"""Volume mount hints must survive creation and fail before provider I/O."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.engine.client import Engine
from agent_sandbox.engine.engine_pb2 import CreateRequest, HealthStatus
from agent_sandbox.engine.server import ProviderEngine
from agent_sandbox.models.errors import (
    ProviderConfigError,
    ProviderFeatureNotSupportedError,
    ProviderNotFoundError,
)
from agent_sandbox.models.sandbox import SandboxConfig
from agent_sandbox.providers.base import Provider, ProviderInfra
from agent_sandbox.providers.registry import get_provider
from agent_sandbox.transport.auth_contract import SessionAuth
from agent_sandbox.transport.config import TransportConfig
from tests.test_api.conftest import make_sandbox_info

INVALID = [
    [],
    "volume",
    {"relative": "volume"},
    {"/": "volume"},
    {"/mnt//data": "volume"},
    {"/mnt/data/": "volume"},
    {"/mnt/../data": "volume"},
    {"/mnt/./data": "volume"},
    {"/mnt/.cache": "volume"},
    {" /mnt/data": "volume"},
    {"/mnt/data ": "volume"},
    {"/mnt/\x00data": "volume"},
    {"/bin/data": "volume"},
    {"/opt": "volume"},
    {"/var/data": "volume"},
    {"/dev/data": "volume"},
    {"__proto__": "volume"},
    {"constructor": "volume"},
    {"prototype": "volume"},
    {"/mnt/data": ""},
    {"/mnt/data": " "},
    {"/mnt/data": " padded"},
    {"/mnt/data": "volume\x00name"},
    {"/mnt/data": 123},
    {123: "volume"},
]


@pytest.mark.parametrize("mounts", INVALID)
async def test_invalid_mounts_never_select_or_build_provider(mounts: Any) -> None:
    with (
        patch("agent_sandbox.api.sandbox._select_provider") as select,
        patch("agent_sandbox.api.sandbox._build_infra") as build,
        pytest.raises(ProviderConfigError),
    ):
        await Sandbox.create(volume_mounts=mounts)
    select.assert_not_called()
    build.assert_not_called()
    with pytest.raises(ProviderConfigError):
        SandboxConfig(volume_mounts=mounts)
    with patch("agent_sandbox.engine.client._channel") as channel:
        with pytest.raises(ProviderConfigError):
            await Engine().create(volume_mounts=mounts)
        channel.assert_not_called()


async def test_unknown_provider_mounts_fail_before_building() -> None:
    with patch("agent_sandbox.api.sandbox._provider_infra") as build:
        with pytest.raises(ProviderNotFoundError):
            await Sandbox.create(
                provider="uninstalled-plugin", volume_mounts={"/mnt/data": "volume"}
            )
        build.assert_not_called()


async def test_plugin_mounts_require_explicit_create_option() -> None:
    class Plugin(Provider):
        id = "programmatic-plugin"

        async def build_infra(self, config):
            raise AssertionError("must fail before provider I/O")

    with pytest.raises(ProviderFeatureNotSupportedError):
        await Sandbox.create(provider=Plugin(), volume_mounts={"/mnt/data": "volume"})


@pytest.mark.parametrize("mounts", [None, {}, {"/mnt/data": "existing-volume"}])
async def test_builtin_api_forwards_only_nonempty_mounts(mounts: Any) -> None:
    http = AsyncMock()
    provider = get_provider("alicloud-express")

    async def factory(config):
        return ProviderInfra(config, None, http, provider_lifecycle, close=http.close)

    from agent_sandbox.providers.alicloud_express.lifecycle import EngineLifecycle

    provider_lifecycle = EngineLifecycle(http, TransportConfig())
    with (
        patch.object(provider, "build_infra", side_effect=factory),
        patch.object(
            provider,
            "prepare_session",
            new_callable=AsyncMock,
            return_value={"envd_token": SessionAuth(None, "sb-1")},
        ),
        patch("agent_sandbox.engine.client.Engine.create", new_callable=AsyncMock) as create,
    ):
        create.return_value = make_sandbox_info()
        sandbox = await Sandbox.create(volume_mounts=mounts)
        if mounts:
            assert create.call_args.kwargs["volume_mounts"] == mounts
        else:
            assert "volume_mounts" not in create.call_args.kwargs
        await sandbox.close()
    http.close.assert_awaited_once()


def test_model_exact_wire_and_empty_compatibility() -> None:
    mounts = {"/mnt/data": "existing-volume"}
    config = SandboxConfig(volume_mounts=mounts)
    mounts.clear()
    assert config.to_create_payload()["volumeMounts"] == [
        {"name": "existing-volume", "path": "/mnt/data"}
    ]
    assert "volumeMounts" not in SandboxConfig().to_create_payload()
    assert "volumeMounts" not in SandboxConfig(volume_mounts={}).to_create_payload()
    config.volume_mounts["/"] = "volume"
    with pytest.raises(ProviderConfigError):
        config.to_create_payload()


async def test_engine_nonbuiltin_mounts_never_open_channel() -> None:
    with patch("agent_sandbox.engine.client._channel") as channel:
        with pytest.raises(ProviderNotFoundError):
            await Engine().create(provider="plugin", volume_mounts={"/mnt/data": "volume"})
        channel.assert_not_called()


@pytest.mark.parametrize("provider,path", [("plugin", "/mnt/data"), ("", "/")])
async def test_raw_grpc_request_cannot_bypass_provider_or_path_gate(
    provider: str, path: str
) -> None:
    request = CreateRequest(provider=provider, volume_mounts={path: "volume"})
    context = AsyncMock()
    with patch("agent_sandbox.api.sandbox._build_infra") as build:
        await ProviderEngine().Create(request, context)
        build.assert_not_called()
    error = json.loads(context.abort.call_args.args[1])
    assert error["code"] == ("E8001" if provider else "E8002")


@pytest.mark.parametrize("mounts", [None, {}, {"/mnt/data": "volume"}])
async def test_old_live_engine_requires_mount_capability_only_for_nonempty_hints(
    mounts: Any,
) -> None:
    stub = MagicMock()
    stub.Health = AsyncMock(return_value=HealthStatus(protocol="abx.engine.v1", version="0.3.0"))
    stub.Create = AsyncMock()
    with (
        patch("agent_sandbox.engine.client._channel", return_value=AsyncMock()),
        patch("agent_sandbox.engine.client._grpc_mod.ProviderEngineStub", return_value=stub),
    ):
        if mounts:
            with pytest.raises(ProviderFeatureNotSupportedError) as caught:
                await Engine().create(volume_mounts=mounts)
            assert caught.value.feature == "volume_mounts"
            stub.Health.assert_awaited_once()
            stub.Create.assert_not_awaited()
        else:
            with patch("agent_sandbox.engine.client._state", return_value=make_sandbox_info()):
                await Engine().create(volume_mounts=mounts)
            stub.Health.assert_not_awaited()
            stub.Create.assert_awaited_once()
