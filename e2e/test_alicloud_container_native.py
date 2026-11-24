"""Native Client SDK verification against an existing Container Edition cluster."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import e2e_helpers as H  # noqa: N812
import pytest

from agent_sandbox._version import __version__
from agent_sandbox.models.errors import SandboxNotFoundError
from agent_sandbox.models.sandbox import SandboxConfig
from agent_sandbox.providers import ProviderClient, ProviderLock
from agent_sandbox.transport.config import TransportConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any

pytestmark = pytest.mark.provider_live


def test_alicloud_container_native(run: Callable[[Coroutine[Any, Any, None]], None]) -> None:
    provider = "alicloud-container"
    base = os.environ.get("ABX_ALICLOUD_CONTAINER_BASE_URL", "").strip()
    domain = os.environ.get("ABX_ALICLOUD_CONTAINER_DOMAIN", "").strip()
    key = os.environ.get("ABX_ALICLOUD_CONTAINER_API_KEY", "").strip()
    if not key or not (base or domain):
        pytest.skip(
            "Set Container Edition API key and domain or private API URL for a live cluster."
        )
    options = {
        "api_key": key,
        "protocol": os.environ.get("ABX_ALICLOUD_CONTAINER_PROTOCOL", "native"),
    }
    if base:
        options["base_url"] = base
    if domain:
        options["domain"] = domain
    run(
        _exercise(
            ProviderLock(provider=provider, version=__version__),
            TransportConfig(provider=provider, provider_options=options),
        )
    )


async def _exercise(lock: ProviderLock, config: TransportConfig) -> None:
    template = os.environ.get("E2E_CONTAINER_SANDBOX_SET", "code-interpreter")
    owned: list[str] = []
    async with await ProviderClient.prepare(lock, config) as client:
        assert client.implementation == "python-native"
        try:
            sandbox = await client.create(
                SandboxConfig(template=template, timeout=300, metadata=H.tag_metadata("container")),
                on_created=owned.append,
            )
            try:
                result = await sandbox.commands.run("printf container-native")
                assert result.exit_code == 0 and result.stdout == "container-native"
                path = "/tmp/container-native-roundtrip.txt"
                await sandbox.files.write(path, "roundtrip")
                assert await sandbox.files.read(path) == "roundtrip"
                await sandbox.files.remove(path)
                code = await sandbox.run_code("print(42)", mode="default-context")
                assert code.exit_code == 0 and code.stdout.strip() == "42"
                assert (await client.get(sandbox.id)).sandbox_id == sandbox.id
                await client.set_timeout(sandbox.id, 300)
                url, _ = await sandbox.network.resolve(49999)
                assert "49999" in url
            finally:
                await sandbox.close()
            attached = await client.connect(sandbox.id)
            try:
                assert attached.id == sandbox.id
            finally:
                await attached.close()
        finally:
            for sandbox_id in owned:
                await client.delete(sandbox_id)
                with pytest.raises(SandboxNotFoundError):
                    await client.get(sandbox_id)
