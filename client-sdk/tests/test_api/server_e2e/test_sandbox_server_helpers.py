"""``Sandbox.server`` / ``server_at`` / ``start_server``."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from agent_sandbox.api.server_client import ServerClient
from agent_sandbox.models.errors import ConnectionError_

if TYPE_CHECKING:
    from agent_sandbox.api.sandbox import Sandbox


class TestServerAt:
    async def test_url_and_gateway_headers(self, sandbox: Sandbox) -> None:
        client = sandbox.server_at(9000)
        assert client.base_url == sandbox.network.get_url(9000)
        assert client.pty_url == sandbox.network.get_url(9001).replace("https://", "wss://")
        for key, value in sandbox.network.get_access_headers().items():
            assert client.auth_headers()[key] == value
        await client.aclose()

    async def test_token_is_sent_as_bearer(self, sandbox: Sandbox) -> None:
        client = sandbox.server_at(9100, token="s3cret")
        assert client.base_url == sandbox.network.get_url(9100)
        assert client.auth_headers()["Authorization"] == "Bearer s3cret"
        await client.aclose()

    async def test_server_property_is_cached(self, sandbox: Sandbox) -> None:
        first = sandbox.server
        assert isinstance(first, ServerClient)
        assert sandbox.server is first
        assert first.base_url == sandbox.network.get_url(9000)
        await first.aclose()

    async def test_every_call_to_server_at_is_a_new_client(self, sandbox: Sandbox) -> None:
        a, b = sandbox.server_at(), sandbox.server_at()
        assert a is not b
        await a.aclose()
        await b.aclose()


class _Spy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, cmd: str, **kwargs: Any) -> object:
        self.calls.append((cmd, kwargs))
        return object()


@pytest.fixture
def spy(sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch) -> _Spy:
    spy = _Spy()
    monkeypatch.setattr(sandbox.commands, "run", spy.run)
    return spy


@pytest.fixture
def healthy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    health = AsyncMock(return_value=True)
    monkeypatch.setattr(ServerClient, "health", health)
    return health


class TestStartServer:
    async def test_default_command_and_background(
        self, sandbox: Sandbox, spy: _Spy, healthy: AsyncMock
    ) -> None:
        client = await sandbox.start_server()
        cmd, kwargs = spy.calls[0]
        assert cmd == "agent-sandbox-server serve --port 9000"
        assert kwargs["background"] is True
        assert kwargs["env"] is None
        healthy.assert_awaited()
        await client.aclose()

    async def test_options_are_forwarded(
        self, sandbox: Sandbox, spy: _Spy, healthy: AsyncMock
    ) -> None:
        client = await sandbox.start_server(
            port=9100,
            commands="/home/user/app/my commands.py",
            policy="read-only",
            token="tok",
            env={"A": "1"},
        )
        cmd, kwargs = spy.calls[0]
        assert cmd.startswith("agent-sandbox-server serve --port 9100")
        assert "--commands '/home/user/app/my commands.py'" in cmd
        assert "--preset read-only" in cmd
        assert kwargs["env"] == {"A": "1", "ABX_SERVER_TOKEN": "tok"}
        assert client.base_url == sandbox.network.get_url(9100)
        assert client.auth_headers()["Authorization"] == "Bearer tok"
        await client.aclose()

    async def test_policy_dict_is_passed_through_the_environment(
        self, sandbox: Sandbox, spy: _Spy, healthy: AsyncMock
    ) -> None:
        policy = {"preset": "transfer-only", "endpoints": {"download": {"enabled": True}}}
        client = await sandbox.start_server(policy=policy)
        cmd, kwargs = spy.calls[0]
        assert "--preset" not in cmd
        assert json.loads(kwargs["env"]["ABX_SERVER_POLICY"]) == policy
        await client.aclose()

    async def test_command_override_wins(
        self, sandbox: Sandbox, spy: _Spy, healthy: AsyncMock
    ) -> None:
        client = await sandbox.start_server(command="python -m my.server", commands="x.py")
        assert spy.calls[0][0] == "python -m my.server"
        await client.aclose()

    async def test_wait_false_does_not_probe(
        self, sandbox: Sandbox, spy: _Spy, healthy: AsyncMock
    ) -> None:
        client = await sandbox.start_server(wait=False)
        healthy.assert_not_awaited()
        await client.aclose()

    async def test_polls_until_healthy(
        self, sandbox: Sandbox, spy: _Spy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        health = AsyncMock(side_effect=[False, False, True])
        monkeypatch.setattr(ServerClient, "health", health)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        client = await sandbox.start_server(timeout=60)
        assert health.await_count == 3
        await client.aclose()

    async def test_timeout_raises_connection_error(
        self, sandbox: Sandbox, spy: _Spy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ServerClient, "health", AsyncMock(return_value=False))
        with pytest.raises(ConnectionError_, match="did not become healthy"):
            await sandbox.start_server(timeout=0.2)


class TestAgainstARealServer:
    """``sandbox.server`` talking to a real in-process SandboxServer."""

    async def test_sandbox_server_reaches_a_live_server(
        self,
        sandbox: Sandbox,
        server_factory: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        live, _client = server_factory()
        monkeypatch.setattr(sandbox.network, "get_url", lambda port: live.url)
        monkeypatch.setattr(sandbox.network, "get_access_headers", lambda: {})
        client = sandbox.server_at(9000)
        assert await client.health() is True
        caps = await client.discover()
        assert caps.can("download")
        await client.aclose()
        await _client.aclose()
