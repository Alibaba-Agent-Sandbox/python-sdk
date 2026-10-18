"""A real in-process ``SandboxServer`` on a free port for client end-to-end tests."""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

import pytest

pytest.importorskip("agent_sandbox.server", reason="needs the agent-sandbox-server distribution")

from agent_sandbox.server.app import SandboxServer  # noqa: E402
from agent_sandbox.server.endpoints import CapabilityGroup  # noqa: E402
from agent_sandbox.server.registry import CommandRegistry  # noqa: E402


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def distinct_port(other: int) -> int:
    """A released candidate can be reused; keep the two listeners separate."""
    for _ in range(32):
        candidate = free_port()
        if candidate != other:
            return candidate
    raise RuntimeError("could not select distinct local HTTP and PTY ports")


class LiveServer:
    """Runs ``SandboxServer.serve`` in a daemon thread; ``close()`` stops it."""

    def __init__(self, **kwargs: Any) -> None:
        self.port = free_port()
        if "pty_port" in kwargs:
            self.pty_port: int = kwargs["pty_port"]
            if self.port == self.pty_port:
                self.port = distinct_port(self.pty_port)
        else:
            self.pty_port = distinct_port(self.port)
            kwargs["pty_port"] = self.pty_port
        self.registry: CommandRegistry = kwargs.pop("registry", None) or CommandRegistry()
        self.server = SandboxServer(host="127.0.0.1", registry=self.registry, **kwargs)
        self.thread = threading.Thread(target=self.server.serve, args=(self.port,), daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            # A network intermediary may accept TCP before our listener exists.
            # Wait for actual server/thread startup before treating a socket as ready.
            pty = self.server._pty_thread
            needs_pty = self.server.policy_engine.group_enabled(CapabilityGroup.TERMINAL)
            if self.server._httpd is None or (needs_pty and (pty is None or pty.ident is None)):
                time.sleep(0.01)
                continue
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.02)
        else:
            self.server.shutdown()
            raise RuntimeError("local client-test server did not start within 5 seconds")
        self._closed = False

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def pty_url(self) -> str:
        return f"http://127.0.0.1:{self.pty_port}"

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.server.shutdown()
        if self.thread.is_alive():
            self.thread.join(timeout=5)
