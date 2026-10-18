"""gRPC server for the local provider engine."""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import json
import os
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from agent_sandbox.providers.engine_contract import Session

import grpc
import httpx
import websockets

from agent_sandbox.engine import engine_pb2 as pb2
from agent_sandbox.engine import engine_pb2_grpc as pb2_grpc
from agent_sandbox.engine.rpcutil import abort_exc
from agent_sandbox.models.errors import ProviderFeatureNotSupportedError, SandboxNotFoundError

_pb2: Any = pb2
_grpc: Any = pb2_grpc

PROTOCOL = "abx.engine.v1"
_CHUNK = 65536


def _opt(value: str) -> str | None:
    return value or None


async def _close(http_client: Any) -> None:
    close = getattr(http_client, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def loopback_url(url: str) -> bool:
    """True only for http(s) or ws(s) aimed at a loopback host. No userinfo."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https", "ws", "wss"} or parsed.username or parsed.password:
        return False
    host = parsed.hostname
    if host is None:
        return False
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(address.is_loopback)


SESSIONS: dict[str, Session] = {}


def _session(sandbox_id: str) -> Session:
    found = SESSIONS.get(sandbox_id)
    if found is None:
        raise SandboxNotFoundError(f"Sandbox '{sandbox_id}' is not held by the engine.")
    return found


def _state(info: Any, *, envd_url: str | None = None, token: str | None = None) -> Any:
    status = info.status.value if hasattr(info.status, "value") else str(info.status)
    return _pb2.SandboxState(
        sandbox_id=info.sandbox_id,
        template=info.template or "",
        status=status,
        envd_url=envd_url if envd_url is not None else (info.envd_url or ""),
        envd_access_token=token if token is not None else (info.envd_access_token or ""),
        envd_version=getattr(info, "envd_version", None) or "",
    )


class ProviderEngine(_grpc.ProviderEngineServicer):
    """Holds backend sockets and answers the SDK's call shapes."""

    async def Health(self, request: Any, context: Any) -> Any:  # noqa: N802
        del request, context
        from agent_sandbox._version import __version__

        return _pb2.HealthStatus(
            protocol=PROTOCOL,
            pid=os.getpid(),
            version=__version__,
            supported_create_options=["volume_mounts"],
        )

    async def Create(self, request: Any, context: Any) -> Any:  # noqa: N802
        try:
            from agent_sandbox.providers.registry import get_provider, resolve_provider_id

            provider = get_provider(resolve_provider_id(getattr(request, "provider", None)))
            if (
                getattr(request, "volume_mounts", {})
                and "volume_mounts" not in provider.create_options
            ):
                raise ProviderFeatureNotSupportedError(provider.id, "volume_mounts")
            info, session = await provider.create_engine_session(request)
            state = _state(info)
            SESSIONS[state.sandbox_id] = session
            return state
        except Exception as exc:
            await abort_exc(context, exc)

    async def Kill(self, request: Any, context: Any) -> Any:  # noqa: N802
        try:
            await _kill(request)
            return _pb2.Empty()
        except Exception as exc:
            await abort_exc(context, exc)

    async def Exec(self, request: Any, context: Any) -> AsyncIterator[Any]:  # noqa: N802
        """Read an SSE stream in this process and forward each data line."""
        if not request.sse_url:
            await context.abort(_grpc_status(), "sse_url is required")
            return
        if not loopback_url(request.sse_url):
            await context.abort(_grpc_status(), "sse_url must be a loopback address")
            return
        async with (
            httpx.AsyncClient(trust_env=False) as client,
            client.stream("GET", request.sse_url) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    yield _pb2.ExecChunk(data=line.split(":", 1)[1].strip())

    async def Terminal(  # noqa: N802
        self, request_iterator: AsyncIterator[Any], context: Any
    ) -> AsyncIterator[Any]:
        """Own the WebSocket; relay bytes on the gRPC stream."""
        first = await anext(request_iterator, None)
        if first is None or not first.websocket_url:
            await context.abort(_grpc_status(), "the first frame must carry websocket_url")
            return
        if not loopback_url(first.websocket_url):
            await context.abort(_grpc_status(), "websocket_url must be a loopback address")
            return
        async with websockets.connect(first.websocket_url) as socket:
            outgoing: asyncio.Queue[Any] = asyncio.Queue(maxsize=4)

            async def from_socket() -> None:
                try:
                    async for message in socket:
                        data = message if isinstance(message, bytes) else message.encode()
                        await outgoing.put(_pb2.TerminalFrame(data=data))
                finally:
                    await outgoing.put(None)

            async def from_client() -> None:
                if first.data:
                    await socket.send(first.data)
                async for frame in request_iterator:
                    await socket.send(frame.data)

            reader = asyncio.create_task(from_socket())
            writer = asyncio.create_task(from_client())
            try:
                while True:
                    item = await outgoing.get()
                    if item is None:
                        break
                    yield item
            finally:
                writer.cancel()
                await reader

    async def ExecStart(self, request: Any, context: Any) -> AsyncIterator[Any]:  # noqa: N802
        try:
            session = _session(request.sandbox_id)
            reader = await session.process.start(
                session.envd_url,
                session.token,
                cmd=request.cmd,
                args=list(request.args),
                env=dict(request.env) or None,
                cwd=request.cwd,
                timeout=request.timeout or 60,
                user=request.user,
            )
            incoming = reader.__aiter__()
            while True:
                chunk = await incoming.__anext__()
                kind = chunk.type.value if hasattr(chunk.type, "value") else str(chunk.type)
                if kind == "exit":
                    # Keep reading the envd stream after this RPC is cancelled.
                    # An aborted Connect stream makes envd kill the process group,
                    # which takes nohup children with it.
                    asyncio.create_task(_drain(incoming))
                yield _pb2.ExecEvent(
                    kind=kind,
                    data=(chunk.data or "").encode(),
                    exit_code=chunk.exit_code or 0,
                    pid=chunk.pid or 0,
                    has_exit=kind == "exit",
                )
                if kind == "exit":
                    return
        except StopAsyncIteration:
            await abort_exc(
                context,
                RuntimeError("envd stream ended before the process exited"),
            )
        except Exception as exc:
            await abort_exc(context, exc)

    async def FileRead(self, request: Any, context: Any) -> AsyncIterator[Any]:  # noqa: N802
        try:
            data = await _read_bytes(request.sandbox_id, request.path)
        except Exception as exc:
            await abort_exc(context, exc)
            return
        if not data:
            yield _pb2.FileChunk(data=b"", eof=True)
            return
        for start in range(0, len(data), _CHUNK):
            piece = data[start : start + _CHUNK]
            yield _pb2.FileChunk(data=piece, eof=start + _CHUNK >= len(data))

    async def FileWrite(  # noqa: N802
        self, request_iterator: AsyncIterator[Any], context: Any
    ) -> Any:
        sandbox_id = ""
        path = ""
        parts: list[bytes] = []
        try:
            async for frame in request_iterator:
                sandbox_id = frame.sandbox_id or sandbox_id
                path = frame.path or path
                parts.append(bytes(frame.data))
            await _write_bytes(sandbox_id, path, b"".join(parts))
        except Exception as exc:
            await abort_exc(context, exc)
        return _pb2.Empty()

    async def FileOp(self, request: Any, context: Any) -> Any:  # noqa: N802
        try:
            entries = await _file_op(request)
            return _pb2.FileOpResult(entries=[_pb2.FileEntry(**row) for row in entries])
        except Exception as exc:
            await abort_exc(context, exc)

    async def WatchDir(self, request: Any, context: Any) -> AsyncIterator[Any]:  # noqa: N802
        try:
            session = _session(request.sandbox_id)
            reader = await session.files.watch_dir(
                session.envd_url, session.token, path=request.path
            )
            async for event in reader:
                kind = event.type.value if hasattr(event.type, "value") else str(event.type)
                yield _pb2.WatchEventMsg(type=kind, path=event.path, old_path=event.old_path or "")
        except Exception as exc:
            await abort_exc(context, exc)

    async def Pty(  # noqa: N802
        self, request_iterator: AsyncIterator[Any], context: Any
    ) -> AsyncIterator[Any]:
        first = await anext(request_iterator, None)
        if first is None or first.op not in {"", "open"}:
            await context.abort(_grpc_status(), "the first frame must be op=open")
            return
        try:
            session = _session(first.sandbox_id)
        except Exception as exc:
            await abort_exc(context, exc)
            return
        if session.terminal is None:
            raise ProviderFeatureNotSupportedError(session.provider, "pty")
        async for frame in session.terminal(session, first, request_iterator):
            yield frame

    async def Op(self, request: Any, context: Any) -> Any:  # noqa: N802
        try:
            payload = json.loads(request.json or "{}")
            result = await _op(request, payload if isinstance(payload, dict) else {})
            return _pb2.OpResult(json=json.dumps(result))
        except Exception as exc:
            await abort_exc(context, exc)


async def _drain(incoming: Any) -> None:
    try:
        while True:
            await incoming.__anext__()
    except Exception:
        return


async def _kill(request: Any) -> None:
    session = SESSIONS.get(request.sandbox_id)
    if session is not None and session.sandbox_protocol is not None:
        await session.sandbox_protocol.kill(request.sandbox_id)
    else:
        from agent_sandbox.providers.registry import get_provider, resolve_provider_id

        provider = get_provider(resolve_provider_id(getattr(request, "provider", None)))
        await provider.kill_engine_resource(request)
    await _drop(request.sandbox_id)


async def _drop(sandbox_id: str) -> None:
    session = SESSIONS.pop(sandbox_id, None)
    if session is None:
        return
    await _close(session.http)


async def _read_bytes(sandbox_id: str, path: str) -> bytes:
    session = _session(sandbox_id)
    return await session.files.read(session.envd_url, session.token, path=path)


async def _write_bytes(sandbox_id: str, path: str, content: bytes) -> None:
    session = _session(sandbox_id)
    await session.files.write(session.envd_url, session.token, path=path, content=content)


async def _file_op(request: Any) -> list[dict[str, Any]]:
    session = _session(request.sandbox_id)
    url, token = session.envd_url, session.token
    files = session.files
    op = request.op
    if op == "stat":
        info = await files.stat(url, token, path=request.path)
        return [_entry(info)]
    if op == "list":
        return [_entry(item) for item in await files.list_dir(url, token, path=request.path)]
    if op == "mkdir":
        await files.make_dir(url, token, path=request.path)
        return []
    if op == "remove":
        await files.remove(url, token, path=request.path)
        return []
    if op == "move":
        await files.move(url, token, source=request.path, destination=request.destination)
        return []
    raise ProviderFeatureNotSupportedError(session.provider, op or "files.rw")


def _entry(info: Any) -> dict[str, Any]:
    kind = info.type.value if hasattr(info.type, "value") else str(info.type)
    return {"name": info.name, "path": info.path, "type": kind, "size": int(info.size or 0)}


async def _op(request: Any, payload: dict[str, Any]) -> dict[str, Any]:
    op = request.op
    if op == "release":
        await _drop(request.sandbox_id)
        return {}
    session = SESSIONS.get(request.sandbox_id)
    if session is None:
        raise SandboxNotFoundError(f"Sandbox '{request.sandbox_id}' is not held by the engine.")
    if op == "process_list":
        rows = await session.process.list_processes(session.envd_url, session.token)
        return {"processes": [row.model_dump() for row in rows]}
    if op == "process_signal":
        await session.process.send_signal(
            session.envd_url,
            session.token,
            pid=payload.get("pid"),
            signal=int(payload.get("signal") or 15),
        )
        return {}
    if op == "process_stdin":
        await session.process.send_input(
            session.envd_url,
            session.token,
            pid=payload.get("pid"),
            data=str(payload.get("data") or ""),
        )
        return {}
    raise ProviderFeatureNotSupportedError(session.provider, op or "sandbox.lifecycle")


def _grpc_status() -> Any:
    return grpc.StatusCode.FAILED_PRECONDITION
