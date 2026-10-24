"""Node providers through the local engine, end to end: Python SDK -> engine -> plugin -> backend.

Needs Node and the CLI dev dependencies; skipped locally unless strict mode is enabled.
The backend is the CLI test suite's E2B-shaped mock; no cloud account is involved.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shlex
import shutil
import signal
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from agent_sandbox import ProviderSandbox as Sandbox
from agent_sandbox.models.errors import ProviderFeatureNotSupportedError, SandboxNotFoundError
from agent_sandbox.providers import doctor, engine_client, installer, registry
from tests.iso import iso  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO = Path(__file__).resolve().parents[4]
CLI = Path(os.environ.get("ABX_TEST_CLI_DIR", str(REPO / "agent-sandbox")))
PROVIDERS = Path(os.environ.get("ABX_TEST_PROVIDERS_DIR", str(REPO / "awesome-providers")))
TSX = CLI / "node_modules" / ".bin" / "tsx"
ABX = CLI / "dist" / "bin" / "abx.js"
_MISSING = (
    shutil.which("node") is None
    or not TSX.exists()
    or not ABX.is_file()
    or not (CLI / "tests/_support/run_e2b_mock.ts").is_file()
    or not (PROVIDERS / "cubesandbox/abx-provider.toml").is_file()
)
if _MISSING and os.environ.get("ABX_TEST_ENGINE_REQUIRED") == "1":
    raise pytest.UsageError(
        "Cross-language test prerequisites missing: Node, CLI npm ci/build, or provider sources. "
        "Set ABX_TEST_CLI_DIR and ABX_TEST_PROVIDERS_DIR."
    )
pytestmark = pytest.mark.skipif(
    _MISSING,
    reason="needs Node, CLI dependencies and provider sources (ABX_TEST_*_DIR)",
)


@pytest.fixture
def mock_backend() -> Iterator[int]:
    proc = subprocess.Popen(
        [str(TSX), "tests/_support/run_e2b_mock.ts"],
        cwd=CLI,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    line = proc.stdout.readline()
    try:
        yield int(json.loads(line)["port"])
    finally:
        assert proc.stdin is not None
        proc.stdin.close()
        proc.wait(timeout=10)


@pytest.fixture
def engine_env(iso: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:  # noqa: F811
    home = iso.home.parent
    # The fixtures only use loopback; inherited corporate proxies must not intercept them.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ABX_BIN", shlex.join([shutil.which("node") or "node", str(ABX)]))
    # This verifies interoperability, not cold-start latency on the CI filesystem.
    monkeypatch.setattr(engine_client, "_START_TIMEOUT", 120.0)
    yield home
    record = engine_client.read_record()
    if record is not None:
        with contextlib.suppress(OSError):
            os.kill(record.pid, signal.SIGTERM)


def _cube(mock_port: int) -> dict[str, Any]:
    installer.install(str(PROVIDERS / "cubesandbox"), yes=True)
    registry.reset_registry()
    return {
        "base_url": f"http://127.0.0.1:{mock_port}",
        "proxy": f"127.0.0.1:{mock_port}",
    }


@pytest.mark.asyncio
async def test_cube_through_the_engine(engine_env: Path, mock_backend: int) -> None:
    await asyncio.wait_for(_cube_scenario(mock_backend), timeout=90)


async def _cube_scenario(mock_backend: int) -> None:
    options = _cube(mock_backend)
    async with await Sandbox.create(provider="cubesandbox", provider_options=options) as sandbox:
        assert sandbox.url.startswith("engine://") or sandbox.id
        result = await sandbox.commands.run("echo hi")
        assert result.exit_code == 0
        assert "hi" in result.stdout

        await sandbox.files.write("/tmp/a.txt", "hello")
        assert await sandbox.files.read("/tmp/a.txt") == "file-bytes"

        # Cube exposes default-context execution, not the default stateless mode.
        with pytest.raises(ProviderFeatureNotSupportedError, match="code.execute"):
            await sandbox.run_code("print(1)", language="python")

        listed = await Sandbox.list(provider="cubesandbox", provider_options=options)
        assert any(item.sandbox_id == sandbox.id for item in listed)

        with pytest.raises(ProviderFeatureNotSupportedError):
            await sandbox.get_terminal(cols=80, rows=24)

        await sandbox.kill()
    with pytest.raises(SandboxNotFoundError):
        await Sandbox.connect(sandbox.id, provider="cubesandbox", provider_options=options)


@pytest.mark.asyncio
async def test_reconnects_after_the_engine_restarts(engine_env: Path, mock_backend: int) -> None:
    await asyncio.wait_for(_restart_scenario(mock_backend), timeout=90)


async def _restart_scenario(mock_backend: int) -> None:
    options = _cube(mock_backend)
    sandbox = await Sandbox.create(provider="cubesandbox", provider_options=options)
    first = engine_client.read_record()
    assert first is not None
    os.kill(first.pid, signal.SIGTERM)
    try:
        for _ in range(100):
            if not await engine_client._healthy(first):
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("the first engine did not stop")
        # Recover this connection with a safe read before submitting another mutation.
        assert await sandbox.is_running()
        result = await sandbox.commands.run("echo again")
        assert result.exit_code == 0
        second = engine_client.read_record()
        assert second is not None and second.pid != first.pid
    finally:
        await sandbox.close()


@pytest.mark.parametrize("valid", [True, False])
def test_doctor_initializes_actual_node_plugin(
    engine_env: Path, tmp_path: Path, valid: bool
) -> None:
    source = tmp_path / "doctor-plugin"
    source.mkdir()
    (source / "abx-provider.toml").write_text(
        """manifest_version = 1
operation_contract_version = 1
[operations]
cli = []
python = []
[workflow]
inputs = ["managed"]
startups = ["none"]
[provider]
id = "initialize-fixture"
name = "Initialize fixture"
version = "1.0.0"
[compat]
protocol = "node/1"
requires = { sdk = ">=0.3" }
[runtime]
kind = "node"
entry = "provider.mjs"
[features]
supported = []
"""
    )
    marker = tmp_path / "closed.txt"
    module = (
        "import fs from 'node:fs'; export default () => ({buildInfra: async () => ({"
        "operation_contract_version: 1, operations: {cli: [], python: []},"
        "sandbox_protocol: {create: () => {throw Error('must not create');},"
        "list: () => {throw Error('must not list');}},"
        f"close: async () => fs.writeFileSync({json.dumps(str(marker))}, 'closed')"
        "})});"
    )
    (source / "provider.mjs").write_text(module if valid else "invalid JavaScript !")
    installer.install(str(source), yes=True)
    report = doctor.doctor("initialize-fixture")
    assert report["ok"] is valid, report
    assert report["checks"][-1]["name"] == "handshake"
    if valid:
        assert marker.read_text() == "closed"
    else:
        assert not marker.exists()
