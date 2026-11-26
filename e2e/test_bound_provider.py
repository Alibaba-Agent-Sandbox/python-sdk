"""Exercise an explicit native Provider binding against Express."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import e2e_helpers as H  # noqa: N812
import pytest

from agent_sandbox.models.errors import SandboxNotFoundError
from agent_sandbox.models.sandbox import SandboxConfig
from agent_sandbox.providers import ProviderClient, ProviderLock
from agent_sandbox.providers.alicloud_express.provider import AlicloudExpressProvider
from agent_sandbox.transport.config import TransportConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any


def test_native_provider_target(run: Callable[[Coroutine[Any, Any, None]], None]) -> None:
    if H.missing_env(("ABX_SANDBOX_BASE_URL", "ABX_SANDBOX_DOMAIN")):
        pytest.skip("The bound test requires an explicit API URL and domain.")
    run(_test_native_provider_target())


async def _test_native_provider_target() -> None:
    provider = AlicloudExpressProvider()
    lock = ProviderLock(provider=provider.id, version=provider.version)
    config = TransportConfig(
        provider=provider.id,
        sandbox_api_key=os.environ["ABX_SANDBOX_API_KEY"],
        sandbox_base_url=os.environ["ABX_SANDBOX_BASE_URL"],
        sandbox_domain=os.environ["ABX_SANDBOX_DOMAIN"],
    )
    async with await ProviderClient.prepare(
        lock,
        config,
        native=provider,
        required_features=("sandbox.lifecycle", "exec.run", "files.rw"),
    ) as client:
        sandbox = await client.create(
            SandboxConfig(template=H.OFFICIAL_BASE, timeout=180, metadata=H.tag_metadata("bound"))
        )
        sandbox_id = sandbox.id
        try:
            result = await sandbox.commands.run("printf bound")
            assert result.stdout == "bound" and result.exit_code == 0
            await sandbox.files.write("/tmp/provider-binding.txt", "checked")
            assert await sandbox.files.read("/tmp/provider-binding.txt") == "checked"
            assert (await client.get(sandbox_id)).sandbox_id == sandbox_id
        finally:
            try:
                await client.delete(sandbox_id)
            finally:
                await sandbox.close()

        with pytest.raises(SandboxNotFoundError):
            await client.get(sandbox_id)
