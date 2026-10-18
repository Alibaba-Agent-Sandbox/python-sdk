"""Engine PTY frames for providers choosing the E2B terminal wire format."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import websockets

from agent_sandbox.engine import engine_pb2 as pb2

_pb2: Any = pb2

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from agent_sandbox.providers.engine_contract import Session


async def stream_terminal(
    session: Session, first: Any, request_iterator: AsyncIterator[Any]
) -> AsyncIterator[Any]:
    ws_url = session.envd_url.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_url}/terminal"
    headers: dict[str, str] = {}
    if session.token is not None and getattr(session.token, "token", None):
        headers = session.token.get_headers()
    async with websockets.connect(ws_url, additional_headers=headers) as socket:
        if first.cols or first.rows:
            await socket.send(
                json.dumps({"type": "resize", "cols": first.cols, "rows": first.rows})
            )
        yield _pb2.PtyFrame(op="open")
        outgoing: asyncio.Queue[Any] = asyncio.Queue(maxsize=4)

        async def from_socket() -> None:
            try:
                async for message in socket:
                    data = message if isinstance(message, bytes) else message.encode()
                    await outgoing.put(_pb2.PtyFrame(op="data", data=data))
            finally:
                await outgoing.put(None)

        async def from_client() -> None:
            async for frame in request_iterator:
                if frame.op == "resize":
                    text = json.dumps({"type": "resize", "cols": frame.cols, "rows": frame.rows})
                    await socket.send(text)
                elif frame.op == "close":
                    return
                elif frame.data:
                    await socket.send(frame.data)

        reader = asyncio.create_task(from_socket())
        writer = asyncio.create_task(from_client())
        try:
            async for item in _until_client_closes(outgoing, writer):
                yield item
        finally:
            writer.cancel()
            reader.cancel()


async def _until_client_closes(
    outgoing: asyncio.Queue[Any], writer: asyncio.Task[None]
) -> AsyncIterator[Any]:
    """Yield socket frames until the client closes the RPC."""
    while True:
        incoming = asyncio.create_task(outgoing.get())
        done, _pending = await asyncio.wait({incoming, writer}, return_when=asyncio.FIRST_COMPLETED)
        if writer in done and incoming not in done:
            incoming.cancel()
            return
        item = incoming.result()
        if item is None:
            return
        yield item
