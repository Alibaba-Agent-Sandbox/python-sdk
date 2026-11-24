"""Prepared provider selection, target binding and cache contracts."""

from __future__ import annotations

import hashlib
import io
import tarfile
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from agent_sandbox.api import sandbox as sandbox_module
from agent_sandbox.models.errors import (
    ProviderConfigError,
    ProviderFeatureNotSupportedError,
    ProviderMismatchError,
    ProviderProcessError,
)
from agent_sandbox.models.sandbox import SandboxConfig, SandboxInfo
from agent_sandbox.providers import Provider, ProviderArtifact, ProviderClient, ProviderInfra
from agent_sandbox.providers.client import EppImplementation, ProviderLock, _select_epp
from agent_sandbox.providers.runtime_assets import unpack
from agent_sandbox.transport.config import TransportConfig

if TYPE_CHECKING:
    from pathlib import Path


class LocalNative(Provider):
    id = "local-native"
    version = "1.0.0"
    operations = frozenset({"sandbox.create", "sandbox.get", "sandbox.delete"})
    features = frozenset({"sandbox.lifecycle"})

    def __init__(self, destination: str) -> None:
        self.destination = destination
        self.calls: list[str] = []

    async def build_infra(self, config):
        self.calls.append(config.provider_options["account"])
        return ProviderInfra(
            config,
            None,
            None,
            SimpleNamespace(
                create=self.create,
                get_info=self.get_info,
                kill=self.kill,
            ),
        )

    async def create(self, config, request_timeout=None):
        return SandboxInfo(sandboxID="shared-id")

    async def get_info(self, sandbox_id):
        return SandboxInfo(sandboxID=sandbox_id)

    async def kill(self, sandbox_id):
        self.calls.append(sandbox_id)

    def resolve_session_url(self, info, config):
        return f"https://{self.destination}.example/{info.sandbox_id}"


async def test_same_id_native_targets_are_independent(monkeypatch):
    def no_discovery(*args, **kwargs):
        pytest.fail("Prepared handles must not consult legacy discovery.")

    monkeypatch.setattr(sandbox_module, "get_provider", no_discovery)
    monkeypatch.setattr(sandbox_module, "load_config", no_discovery)
    lock = ProviderLock(provider="local-native", version="1.0.0")
    first = LocalNative("first")
    second = LocalNative("second")
    async with (
        await ProviderClient.prepare(
            lock,
            TransportConfig(provider=first.id, provider_options={"account": "a"}),
            native=first,
            download=True,
        ) as a,
        await ProviderClient.prepare(
            lock,
            TransportConfig(provider=second.id, provider_options={"account": "b"}),
            native=second,
        ) as b,
    ):
        left = await a.create()
        right = await b.create()
        try:
            assert left.id == right.id == "shared-id"
            assert left.url == "https://first.example/shared-id"
            assert right.url == "https://second.example/shared-id"
            assert left.operations == first.operations
            assert (await right.refresh_info()).envd_url == right.url
            with pytest.raises(ProviderMismatchError):
                await a.connect("foreign:shared-id")
            with pytest.raises(ProviderFeatureNotSupportedError):
                await a.create(SandboxConfig(volume_mounts={"/x": "data"}))
            assert first.calls == ["a"]
            assert second.calls == ["b"]
        finally:
            await left.kill()
            await right.kill()
    with pytest.raises(RuntimeError, match="closed"):
        await left.refresh_info()
    assert first.calls == ["a", "shared-id"]
    assert second.calls == ["b", "shared-id"]


def _asset(tmp_path: Path) -> tuple[ProviderArtifact, Path]:
    cached = io.BytesIO()
    with tarfile.open(fileobj=cached, mode="w:gz") as archive:
        data = b"test provider"
        info = tarfile.TarInfo("provider/entry")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    payload = cached.getvalue()
    asset = ProviderArtifact(
        url="https://packages.example/provider.tar.gz",
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        root="provider",
    )
    cache = tmp_path / "cache"
    cache.mkdir(mode=0o700)
    (cache / asset.sha256).write_bytes(payload)
    return asset, cache


def test_offline_cache_is_rehashed_before_extraction(tmp_path):
    asset, cache = _asset(tmp_path)
    destination = tmp_path / "entry"
    unpack(asset, cache, destination, download=False, deadline=time.monotonic() + 5)
    assert (destination / "entry").read_bytes() == b"test provider"

    blob = cache / asset.sha256
    blob.write_bytes(bytes(asset.size))
    with pytest.raises(ProviderProcessError, match="digest"):
        unpack(asset, cache, tmp_path / "corrupt", download=False, deadline=time.monotonic() + 5)
    assert not (tmp_path / "corrupt").exists()


async def test_required_target_stops_before_opening_cache(monkeypatch, tmp_path):
    asset, cache = _asset(tmp_path)
    entry = EppImplementation(
        id="standalone",
        language="node",
        platform="linux-x86_64-glibc",
        priority=0,
        features=("sandbox.lifecycle",),
        artifact=asset,
        entrypoint="entry",
        required_options=("base_url",),
    )
    lock = ProviderLock(provider="local-native", version="1.0.0", implementations=(entry,))
    monkeypatch.setattr(
        "agent_sandbox.providers.client._host_platform", lambda: "linux-x86_64-glibc"
    )
    with pytest.raises(ProviderConfigError, match="base_url"):
        await ProviderClient.prepare(
            lock,
            TransportConfig(provider="local-native", provider_options={"base_url": " "}),
            cache_dir=cache,
        )


def test_standalone_selection_uses_language_platform_and_features(monkeypatch, tmp_path):
    asset, _ = _asset(tmp_path)
    monkeypatch.setattr(
        "agent_sandbox.providers.client._host_platform", lambda: "linux-x86_64-glibc"
    )
    common = {
        "platform": "linux-x86_64-glibc",
        "features": ("sandbox.lifecycle",),
        "entrypoint": "entry",
        "artifact": asset,
    }
    local = EppImplementation(id="python-epp", language="python", priority=20, **common)
    alternate = EppImplementation(
        id="node-epp",
        language="node",
        priority=0,
        **{**common, "features": ("sandbox.lifecycle", "pty")},
    )
    assert _select_epp((local, alternate), frozenset({"sandbox.lifecycle"})) is local
    assert _select_epp((local, alternate), frozenset({"pty"})) is alternate
    with pytest.raises(ProviderConfigError, match="No approved"):
        _select_epp((local,), frozenset({"pty"}))
