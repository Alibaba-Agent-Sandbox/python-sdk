"""Cleanup failure recovery over the real session store and local HTTP transport."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import uvicorn

from agent_sandbox.agent.mcp import MCPCleanupError
from agent_sandbox.agent.mcp_http import (
    SessionCapacityError,
    SessionClosingError,
    SessionStore,
    create_mcp_app,
)


async def test_failed_delete_retains_session_capacity_and_retry():
    store = SessionStore(max_sessions=1)
    sid, server = await store.create_session()
    server.shutdown = AsyncMock(side_effect=RuntimeError("SYNTHETIC_PRIVATE_VALUE"))
    with pytest.raises(RuntimeError):
        await store.destroy_session(sid)
    with pytest.raises(SessionClosingError):
        store.get_session(sid)
    with pytest.raises(SessionCapacityError):
        await store.create_session()
    server.shutdown.side_effect = None
    assert await store.destroy_session(sid)
    assert store.get_session(sid) is None
    assert await store.create_session()


async def test_expired_cleanup_retries_only_after_idle_ttl_and_continues_others():
    store = SessionStore(session_ttl_seconds=10)
    first, failed = await store.create_session()
    second, succeeded = await store.create_session()
    failed.shutdown = AsyncMock(side_effect=RuntimeError("temporary"))
    succeeded.shutdown = AsyncMock()
    for entry in store._sessions.values():
        entry.last_access = 0
    with patch("agent_sandbox.agent.mcp_http.time.monotonic", return_value=11):
        assert await store.cleanup_expired() == 1
        assert second not in store._sessions
        assert await store.cleanup_expired() == 0
    failed.shutdown.assert_awaited_once()
    failed.shutdown.side_effect = None
    with patch("agent_sandbox.agent.mcp_http.time.monotonic", return_value=21):
        assert await store.cleanup_expired() == 1
    assert first not in store._sessions


async def test_concurrent_delete_and_cancelled_caller_share_cleanup():
    store = SessionStore()
    sid, server = await store.create_session()
    entered, release = asyncio.Event(), asyncio.Event()

    async def shutdown():
        entered.set()
        await release.wait()

    server.shutdown = AsyncMock(side_effect=shutdown)
    first = asyncio.create_task(store.destroy_session(sid))
    await entered.wait()
    second = asyncio.create_task(store.destroy_session(sid))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert not second.done()
    release.set()
    assert await second
    server.shutdown.assert_awaited_once()
    assert sid not in store._sessions


async def test_shutdown_all_continues_after_failure_and_blocks_admission():
    store = SessionStore()
    first, failed = await store.create_session()
    _, succeeded = await store.create_session()
    failed.shutdown = AsyncMock(side_effect=RuntimeError("temporary"))
    succeeded.shutdown = AsyncMock()
    with pytest.raises(MCPCleanupError):
        await store.shutdown_all()
    succeeded.shutdown.assert_awaited_once()
    assert list(store._sessions) == [first]
    with pytest.raises(SessionCapacityError, match="shutting down"):
        await store.create_session()
    failed.shutdown.side_effect = None
    await store.shutdown_all()
    assert not store._sessions


async def test_real_http_delete_failure_then_retry_keeps_same_session(tmp_path):
    app = create_mcp_app(auth_token="placeholder-mcp-token")
    socket_path = str(tmp_path / "mcp.sock")
    server = uvicorn.Server(uvicorn.Config(app, uds=socket_path, log_level="error", lifespan="on"))
    serving = asyncio.create_task(server.serve())
    try:

        async def wait_started():
            while not server.started:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_started(), 10)
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=socket_path),
            base_url="http://localhost",
            headers={"Authorization": "Bearer placeholder-mcp-token"},
        ) as client:
            response = await client.post(
                "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
            )
            assert response.status_code == 200
            sid = response.headers["mcp-session-id"]
            client.headers["Mcp-Session-Id"] = sid
            manager = app.state.session_store.get_session(sid)._manager
            failed, good = AsyncMock(), AsyncMock()
            failed.id, good.id = "retry-owned", "good-owned"
            manager._sandboxes.update({failed.id: failed, good.id: good})
            manager._owned_sandbox_ids.update([failed.id, good.id])
            failed.kill.side_effect = RuntimeError("SYNTHETIC_PRIVATE_VALUE")
            response = await client.delete("/mcp")
            assert response.status_code == 503
            assert (
                "retry DELETE" in response.text and "SYNTHETIC_PRIVATE_VALUE" not in response.text
            )
            assert list(manager._sandboxes) == [failed.id]
            good.kill.assert_awaited_once()
            response = await client.post(
                "/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
            )
            assert response.status_code == 409
            failed.kill.side_effect = None
            assert (await client.delete("/mcp")).status_code == 200
            assert (await client.delete("/mcp")).status_code == 404
            assert not manager._sandboxes
    finally:
        server.should_exit = True
        await asyncio.wait_for(serving, 10)


@pytest.mark.parametrize("method", ["POST", "GET", "DELETE"])
@pytest.mark.parametrize("protocol", ["unknown", "2024-11-05", ""])
async def test_invalid_protocol_is_refused_before_cleanup_or_dispatch(method, protocol):
    app = create_mcp_app(auth_token="placeholder-mcp-token")
    store = app.state.session_store
    sid, server = await store.create_session()
    server.handle_request = AsyncMock()
    server.shutdown = AsyncMock()
    store._sessions[sid].last_access = 0
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        headers = {
            "Authorization": "Bearer placeholder-mcp-token",
            "Mcp-Session-Id": sid,
            "MCP-Protocol-Version": protocol,
        }
        response = await client.request(
            method,
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert response.status_code == 400
        assert sid in store._sessions
        server.shutdown.assert_not_awaited()
        server.handle_request.assert_not_awaited()
        headers["Authorization"] = "Bearer placeholder-wrong-token"
        assert (await client.request(method, "/mcp", headers=headers)).status_code == 401
        headers["Origin"] = "https://denied.example.invalid"
        assert (await client.request(method, "/mcp", headers=headers)).status_code == 403
    await store.shutdown_all()


async def test_matching_protocol_header_and_missing_header_use_existing_http_session():
    app = create_mcp_app(auth_token="placeholder-mcp-token")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost",
        headers={"Authorization": "Bearer placeholder-mcp-token"},
    ) as client:
        response = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        client.headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
        for protocol in (None, "2025-06-18"):
            if protocol:
                client.headers["MCP-Protocol-Version"] = protocol
            assert (
                await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            ).status_code == 200
        assert (await client.get("/mcp")).status_code == 405
        assert (await client.delete("/mcp")).status_code == 200
