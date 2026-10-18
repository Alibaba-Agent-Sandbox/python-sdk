"""An engine restart must not repeat work whose outcome is unknown."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
import pytest

from agent_sandbox.models.errors import ProviderProtocolError
from agent_sandbox.providers import engine_client
from agent_sandbox.providers.engine_client import EngineClient, EngineRecord

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[EngineClient]:
    record = EngineRecord(pid=1, host="127.0.0.1", port=12345, token="placeholder")

    async def discover() -> EngineRecord:
        return record

    monkeypatch.setattr(engine_client, "discover", discover)
    instance = EngineClient({"provider": "test"})
    await instance._http.aclose()
    instance._http = httpx.AsyncClient(trust_env=False)
    yield instance
    await instance.close()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "failure", [httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError]
)
@pytest.mark.parametrize("streaming", [False, True])
async def test_mutations_are_not_replayed(
    client: EngineClient, method: str, failure: type[httpx.TransportError], streaming: bool
) -> None:
    attempts = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise failure("response lost", request=request)

    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with pytest.raises(ProviderProtocolError, match="outcome is unknown"):
        if streaming:
            async for _ in client.stream(method, "/v1/sandboxes", json_body={}):
                pytest.fail("No event was received")
        else:
            await client.request(method, "/v1/sandboxes", json_body={})
    assert attempts == 1


@pytest.mark.parametrize("method", ["GET", "HEAD", "get"])
@pytest.mark.parametrize("streaming", [False, True])
async def test_safe_reads_recover_once(client: EngineClient, method: str, streaming: bool) -> None:
    attempts = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.RemoteProtocolError("engine stopped", request=request)
        return httpx.Response(200, text='data: {"ok": true}\n\n')

    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    if streaming:
        assert [item async for item in client.stream(method, "/events")] == [{"ok": True}]
    else:
        assert (await client.request(method, "/v1/sandboxes")).status_code == 200
    assert attempts == 2


@pytest.mark.parametrize("streaming", [False, True])
async def test_auth_rejection_can_refresh_before_mutation(
    client: EngineClient, streaming: bool
) -> None:
    attempts = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(401)
        return httpx.Response(200, text='data: {"ok": true}\n\n')

    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    if streaming:
        assert [item async for item in client.stream("POST", "/execute")] == [{"ok": True}]
    else:
        assert (await client.request("POST", "/v1/sandboxes")).status_code == 200
    assert attempts == 2


async def test_read_stream_never_replays_after_output(client: EngineClient) -> None:
    attempts = 0

    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b'data: {"first": true}\n\n'
            raise httpx.ReadError("stream lost")

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, stream=BrokenStream())

    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    events = client.stream("GET", "/events")
    assert await anext(events) == {"first": True}
    with pytest.raises(ProviderProtocolError):
        await anext(events)
    assert attempts == 1


@pytest.mark.parametrize("streaming", [False, True])
async def test_real_socket_lost_response_creates_only_once(
    client: EngineClient, tmp_path: Path, streaming: bool
) -> None:
    committed: list[bytes] = []

    async def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            size = next(
                int(line.split(b":", 1)[1])
                for line in headers.split(b"\r\n")
                if line.lower().startswith(b"content-length:")
            )
            committed.append(await reader.readexactly(size))
            # The operation committed, but the peer never receives its result.
        finally:
            writer.close()
            await writer.wait_closed()

    # A Unix socket exercises real HTTP framing without ambient HTTP proxies.
    path = str(tmp_path / "engine.sock")
    server = await asyncio.start_unix_server(accept, path)
    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds=path))
    async with server:
        with pytest.raises(ProviderProtocolError, match="outcome is unknown"):
            if streaming:
                async for _ in client.stream("POST", "/v1/sandboxes", json_body={"x": 1}):
                    pytest.fail("No response was sent")
            else:
                await client.request("POST", "/v1/sandboxes", json_body={"x": 1})
    assert committed == [b'{"x":1}']
