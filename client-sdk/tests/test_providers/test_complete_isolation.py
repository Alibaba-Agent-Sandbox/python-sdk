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
            "protocol/port.py",
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


def test_wire_adapter_owns_url_without_legacy_transport_helper(monkeypatch):
    from agent_sandbox.providers.alicloud_express.provider import AlicloudExpressProvider

    def legacy_helper(*args):
        raise AssertionError("legacy config URL helper used")

    monkeypatch.setattr(TransportConfig, "build_envd_url", legacy_helper)
    provider = AlicloudExpressProvider()
    info = SandboxInfo(sandbox_id="owned")
    config = TransportConfig(sandbox_domain="protocol.test")
    assert provider.resolve_session_url(info, config) == "https://49983-owned.protocol.test"


def test_bundled_schema_does_not_discover_registry_in_a_fresh_process():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from agent_sandbox.transport.config import _builtin_schema; "
            "schema = _builtin_schema(); assert schema.provider_id == 'alicloud-express'; "
            "assert 'agent_sandbox.providers.registry' not in sys.modules",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_core_contract_import_does_not_load_builtin_auth_or_wire():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from agent_sandbox.transport.http import HttpClient; "
            "from agent_sandbox.protocol import contracts; "
            "assert 'agent_sandbox.providers.alicloud_express.auth' not in sys.modules; "
            "assert 'agent_sandbox.providers.shared.e2b.sandbox' not in sys.modules",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_async_provider_ports_never_inherit_native_addresses_or_headers(iso):  # noqa: F811
    from agent_sandbox.models.errors import ProviderFeatureNotSupportedError
    from agent_sandbox.transport.auth_contract import SessionAuth

    class PortProvider(IsolatedProvider):
        features = frozenset({"sandbox.lifecycle", "ports.url"})

        async def prepare_session(self, *args, **kwargs):
            return {"envd_token": SessionAuth("opaque-token", "owned")}

        async def build_infra(self, config):
            infra = await super().build_infra(config)
            infra.sandbox_protocol.has_port_url = True
            infra.sandbox_protocol.port_url = AsyncMock(
                return_value=(
                    "https://gateway.example/owned/service",
                    {"Provider-Gateway": "placeholder"},
                )
            )
            return infra

    sandbox = await Sandbox.create(provider=PortProvider())
    try:
        with pytest.raises(ProviderFeatureNotSupportedError):
            sandbox.network.get_url(8080)
        with pytest.raises(ProviderFeatureNotSupportedError):
            sandbox.network.get_access_headers()
        assert await sandbox.network.resolve(8080) == (
            "https://gateway.example/owned/service",
            {"Provider-Gateway": "placeholder"},
        )
        with pytest.raises(ProviderFeatureNotSupportedError):
            sandbox.server_at()
    finally:
        await sandbox.kill()


def test_legacy_config_url_uses_the_composed_owned_builder(monkeypatch):
    from agent_sandbox.providers.alicloud_express.metadata import CONFIG_METADATA

    monkeypatch.setitem(
        CONFIG_METADATA,
        "legacy_url_builder",
        lambda sandbox_id, domain: f"https://{domain}/owned/{sandbox_id}",
    )
    assert TransportConfig(sandbox_domain="owned.example").build_envd_url("opaque") == (
        "https://owned.example/owned/opaque"
    )
