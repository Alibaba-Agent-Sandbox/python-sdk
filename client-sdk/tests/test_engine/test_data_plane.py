"""Commands and files go through the engine, including the OpenSandbox adapter."""

from __future__ import annotations

import json
from typing import Any

import pytest
from tests.test_engine.test_engine import _http_server, _read_http

from agent_sandbox.engine.client import Engine
from agent_sandbox.engine.rpcutil import encode_error, reraise
from agent_sandbox.models.errors import EnvdRpcError
from agent_sandbox.models.process import ProcessChunk, ProcessChunkType
from agent_sandbox.transport.http import stream_envelope_for_envd


@pytest.mark.asyncio
async def test_alicloud_exec_uses_the_engine_session(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ABX_ENGINE_SOCKET", str(tmp_path / "engine.sock"))
    monkeypatch.setenv("ABX_ENGINE_INPROCESS", "1")

    async def handler(reader: Any, writer: Any) -> None:
        _head, body = await _read_http(reader)
        payload = json.loads(body)
        raw = json.dumps(
            {
                "sandboxID": "sbx-data",
                "templateID": payload["templateID"],
                "state": "running",
                "envdUrl": "http://127.0.0.1:9",
                "envdAccessToken": "token",
            }
        ).encode()
        writer.write(
            b"HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: "
            + str(len(raw)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + raw
        )
        await writer.drain()
        writer.close()

    server, port = await _http_server(handler)
    try:
        info = await Engine().create("base", api_key="k", api_url=f"http://127.0.0.1:{port}")
    finally:
        server.close()
        await server.wait_closed()

    from agent_sandbox.engine.server import SESSIONS

    class _Reader:
        def __aiter__(self) -> Any:
            return self._gen()

        async def _gen(self) -> Any:
            yield ProcessChunk(type=ProcessChunkType.STDOUT, data="pong\n")
            yield ProcessChunk(type=ProcessChunkType.EXIT, exit_code=0)

    class _Process:
        def __init__(self) -> None:
            self.seen: dict[str, Any] = {}

        async def start(self, url: str, token: Any, **kwargs: Any) -> _Reader:
            self.seen = {"url": url, "cmd": kwargs.get("cmd"), "args": kwargs.get("args")}
            return _Reader()

    process = _Process()
    SESSIONS[info.sandbox_id].process = process
    events = [
        event async for event in Engine().exec_start(info.sandbox_id, cmd="echo", args=["pong"])
    ]
    assert process.seen["cmd"] == "echo"
    assert process.seen["url"] == "http://127.0.0.1:9"
    assert events[-1].has_exit
    assert events[0].data == b"pong\n"


def test_stream_envelope_tracks_envd_generation() -> None:
    assert stream_envelope_for_envd("0.6.1") is True
    assert stream_envelope_for_envd("v0.6.0") is True
    assert stream_envelope_for_envd(None) is True
    assert stream_envelope_for_envd("0.5.2") is False
    assert stream_envelope_for_envd("0.5") is False


def test_empty_exception_is_not_encoded_as_a_blank_message() -> None:
    payload = json.loads(encode_error(StopAsyncIteration()))
    assert payload["type"] == "StopAsyncIteration"
    assert payload["message"] == "StopAsyncIteration"


def test_envd_error_round_trip_keeps_code_and_message() -> None:
    original = EnvdRpcError(
        "envd RPC /process.Process/Start failed: invalid_argument: protocol error: promised 49",
        rpc_path="/process.Process/Start",
        envd_error={
            "error": {
                "code": "invalid_argument",
                "message": "protocol error: promised 49 bytes",
            }
        },
    )
    encoded = encode_error(original)

    class _RpcError(Exception):
        def details(self) -> str:
            return encoded

    try:
        reraise(_RpcError())
    except EnvdRpcError as exc:
        assert "invalid_argument" in exc.message
        assert "promised 49" in exc.message
        assert exc.rpc_path == "/process.Process/Start"
        assert exc.envd_error is not None
        assert exc.envd_error["error"]["code"] == "invalid_argument"
    else:
        raise AssertionError("reraise did not raise")


@pytest.mark.asyncio
async def test_engine_create_selects_stream_envelope_from_envd_version(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ABX_ENGINE_SOCKET", str(tmp_path / "engine.sock"))
    monkeypatch.setenv("ABX_ENGINE_INPROCESS", "1")

    async def handler(reader: Any, writer: Any) -> None:
        _head, body = await _read_http(reader)
        payload = json.loads(body)
        raw = json.dumps(
            {
                "sandboxID": "sbx-gen2",
                "templateID": payload["templateID"],
                "state": "running",
                "envdVersion": "0.6.1",
                "envdAccessToken": "token",
            }
        ).encode()
        writer.write(
            b"HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: "
            + str(len(raw)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + raw
        )
        await writer.drain()
        writer.close()

    server, port = await _http_server(handler)
    try:
        info = await Engine().create("base", api_key="k", api_url=f"http://127.0.0.1:{port}")
    finally:
        server.close()
        await server.wait_closed()

    from agent_sandbox.engine.server import SESSIONS

    assert SESSIONS[info.sandbox_id].http._stream_envelope is True


@pytest.mark.asyncio
async def test_engine_exec_surfaces_envd_error(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ABX_ENGINE_SOCKET", str(tmp_path / "engine.sock"))
    monkeypatch.setenv("ABX_ENGINE_INPROCESS", "1")

    async def handler(reader: Any, writer: Any) -> None:
        _head, body = await _read_http(reader)
        payload = json.loads(body)
        raw = json.dumps(
            {
                "sandboxID": "sbx-err",
                "templateID": payload["templateID"],
                "state": "running",
                "envdVersion": "0.6.1",
                "envdAccessToken": "token",
            }
        ).encode()
        writer.write(
            b"HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: "
            + str(len(raw)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + raw
        )
        await writer.drain()
        writer.close()

    server, port = await _http_server(handler)
    try:
        info = await Engine().create("base", api_key="k", api_url=f"http://127.0.0.1:{port}")
    finally:
        server.close()
        await server.wait_closed()

    from agent_sandbox.engine.server import SESSIONS

    class _Reader:
        def __aiter__(self) -> Any:
            return self

        async def __anext__(self) -> Any:
            raise EnvdRpcError(
                "envd RPC /process.Process/Start failed: "
                "invalid_argument: protocol error: promised 577794671 bytes",
                rpc_path="/process.Process/Start",
                envd_error={
                    "error": {
                        "code": "invalid_argument",
                        "message": "protocol error: promised 577794671 bytes",
                    }
                },
            )

    class _Process:
        async def start(self, url: str, token: Any, **kwargs: Any) -> _Reader:
            del url, token, kwargs
            return _Reader()

    SESSIONS[info.sandbox_id].process = _Process()
    with pytest.raises(EnvdRpcError, match="invalid_argument") as err:
        async for _event in Engine().exec_start(info.sandbox_id, cmd="echo", args=["hi"]):
            pass
    assert "577794671" in err.value.message
