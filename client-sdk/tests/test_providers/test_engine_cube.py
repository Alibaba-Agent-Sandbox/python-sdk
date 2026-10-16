"""CubeSandbox through the Python SDK and the local engine.

The backend is the CLI's E2B-shaped mock. This file covers the paths that
``test_engine_provider.py`` does not already lock down: timeout, streaming,
directory listing, port URLs, defaults, and error mapping.
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
from agent_sandbox.models.errors import (
    ProviderConfigError,
    ProviderFeatureNotSupportedError,
    QuotaExceededError,
    SandboxCreationError,
    SandboxNotFoundError,
    TemplateNotFoundError,
)
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


def _start_mock(extra_env: dict[str, str] | None = None) -> subprocess.Popen[str]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.Popen(
        [str(TSX), "tests/_support/run_e2b_mock.ts"],
        cwd=CLI,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )


@pytest.fixture
def mock_backend() -> Iterator[int]:
    proc = _start_mock()
    assert proc.stdout is not None
    line = proc.stdout.readline()
    yield int(json.loads(line)["port"])
    assert proc.stdin is not None
    proc.stdin.close()
    proc.wait(timeout=10)


@pytest.fixture
def mock_without_domain() -> Iterator[int]:
    proc = _start_mock({"ABX_E2B_MOCK_OMIT_DOMAIN": "1"})
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


def _options(port: int, **extra: object) -> dict[str, Any]:
    installer.install(str(REPO / "awesome-providers" / "cubesandbox"), yes=True)
    registry.reset_registry()
    return {"base_url": f"http://127.0.0.1:{port}", "proxy": f"127.0.0.1:{port}", **extra}


@pytest.mark.asyncio
async def test_cube_data_plane(engine_env: Path, mock_backend: int) -> None:
    options = _options(mock_backend, domain="cube.test")
    sandbox = await Sandbox.create(
        provider="cubesandbox", template="py-image", timeout=90, provider_options=options
    )
    try:
        assert sandbox.id == "sbx-1"
        connected = await Sandbox.connect(
            sandbox.id, provider="cubesandbox", provider_options=options
        )
        assert connected.id == sandbox.id
        await connected.close()

        listed = await Sandbox.list(provider="cubesandbox", provider_options=options)
        assert any(item.sandbox_id == sandbox.id for item in listed)

        result = await sandbox.commands.run("echo hi")
        assert result.exit_code == 0
        assert "hi" in result.stdout
        chunks = [chunk async for chunk in sandbox.commands.stream("echo hi")]
        assert any(chunk.type == "stdout" and "hi" in chunk.data for chunk in chunks)
        assert any(chunk.type == "exit" and chunk.exit_code == 0 for chunk in chunks)

        await sandbox.files.write("/tmp/a.txt", "hello")
        assert await sandbox.files.read("/tmp/a.txt") == "file-bytes"
        names = [entry.name for entry in await sandbox.files.list("/tmp")]
        assert names == ["a.txt"]

        watched = await sandbox.files.watch("/tmp")
        event = await anext(watched)
        assert event.path.endswith("a.txt")

        run = await sandbox.run_code("print(42)", language="python", envs={"FOO": "bar"})
        assert "42" in (run.stdout + run.text)
        assert run.exit_code == 0

        await sandbox.set_timeout(120)
        await sandbox.pause()
        url, headers = await sandbox.network.resolve(8080)
        assert url == "http://8080-sbx-1.reported.test"
        assert headers.get("X-Access-Token") == "tok"

        async with await sandbox.get_terminal(cols=80, rows=24) as terminal:
            await terminal.send("ping\n")
            seen = ""
            while "ping" not in seen:
                seen += str(await terminal.receive(timeout=5))
    finally:
        await sandbox.kill()
    with pytest.raises(SandboxNotFoundError):
        await Sandbox.connect(sandbox.id, provider="cubesandbox", provider_options=options)


@pytest.mark.asyncio
async def test_missing_key_and_domain_use_defaults(
    engine_env: Path, mock_without_domain: int
) -> None:
    options = _options(mock_without_domain)
    assert "api_key" not in options
    assert "domain" not in options
    sandbox = await Sandbox.create(
        provider="cubesandbox", template="base", provider_options=options
    )
    try:
        url, _headers = await sandbox.network.resolve(8080)
        assert url == "http://8080-sbx-1.cube.app"
        assert (await sandbox.commands.run("echo hi")).exit_code == 0
    finally:
        await sandbox.kill()


@pytest.mark.asyncio
async def test_error_mapping(engine_env: Path, mock_backend: int) -> None:
    options = _options(mock_backend)
    with pytest.raises(TemplateNotFoundError, match="template not found"):
        await Sandbox.create(
            provider="cubesandbox", template="status-404", provider_options=options
        )
    with pytest.raises(QuotaExceededError, match="quota exceeded"):
        await Sandbox.create(
            provider="cubesandbox", template="status-429", provider_options=options
        )
    with pytest.raises(SandboxCreationError, match="bad create") as bad:
        await Sandbox.create(
            provider="cubesandbox", template="status-400", provider_options=options
        )
    assert bad.value.code == "E2000"
    with pytest.raises(ProviderConfigError, match="Unknown option"):
        await Sandbox.create(
            provider="cubesandbox", template="base", provider_options={**options, "nope": "1"}
        )

    sandbox = await Sandbox.create(
        provider="cubesandbox", template="base", provider_options=options
    )
    try:
        with pytest.raises(ProviderFeatureNotSupportedError, match="process.manage"):
            await sandbox.commands.list()
    finally:
        await sandbox.kill()
    with pytest.raises(SandboxNotFoundError):
        await Sandbox.connect("missing", provider="cubesandbox", provider_options=options)
