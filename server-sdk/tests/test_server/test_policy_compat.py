"""Backward compatibility: an unconfigured server behaves as before."""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

import pytest

from easy_sandbox.server.app import SandboxRequestHandler, SandboxServer
from easy_sandbox.server.registry import CommandRegistry
from easy_sandbox.server.router import default_table

from ._live import Live, free_port

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def bare_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[int, ThreadingHTTPServer]]:
    """Wire the handler the way pre-policy tests did (no ``policy_engine`` attribute)."""
    monkeypatch.delenv("EBX_SERVER_POLICY", raising=False)
    monkeypatch.delenv("EBX_SERVER_POLICY_FILE", raising=False)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SandboxRequestHandler)
    httpd.auth_token = "tok"  # type: ignore[attr-defined]
    httpd.registry = CommandRegistry()  # type: ignore[attr-defined]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1], httpd
    httpd.shutdown()
    httpd.server_close()


def test_bare_handler_wiring_still_works(bare_server: Any) -> None:
    port, _ = bare_server
    live = Live.__new__(Live)
    live.port = port
    assert live.request("GET", "/health")[0] == 200
    assert live.request("GET", "/capabilities")[0] == 401
    status, body, _ = live.request("GET", "/capabilities", headers={"X-Access-Token": "tok"})
    assert status == 200 and "groups" in body


def test_unconfigured_server_has_no_engine(live_server: Any) -> None:
    live: Live = live_server()
    assert getattr(live.server._httpd, "policy_engine", None) is None


def test_legacy_token_env_still_gates_everything(
    live_server: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EBX_SERVER_TOKEN", "legacy-secret")
    live: Live = live_server()
    assert live.get("/health")[0] == 200
    assert live.get("/system/info")[0] == 401
    assert live.get("/system/info", headers={"X-Access-Token": "legacy-secret"})[0] == 200


def test_default_table_is_not_mutated_by_policy_servers(live_server: Any) -> None:
    before = default_table().is_group_enabled
    live_server(policy={"groups": {"dev_tools": True}})
    from easy_sandbox.server.router import CapabilityGroup

    assert before(CapabilityGroup.DEV_TOOLS) is False
    assert default_table().is_group_enabled(CapabilityGroup.DEV_TOOLS) is False


def test_policy_server_is_constructible_directly() -> None:
    server = SandboxServer(host="127.0.0.1", pty_port=free_port(), policy={"preset": "locked"})
    assert server is not None
