"""Commands and files go through the engine, including the OpenSandbox adapter."""

from __future__ import annotations

import json
from typing import Any

import pytest
from tests.test_engine.test_engine import _http_server, _read_http

from agent_sandbox.engine.client import Engine
from agent_sandbox.models.process import ProcessChunk, ProcessChunkType


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
