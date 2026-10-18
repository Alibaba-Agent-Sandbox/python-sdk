"""Volume mount hints must survive creation and fail before provider I/O."""

from __future__ import annotations

import json
import sys
from typing import Any
from unittest.mock import patch

import pytest

from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.models.errors import (
    ProviderConfigError,
    ProviderFeatureNotSupportedError,
    ProviderNotFoundError,
)
from agent_sandbox.models.sandbox import SandboxConfig
from agent_sandbox.providers.base import Provider

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
async def test_builtin_api_forwards_only_nonempty_mounts(mounts, httpx_mock, monkeypatch):
    monkeypatch.setitem(sys.modules, "agent_sandbox.engine", None)
    monkeypatch.setenv("ABX_PROVIDER", "uninstalled-plugin")
    httpx_mock.add_response(
        method="POST",
        url="https://platform.invalid/sandboxes",
        status_code=201,
        json={
            "sandboxID": "owned",
            "envdUrl": "https://envd.invalid",
            "envdAccessToken": "placeholder-token",
        },
    )
    httpx_mock.add_response(
        method="DELETE", url="https://platform.invalid/sandboxes/owned", status_code=204
    )
    sandbox = await Sandbox.create(
        provider="alicloud-express",
        api_key="placeholder-key",
        api_url="https://platform.invalid",
        volume_mounts=mounts,
    )
    try:
        payload = json.loads(httpx_mock.get_requests()[0].content)
        if mounts:
            assert payload["volumeMounts"] == [{"name": "existing-volume", "path": "/mnt/data"}]
        else:
            assert "volumeMounts" not in payload
    finally:
        await sandbox.kill()


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
