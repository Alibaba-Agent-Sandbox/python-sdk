"""alicloud-container through the local engine: Python SDK -> engine -> provider.mjs -> mock.

The backend is the CLI's E2B-shaped mock. No ACS/ACK account and no real API key.
Wire headers are recorded by the mock when ``ABX_E2B_MOCK_SEEN`` is set.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from agent_sandbox import ProviderSandbox as Sandbox
from agent_sandbox.models.errors import (
    EnvdRpcError,
    FileNotFoundError_,
    FileOperationError,
    InvalidAPIKeyError,
    InvalidCredentialsError,
    ProviderConfigError,
    ProviderFeatureNotSupportedError,
    SandboxCreationError,
    SandboxNotFoundError,
    TemplateNotFoundError,
)
from agent_sandbox.models.sandbox import SandboxStatus
from agent_sandbox.providers import engine_client, installer, registry
from tests.iso import iso  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Iterator

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

REPO = Path(__file__).resolve().parents[4]
CLI = REPO / "cli"
PLUGIN = REPO / "awesome-providers" / "alicloud-container"
TSX = CLI / "node_modules" / ".bin" / "tsx"

ADVERTISED = [
    "sandbox.lifecycle",
    "sandbox.timeout",
    "sandbox.pause",
    "exec.run",
    "exec.stream",
    "process.manage",
    "files.rw",
    "ports.url",
]

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not TSX.exists(),
    reason="needs node and cli/node_modules",
)


@pytest.fixture
def mock_backend(tmp_path: Path) -> Iterator[dict[str, Any]]:
    seen = tmp_path / "seen.ndjson"
    env = os.environ.copy()
    env["ABX_E2B_MOCK_SEEN"] = str(seen)
    proc = subprocess.Popen(
        [str(TSX), "tests/_support/run_e2b_mock.ts"],
        cwd=CLI,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.stdout is not None
    line = proc.stdout.readline()
    port = int(json.loads(line)["port"])
    yield {"port": port, "origin": f"http://127.0.0.1:{port}", "seen": seen}
    assert proc.stdin is not None
    proc.stdin.close()
    proc.wait(timeout=10)


@pytest.fixture
def engine_env(iso: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:  # noqa: F811
    home = iso.home.parent
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ABX_BIN", f"{TSX} {CLI / 'src' / 'bin' / 'abx.ts'}")
    yield home
    record = engine_client.read_record()
    if record is not None:
        with contextlib.suppress(OSError):
            os.kill(record.pid, signal.SIGTERM)


def _install() -> None:
    installer.install(str(PLUGIN), yes=True)
    registry.reset_registry()


def _seen(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _native(mock: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "base_url": mock["origin"],
        "domain": "acs.test",
        "api_key": "super-secret-key",
        **extra,
    }


def _private(mock: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "base_url": f"{mock['origin']}/kruise/api",
        "domain": "acs.test",
        "api_key": "super-secret-key",
        "protocol": "private",
        **extra,
    }


@pytest.mark.asyncio
async def test_config_and_advertised_features(
    engine_env: Path, mock_backend: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _install()
    declared = tomllib.loads(PLUGIN.joinpath("abx-provider.toml").read_text(encoding="utf-8"))[
        "features"
    ]["supported"]
    assert sorted(declared) == sorted(ADVERTISED)
    assert "pty" not in declared and "files.watch" not in declared
    assert sorted(registry.get_provider("alicloud-container").features) == sorted(ADVERTISED)

    monkeypatch.setenv("ABX_SANDBOX_API_KEY", "express-secret")
    with pytest.raises(InvalidCredentialsError, match="ABX_ALICLOUD_CONTAINER_API_KEY"):
        await Sandbox.create(
            provider="alicloud-container",
            provider_options={"domain": "acs.test"},
            template="code-interpreter",
        )
    with pytest.raises(ProviderConfigError, match="domain or a base URL"):
        await Sandbox.create(
            provider="alicloud-container",
            provider_options={"api_key": "k"},
            template="code-interpreter",
        )
    with pytest.raises(ProviderConfigError, match="native or private"):
        await Sandbox.create(
            provider="alicloud-container",
            provider_options={"domain": "acs.test", "api_key": "k", "protocol": "public"},
            template="code-interpreter",
        )
    with pytest.raises(ProviderConfigError, match="scheme"):
        await Sandbox.create(
            provider="alicloud-container",
            provider_options={"base_url": "127.0.0.1:9", "api_key": "k"},
            template="code-interpreter",
        )
    with pytest.raises(ProviderConfigError, match="must be a host"):
        await Sandbox.create(
            provider="alicloud-container",
            provider_options={"domain": "https://acs.test/kruise", "api_key": "k"},
            template="code-interpreter",
        )
    assert _seen(mock_backend["seen"]) == []


@pytest.mark.asyncio
async def test_native_lifecycle_and_scheme(engine_env: Path, mock_backend: dict[str, Any]) -> None:
    _install()
    options = _native(mock_backend, domain="https://acs.test")
    sandbox = await Sandbox.create(
        provider="alicloud-container",
        provider_options=options,
        template="code-interpreter",
        timeout=42,
    )
    try:
        assert sandbox.id == "sbx-1"
        url, _headers = await sandbox.network.resolve(8080)
        assert url == "https://8080-sbx-1.acs.test"

        listed = await Sandbox.list(
            provider="alicloud-container",
            provider_options=options,
            status=SandboxStatus.RUNNING,
            limit=2,
            offset=3,
        )
        assert any(item.sandbox_id == sandbox.id for item in listed)
        list_urls = [
            row["url"]
            for row in _seen(mock_backend["seen"])
            if str(row["url"]).startswith("/v2/sandboxes")
        ]
        assert list_urls
        assert "state=running" in list_urls[-1]
        assert "limit=2" in list_urls[-1] and "offset=3" in list_urls[-1]

        await sandbox.set_timeout(120)
        await sandbox.pause()
        await sandbox.resume()
        # The live engine reuses the create session and only refreshes. A new engine has to connect.
        record = engine_client.read_record()
        assert record is not None
        os.kill(record.pid, signal.SIGTERM)
        again = await Sandbox.connect(
            sandbox.id, provider="alicloud-container", provider_options=options
        )
        assert again.id == sandbox.id
        await again.close()
    finally:
        await sandbox.kill()

    calls = _seen(mock_backend["seen"])
    assert any(row["method"] == "DELETE" and row["url"] == "/sandboxes/sbx-1" for row in calls)
    assert any(row["url"] == "/sandboxes/sbx-1/timeout" for row in calls)
    assert any(row["url"] == "/sandboxes/sbx-1/pause" for row in calls)
    assert any(row["url"] == "/v2/sandboxes/sbx-1/connect" for row in calls)
    for row in calls:
        if str(row["url"]).startswith("/sandboxes") or str(row["url"]).startswith("/v2/"):
            assert row["headers"]["x-api-key"] == "super-secret-key"
            assert row["headers"]["authorization"] is None
    with pytest.raises(SandboxNotFoundError):
        await Sandbox.connect(sandbox.id, provider="alicloud-container", provider_options=options)


@pytest.mark.asyncio
async def test_private_data_plane_through_the_engine(
    engine_env: Path, mock_backend: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _install()
    monkeypatch.setenv("ABX_SANDBOX_API_KEY", "express-secret")
    options = _private(mock_backend)
    async with await Sandbox.create(
        provider="alicloud-container", provider_options=options, template="code-interpreter"
    ) as sandbox:
        url, _headers = await sandbox.network.resolve(8080)
        assert url == f"{mock_backend['origin']}/kruise/{sandbox.id}/8080"

        result = await sandbox.commands.run("echo hi")
        assert result.exit_code == 0
        assert "hi" in result.stdout

        streamed = [chunk async for chunk in sandbox.commands.stream("echo hi")]
        assert any("hi" in chunk.data for chunk in streamed)
        assert any(chunk.type == "exit" and chunk.exit_code == 0 for chunk in streamed)

        processes = await sandbox.commands.list()
        assert any(p.pid == 7 and "echo" in p.command for p in processes)
        await sandbox.commands.kill(7)

        await sandbox.files.write("/tmp/a.txt", "hello")
        assert await sandbox.files.read("/tmp/a.txt") == "file-bytes"
        entries = await sandbox.files.list("/tmp")
        assert [entry.name for entry in entries] == ["a.txt"]

        run = await sandbox.run_code(
            "print(42)", mode="default-context", language="python", envs={"A": "b"}
        )
        assert "42" in (run.stdout or "") or "42" in (run.text or "")

        with pytest.raises(ProviderFeatureNotSupportedError):
            async for _event in await sandbox.files.watch("/tmp"):
                break
        with pytest.raises(ProviderFeatureNotSupportedError):
            await sandbox.code.create_context(language="python")

    calls = _seen(mock_backend["seen"])
    start = next(row for row in calls if row["url"] == "/process.Process/Start")
    assert start["headers"]["x-access-token"] == "tok"
    assert start["headers"]["x-api-key"] is None
    assert start["headers"]["e2b-sandbox-port"] == "49983"
    execute = next(row for row in calls if row["url"] == "/execute")
    assert execute["headers"]["e2b-sandbox-port"] == "49999"
    assert execute["headers"]["x-access-token"] == "tok"
    assert execute["headers"]["x-api-key"] is None
    assert any(row["url"] == "/process.Process/SendSignal" for row in calls)
    assert all("express-secret" not in row["values"] for row in calls)


@pytest.mark.asyncio
async def test_error_mapping_through_the_engine(
    engine_env: Path, mock_backend: dict[str, Any]
) -> None:
    _install()
    options = _native(mock_backend)
    with pytest.raises(InvalidAPIKeyError, match="HTTP 401") as unauthorized:
        await Sandbox.create(
            provider="alicloud-container", provider_options=options, template="status-401"
        )
    assert "super-secret-key" not in str(unauthorized.value)
    with pytest.raises(TemplateNotFoundError, match="template not found") as missing_template:
        await Sandbox.create(
            provider="alicloud-container", provider_options=options, template="status-404"
        )
    assert "super-secret-key" not in str(missing_template.value)
    with pytest.raises(SandboxCreationError, match="backend unavailable") as unavailable:
        await Sandbox.create(
            provider="alicloud-container", provider_options=options, template="status-503"
        )
    assert "super-secret-key" not in str(unavailable.value)
    with pytest.raises(SandboxNotFoundError):
        await Sandbox.connect(
            "missing-sbx", provider="alicloud-container", provider_options=options
        )
    with pytest.raises(Exception, match="503") as server_error:
        await Sandbox.connect("status-503", provider="alicloud-container", provider_options=options)
    assert "super-secret-key" not in str(server_error.value)

    sandbox = await Sandbox.create(
        provider="alicloud-container",
        provider_options=_private(mock_backend),
        template="code-interpreter",
    )
    try:
        with pytest.raises(FileNotFoundError_):
            await sandbox.files.read("/status-404")
        with pytest.raises(FileOperationError, match="HTTP 500"):
            await sandbox.files.read("/status-500")
        with pytest.raises(EnvdRpcError, match="HTTP 500"):
            await sandbox.commands.run("status-500")
    finally:
        await sandbox.kill()
