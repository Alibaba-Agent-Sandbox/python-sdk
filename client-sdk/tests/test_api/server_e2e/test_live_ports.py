"""Regression for an OS allocator reusing a released ephemeral port."""

from __future__ import annotations

import socket
import time
from typing import TYPE_CHECKING, Any

import pytest

from . import _live

if TYPE_CHECKING:
    from collections.abc import Callable

    from agent_sandbox.api.server_client import ServerClient


@pytest.mark.parametrize("explicit_pty", [False, True])
def test_reused_candidate_keeps_real_http_and_pty_listeners_separate(
    monkeypatch: pytest.MonkeyPatch,
    server_factory: Callable[..., tuple[_live.LiveServer, ServerClient]],
    explicit_pty: bool,
) -> None:
    with socket.socket() as http, socket.socket() as pty:
        http.bind(("127.0.0.1", 0))
        pty.bind(("127.0.0.1", 0))
        http_port, pty_port = http.getsockname()[1], pty.getsockname()[1]

    # A released candidate may be returned again. Explicit PTY selections must
    # be preserved; the HTTP candidate must move in that case.
    candidates = iter([pty_port, http_port] if explicit_pty else [http_port, http_port, pty_port])
    monkeypatch.setattr(_live, "free_port", lambda: next(candidates))
    options: dict[str, Any] = {"pty_port": pty_port} if explicit_pty else {}
    live, _client = server_factory(**options)
    assert (live.port, live.pty_port) == (http_port, pty_port)

    # PTY startup is asynchronous. Probe only local listener readiness, bounded
    # independently of requests or shell execution.
    for port in (http_port, pty_port):
        deadline = time.monotonic() + 3
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    pytest.fail("the selected local listener did not start")
                time.sleep(0.01)
