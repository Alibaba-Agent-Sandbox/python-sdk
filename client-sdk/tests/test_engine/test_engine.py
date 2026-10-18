"""The SDK reaches Alibaba Cloud, SSE and WebSocket only through the engine."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
import websockets

from agent_sandbox.engine.client import Engine
from agent_sandbox.models.errors import ProviderNotFoundError


async def _http_server(handler: Any) -> tuple[asyncio.Server, int]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port


async def _read_http(reader: asyncio.StreamReader) -> tuple[bytes, bytes]:
    head = await reader.readuntil(b"\r\n\r\n")
    length = 0
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
    body = await reader.readexactly(length) if length else b""
    return head, body


@pytest.mark.asyncio
@pytest.mark.parametrize("mounts", [None, {}, {"/mnt/data": "existing-volume"}])
async def test_builtin_create_goes_through_the_engine(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, mounts: dict[str, str] | None
) -> None:
    monkeypatch.setenv("ABX_ENGINE_SOCKET", str(tmp_path / "engine.sock"))
    seen: dict[str, Any] = {}

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head, body = await _read_http(reader)
        assert head.startswith(b"POST /sandboxes")
        payload = json.loads(body)
        seen["template"] = payload["templateID"]
        seen["payload"] = payload
        raw = json.dumps(
            {"sandboxID": "sbx-engine", "templateID": payload["templateID"], "state": "running"}
        ).encode()
        writer.write(
            b"HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: "
            + str(len(raw)).encode()
            + b"\r\n\r\n"
            + raw
        )
        await writer.drain()
        writer.close()

    server, port = await _http_server(handler)
    try:
        info = await Engine().create(
            "python-base",
            api_key="test-key",
            api_url=f"http://127.0.0.1:{port}",
            volume_mounts=mounts,
        )
    finally:
        if "template" in seen:
            await Engine().op("release", sandbox_id="sbx-engine")
        server.close()
        await server.wait_closed()
    assert seen["template"] == "python-base"
    assert info.sandbox_id == "sbx-engine"
    if mounts:
        assert seen["payload"]["volumeMounts"] == [{"name": "existing-volume", "path": "/mnt/data"}]
    else:
        assert "volumeMounts" not in seen["payload"]


@pytest.mark.asyncio
async def test_engine_reports_uninstalled_catalog_provider(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ABX_ENGINE_SOCKET", str(tmp_path / "engine.sock"))
    with pytest.raises(ProviderNotFoundError, match="not installed"):
        await Engine().create(
            "base",
            provider="opensandbox",
            api_key="test-not-sent",
            api_url="http://127.0.0.1:9",
        )


@pytest.mark.asyncio
async def test_engine_reads_sse(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABX_ENGINE_SOCKET", str(tmp_path / "engine.sock"))

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _read_http(reader)
        raw = b"data: hello-from-engine\n\n"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: "
            + str(len(raw)).encode()
            + b"\r\n\r\n"
            + raw
        )
        await writer.drain()
        writer.close()

    server, port = await _http_server(handler)
    try:
        chunks = [item async for item in Engine().exec_sse(f"http://127.0.0.1:{port}/events")]
    finally:
        server.close()
        await server.wait_closed()
    assert chunks == ["hello-from-engine"]


@pytest.mark.asyncio
async def test_engine_relays_websocket(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABX_ENGINE_SOCKET", str(tmp_path / "engine.sock"))

    async def echo(websocket: Any) -> None:
        async for message in websocket:
            await websocket.send(message)

    server = await websockets.serve(echo, "127.0.0.1", 0)
    sockets = list(server.sockets or [])
    port = sockets[0].getsockname()[1]
    try:
        reply = await Engine().terminal(f"ws://127.0.0.1:{port}", b"ping")
    finally:
        server.close()
        await server.wait_closed()
    assert reply == b"ping"


@pytest.mark.asyncio
async def test_socket_is_owner_only(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    sock = tmp_path / "engine.sock"
    monkeypatch.setenv("ABX_ENGINE_SOCKET", str(sock))
    from agent_sandbox.engine.client import ensure_engine

    ensure_engine()
    mode = sock.stat().st_mode
    assert mode & 0o077 == 0


@pytest.mark.asyncio
async def test_second_ensure_keeps_the_listening_socket(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    sock = tmp_path / "engine.sock"
    monkeypatch.setenv("ABX_ENGINE_SOCKET", str(sock))
    from agent_sandbox.engine.client import ensure_engine

    ensure_engine()
    inode = sock.stat().st_ino
    ensure_engine()
    assert sock.stat().st_ino == inode


@pytest.mark.asyncio
async def test_exec_rejects_non_loopback(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABX_ENGINE_SOCKET", str(tmp_path / "engine.sock"))
    with pytest.raises(Exception, match="loopback"):
        async for _item in Engine().exec_sse("http://169.254.169.254/"):
            pass
