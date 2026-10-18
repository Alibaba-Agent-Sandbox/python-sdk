"""Guard backend boundaries and owned/borrowed cleanup through the public lifecycle."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.models.sandbox import SandboxInfo
from agent_sandbox.providers.base import Provider, ProviderInfra
from agent_sandbox.providers.registry import register_provider
from agent_sandbox.transport.config import TransportConfig, load_config
from tests.iso import iso  # noqa: F401


class IsolatedProvider(Provider):
    id = "isolation-test"
    features = frozenset({"sandbox.lifecycle"})

    def __init__(self) -> None:
        self.killed = AsyncMock()
        self.closed = AsyncMock()

    async def build_infra(self, config: TransportConfig) -> ProviderInfra:
        info = SandboxInfo(sandbox_id="owned", template="base", envd_url="custom://session")
        protocol = type("Lifecycle", (), {})()
        protocol.create = AsyncMock(return_value=info)
        protocol.connect = AsyncMock(return_value=info)
        protocol.kill = self.killed
        return ProviderInfra(
            config=config, auth=None, http_client=None, sandbox_protocol=protocol, close=self.closed
        )

    async def prepare_session(self, *args: object, **kwargs: object) -> dict:
        raise ValueError("binding failed")


@pytest.mark.asyncio
async def test_created_resource_is_cleaned_on_binding_failure(iso):  # noqa: F811
    provider = IsolatedProvider()
    register_provider(provider)
    with pytest.raises(ValueError, match="binding failed"):
        await Sandbox.create(provider=provider.id)
    provider.killed.assert_awaited_once_with("owned")
    provider.closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_borrowed_resource_is_kept_on_binding_failure(iso):  # noqa: F811
    provider = IsolatedProvider()
    register_provider(provider)
    with pytest.raises(ValueError, match="binding failed"):
        await Sandbox.connect("owned", provider=provider.id)
    provider.killed.assert_not_awaited()
    provider.closed.assert_awaited_once()


def test_direct_and_layered_config_do_not_inherit_cloud_defaults(iso):  # noqa: F811
    provider = IsolatedProvider()
    register_provider(provider)
    for config in (TransportConfig(provider=provider.id), load_config(provider=provider.id)):
        assert (config.sandbox_base_url, config.sandbox_domain, config.region) == ("", "", "")
    explicit = TransportConfig(provider=provider.id, sandbox_base_url="https://provider.example")
    assert explicit.sandbox_base_url == "https://provider.example"


def test_core_imports_no_concrete_backend_implementation() -> None:
    root = Path(__file__).parents[2] / "src" / "agent_sandbox"
    violations = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        if relative.startswith("providers/"):
            continue
        tree = ast.parse(path.read_text())
        # Historical public modules remain explicit export facades, including monkeypatch identity.
        if relative in {
            "transport/auth.py",
            "transport/__init__.py",
            "protocol/__init__.py",
            "protocol/sandbox.py",
            "protocol/filesystem.py",
            "protocol/process.py",
            "protocol/code_interpreter.py",
            "protocol/terminal.py",
        }:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if (
                    any(
                        marker in module
                        for marker in (
                            "providers.alicloud_express",
                            "providers.shared.e2b",
                            "protocol.sandbox",
                            "protocol.filesystem",
                            "protocol.process",
                            "protocol.terminal",
                            "protocol.code_interpreter",
                            "transport.auth",
                        )
                    )
                    and "auth_contract" not in module
                ):
                    violations.append(f"{relative}: {module}")
    assert violations == []


@pytest.mark.asyncio
async def test_native_http_keeps_explicit_provider_over_ambient(iso, monkeypatch):  # noqa: F811
    from unittest.mock import patch

    from agent_sandbox.providers.alicloud_express.provider import AlicloudExpressProvider
    from agent_sandbox.providers.shared.e2b.sandbox import SandboxProtocol

    monkeypatch.setenv("ABX_PROVIDER", "another-provider")
    provider = AlicloudExpressProvider()
    infra = await provider.build_infra(
        TransportConfig(provider="alicloud-express", sandbox_api_key="fixture-key")
    )
    try:
        assert isinstance(infra.sandbox_protocol, SandboxProtocol)
        assert infra.config.provider == "alicloud-express"
        info = SandboxInfo(sandbox_id="owned", template="base")
        with patch.object(
            infra.sandbox_protocol, "create", new_callable=AsyncMock, return_value=info
        ) as create:
            from agent_sandbox.models.sandbox import SandboxConfig

            assert await infra.sandbox_protocol.create(SandboxConfig()) is info
        create.assert_awaited_once()
    finally:
        await infra.http_client.close()
