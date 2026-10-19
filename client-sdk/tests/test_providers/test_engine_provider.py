"""Node providers through the local engine, end to end: Python SDK -> engine -> plugin -> backend.

Needs Node and the CLI's dev dependencies (``cli/node_modules``); skipped otherwise. The backend is
the CLI test suite's E2B-shaped mock, so no network or account is involved.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from agent_sandbox import ProviderSandbox as Sandbox
from agent_sandbox.models.errors import SandboxNotFoundError
from agent_sandbox.providers import engine_client, installer, registry
from tests.iso import iso  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO = Path(__file__).resolve().parents[4]
CLI = REPO / "cli"
TSX = CLI / "node_modules" / ".bin" / "tsx"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not TSX.exists(),
    reason="needs node and cli/node_modules",
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
    yield int(json.loads(line)["port"])
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


def _cube(mock_port: int) -> dict[str, Any]:
    installer.install(str(REPO / "awesome-providers" / "cubesandbox"), yes=True)
    registry.reset_registry()
    return {
        "base_url": f"http://127.0.0.1:{mock_port}",
        "proxy": f"127.0.0.1:{mock_port}",
    }


@pytest.mark.asyncio
async def test_cube_through_the_engine(engine_env: Path, mock_backend: int) -> None:
    options = _cube(mock_backend)
    async with await Sandbox.create(provider="cubesandbox", provider_options=options) as sandbox:
        assert sandbox.url.startswith("engine://") or sandbox.id
        result = await sandbox.commands.run("echo hi")
        assert result.exit_code == 0
        assert "hi" in result.stdout

        await sandbox.files.write("/tmp/a.txt", "hello")
        assert await sandbox.files.read("/tmp/a.txt") == "file-bytes"

        run = await sandbox.run_code("print(1)", language="python")
        assert run is not None

        listed = await Sandbox.list(provider="cubesandbox", provider_options=options)
        assert any(item.sandbox_id == sandbox.id for item in listed)

        async with await sandbox.get_terminal(cols=80, rows=24) as terminal:
            await terminal.send("ping\n")
            seen = ""
            while "ping" not in seen:
                seen += str(await terminal.receive(timeout=5))

        await sandbox.kill()
    with pytest.raises(SandboxNotFoundError):
        await Sandbox.connect(sandbox.id, provider="cubesandbox", provider_options=options)


@pytest.mark.asyncio
async def test_reconnects_after_the_engine_restarts(engine_env: Path, mock_backend: int) -> None:
    options = _cube(mock_backend)
    sandbox = await Sandbox.create(provider="cubesandbox", provider_options=options)
    first = engine_client.read_record()
    assert first is not None
    os.kill(first.pid, signal.SIGTERM)
    result = await sandbox.commands.run("echo again")
    assert result.exit_code == 0
    second = engine_client.read_record()
    assert second is not None and second.pid != first.pid
    await sandbox.close()
