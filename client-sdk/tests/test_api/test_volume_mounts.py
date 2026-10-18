"""Volume mount hints must survive creation and fail before provider I/O."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.models.errors import (
    ProviderConfigError,
    ProviderFeatureNotSupportedError,
    ProviderNotFoundError,
)
from agent_sandbox.models.sandbox import SandboxConfig
from agent_sandbox.providers.base import Provider, ProviderInfra
from agent_sandbox.providers.registry import get_provider
from agent_sandbox.transport.auth_contract import SessionAuth
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

    provider_lifecycle = AsyncMock()
    provider_lifecycle.create.return_value = make_sandbox_info()
    with (
        patch.object(provider, "build_infra", side_effect=factory),
        patch.object(
            provider,
            "prepare_session",
            new_callable=AsyncMock,
            return_value={"envd_token": SessionAuth(None, "sb-1")},
        ),
    ):
        sandbox = await Sandbox.create(volume_mounts=mounts)
        forwarded = provider_lifecycle.create.call_args.args[0]
        assert forwarded.volume_mounts == (mounts or {})
        assert ("volumeMounts" in forwarded.to_create_payload()) is bool(mounts)
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


def test_retired_native_grpc_bridge_is_not_packaged() -> None:
    import importlib.util

    assert importlib.util.find_spec("agent_sandbox.engine") is None
