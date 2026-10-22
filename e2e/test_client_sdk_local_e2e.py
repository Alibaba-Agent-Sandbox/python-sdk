"""Client SDK over HTTP against a local ``python -m agent_sandbox.server serve``.

The server is a subprocess on 127.0.0.1. ``ServerClient`` (source tree on
``PYTHONPATH``) performs every check. Route handlers are not called in-process.
No API key or server token is set.
"""

from __future__ import annotations

import http.client
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

import pytest

from agent_sandbox.api.server_client import ServerClient
from agent_sandbox.models.server import ShellResult, TransferResult

SERVER_SRC = Path(__file__).resolve().parents[1] / "server-sdk" / "src"
_DROP = {
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "ANTHROPIC_API_KEY",
    "ABX_SANDBOX_API_KEY",
    "ABX_API_KEY",
    "ABX_SANDBOX_API_KEY",
    "DASHSCOPE_API_KEY",
    "ABX_SERVER_TOKEN",
    "ABX_SERVER_POLICY",
    "ABX_SERVER_POLICY_FILE",
    "ABX_SERVER_BASE_DIR",
    "ABX_SERVER_ENABLED_GROUPS",
}
_MARKER = "client-sdk-local-e2e"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_ok(port: int) -> bool:
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
        try:
            conn.request("GET", "/health")
            response = conn.getresponse()
            response.read()
            return response.status == 200
        finally:
            conn.close()
    except OSError:
        return False


class LiveServer:
    """One ``python -m agent_sandbox.server serve`` process."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.base_dir = root / "base"
        self.base_dir.mkdir(parents=True)
        self.port = 0
        self.proc: subprocess.Popen[bytes] | None = None
        self.log_path = root / "server.log"
        self._log = open(self.log_path, "ab")  # noqa: SIM115

    def start(self) -> None:
        last = ""
        for _ in range(4):
            port = _free_port()
            pty = _free_port()
            env = os.environ.copy()
            for key in _DROP:
                env.pop(key, None)
            env["PYTHONPATH"] = str(SERVER_SRC)
            self.proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "agent_sandbox.server",
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--pty-port",
                    str(pty),
                    "--base-dir",
                    str(self.base_dir),
                ],
                cwd=str(self.root),
                env=env,
                stdout=self._log,
                stderr=self._log,
                start_new_session=True,
            )
            if self._wait_ready(port):
                self.port = port
                return
            last = self.log_path.read_text(errors="replace")[-2000:]
            self._kill()
        raise RuntimeError(f"server did not become healthy on 127.0.0.1: {last}")

    def _wait_ready(self, port: int) -> bool:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                return False
            if _http_ok(port):
                return True
            time.sleep(0.05)
        return False

    def stop(self) -> None:
        self._kill()
        self._log.close()

    def _kill(self) -> None:
        proc = self.proc
        self.proc = None
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait(timeout=5)

    def client(self) -> ServerClient:
        return ServerClient(f"http://127.0.0.1:{self.port}", timeout=10)


@pytest.fixture(scope="module")
def live(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveServer]:
    server = LiveServer(tmp_path_factory.mktemp("client-sdk-local-e2e"))
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def client(live: LiveServer) -> Iterator[ServerClient]:
    api = live.client()
    try:
        yield api
    finally:
        api.aclose_sync()


def test_health(client: ServerClient) -> None:
    assert client.health_sync() is True


def test_write_and_read_file_under_base_dir(client: ServerClient, live: LiveServer) -> None:
    target = live.base_dir / "note.txt"
    payload = f"{_MARKER}\n"
    uploaded = client.files.upload_sync(str(target), payload)
    assert isinstance(uploaded, TransferResult)
    assert uploaded.size == len(payload.encode())
    written = Path(uploaded.path).resolve()
    assert written.is_relative_to(live.base_dir.resolve())
    assert written.read_text(encoding="utf-8") == payload
    assert client.files.read_text_sync(str(target)) == payload


def test_shell_stdout(client: ServerClient) -> None:
    result = client.process.shell_sync(f"echo {_MARKER}")
    assert isinstance(result, ShellResult)
    assert result.exit_code == 0
    assert result.stdout == f"{_MARKER}\n"
