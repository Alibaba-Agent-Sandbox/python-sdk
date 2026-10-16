"""The catalog ``e2b`` node provider through the Python SDK and the local engine.

Python SDK -> engine -> ``awesome-providers/e2b/provider.mjs`` -> the CLI's E2B-shaped mock.
No network account and no real API key. Needs Node and ``cli/node_modules``.
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
    InvalidAPIKeyError,
    InvalidCredentialsError,
    SandboxNotFoundError,
)
from agent_sandbox.models.filesystem import WatchEventType
from agent_sandbox.models.process import ProcessChunkType
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


def _serve(extra: dict[str, str]) -> Iterator[int]:
    env = os.environ.copy()
    env.update(extra)
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
    yield int(json.loads(line)["port"])
    assert proc.stdin is not None
    proc.stdin.close()
    proc.wait(timeout=10)


@pytest.fixture
def mock_backend() -> Iterator[int]:
    yield from _serve({"E2B_MOCK_ENVD_SELF": "1"})


@pytest.fixture
def connect_fallback_backend() -> Iterator[int]:
    yield from _serve({"E2B_MOCK_CONNECT_STATUS": "404"})


@pytest.fixture
def unauthorized_backend() -> Iterator[int]:
    yield from _serve({"E2B_MOCK_UNAUTHORIZED": "1"})


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
    installer.install(str(REPO / "awesome-providers" / "e2b"), yes=True)
    registry.reset_registry()


def _options(port: int, *, key: str = "e2b-key") -> dict[str, Any]:
    return {
        "base_url": f"http://127.0.0.1:{port}",
        "api_key": key,
        "domain": "e2b.test",
    }


@pytest.mark.asyncio
async def test_e2b_lifecycle_and_data_plane(engine_env: Path, mock_backend: int) -> None:
    _install()
    options = _options(mock_backend)
    async with await Sandbox.create(
        provider="e2b", provider_options=options, template="base", timeout=60
    ) as sandbox:
        assert sandbox.id == "sbx-1"
        assert sandbox.info.region == ""
        assert sandbox.info.timeout == 0

        info = await sandbox.refresh_info()
        assert info.sandbox_id == sandbox.id
        assert await sandbox.is_running()

        listed = await Sandbox.list(provider="e2b", provider_options=options)
        assert [item.sandbox_id for item in listed] == [sandbox.id]

        other = await Sandbox.connect(sandbox.id, provider="e2b", provider_options=options)
        assert other.id == sandbox.id
        await other.close()
        with pytest.raises(SandboxNotFoundError):
            await Sandbox.connect("no-such", provider="e2b", provider_options=options)

        await sandbox.set_timeout(120)
        await sandbox.pause()
        await sandbox.resume()

        url, headers = await sandbox.network.resolve(8080)
        assert url == "https://8080-sbx-1.e2b.test"
        assert headers.get("X-Access-Token") == "tok"

        result = await sandbox.commands.run("echo hi")
        assert result.exit_code == 0
        assert "hi" in result.stdout

        chunks = [chunk async for chunk in sandbox.commands.stream("echo hi")]
        stdout = "".join(chunk.data for chunk in chunks if chunk.type == ProcessChunkType.STDOUT)
        assert "hi" in stdout
        assert [chunk.exit_code for chunk in chunks if chunk.type == ProcessChunkType.EXIT] == [0]

        processes = await sandbox.commands.list()
        assert any(p.pid == 7 and "echo" in p.command for p in processes)

        await sandbox.files.write("/tmp/a.txt", "hello")
        assert await sandbox.files.read("/tmp/a.txt") == "file-bytes"
        entries = await sandbox.files.list("/tmp")
        assert [(e.name, e.path) for e in entries] == [("a.txt", "/tmp/a.txt")]

        events = await (await sandbox.files.watch("/tmp")).collect()
        assert [(e.type, e.path) for e in events] == [(WatchEventType.MODIFIED, "/tmp/a.txt")]

        code = await sandbox.run_code("print(42)", language="python")
        assert code.stdout == "42\n"
        assert code.text == "42"
        assert code.exit_code == 0

        await sandbox.kill()
        assert await Sandbox.list(provider="e2b", provider_options=options) == []

    with pytest.raises(SandboxNotFoundError):
        await Sandbox.connect(sandbox.id, provider="e2b", provider_options=options)


@pytest.mark.asyncio
async def test_e2b_connect_falls_back_when_post_connect_404s(
    engine_env: Path, connect_fallback_backend: int
) -> None:
    _install()
    options = _options(connect_fallback_backend)
    created = await Sandbox.create(provider="e2b", provider_options=options, template="base")
    try:
        connected = await Sandbox.connect(created.id, provider="e2b", provider_options=options)
        assert connected.id == created.id
        await connected.close()
    finally:
        await created.kill()


@pytest.mark.asyncio
async def test_e2b_missing_credentials(engine_env: Path) -> None:
    _install()
    with pytest.raises(InvalidCredentialsError, match="ABX_E2B_API_KEY"):
        await Sandbox.create(provider="e2b", provider_options={"base_url": "http://127.0.0.1:9"})


@pytest.mark.asyncio
async def test_e2b_ignores_the_express_key(
    engine_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install()
    monkeypatch.setenv("E2B_API_KEY", "express-key")
    with pytest.raises(InvalidCredentialsError, match="ABX_E2B_API_KEY") as raised:
        await Sandbox.create(provider="e2b", provider_options={"base_url": "http://127.0.0.1:9"})
    assert "express-key" not in str(raised.value)


@pytest.mark.asyncio
async def test_e2b_api_key_from_environment(
    engine_env: Path, mock_backend: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install()
    monkeypatch.setenv("ABX_E2B_API_KEY", "from-env")
    sandbox = await Sandbox.create(
        provider="e2b",
        provider_options={"base_url": f"http://127.0.0.1:{mock_backend}", "domain": "e2b.test"},
        template="base",
    )
    try:
        assert sandbox.id == "sbx-1"
        assert (await sandbox.network.resolve(8080))[0] == "https://8080-sbx-1.e2b.test"
    finally:
        await sandbox.kill()


@pytest.mark.asyncio
async def test_e2b_rejected_api_key(engine_env: Path, unauthorized_backend: int) -> None:
    _install()
    options = _options(unauthorized_backend)
    with pytest.raises(InvalidAPIKeyError) as raised:
        await Sandbox.create(provider="e2b", provider_options=options, template="base")
    assert "e2b-key" not in str(raised.value)
    assert "127.0.0.1" not in str(raised.value)
