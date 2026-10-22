"""Backward compatibility: an unconfigured server behaves as before."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_sandbox.server.app import SandboxServer
from agent_sandbox.server.router import default_table

from ._live import Live, free_port

if TYPE_CHECKING:
    import pytest


def test_unconfigured_server_still_has_the_one_engine(live_server: Any) -> None:
    live: Live = live_server()
    engine = live.server.policy_engine
    assert engine is live.server._httpd.policy_engine  # type: ignore[union-attr]
    assert engine.policy.configured is False
    status, body = live.get("/capabilities")
    assert status == 200 and body["policy"]["configured"] is False


def test_unconfigured_server_serves_without_a_token(live_server: Any) -> None:
    live: Live = live_server()
    assert live.get("/health")[0] == 200
    assert live.get("/system/info")[0] == 200


def test_legacy_token_env_still_gates_everything(
    live_server: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ABX_SERVER_TOKEN", "legacy-secret")
    live: Live = live_server()
    assert live.get("/health")[0] == 200
    assert live.get("/system/info")[0] == 401
    assert live.get("/system/info", headers={"X-Access-Token": "legacy-secret"})[0] == 200


def test_default_table_is_not_mutated_by_policy_servers(live_server: Any) -> None:
    before = default_table().group_overrides
    live = live_server(policy={"groups": {"dev_tools": True}})
    assert default_table().group_overrides == before
    assert live.get("/git/status?path=/nonexistent")[0] != 404


def test_policy_server_is_constructible_directly() -> None:
    server = SandboxServer(host="127.0.0.1", pty_port=free_port(), policy={"preset": "locked"})
    assert server is not None


def test_retired_transfer_routes_are_absent(live_server):
    live = live_server()
    assert live.post("/upload", {"path": "/tmp/unused", "content_base64": ""})[0] == 404
    assert live.get("/download?path=/tmp/unused")[0] == 404
