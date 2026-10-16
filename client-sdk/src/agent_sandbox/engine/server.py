"""gRPC server for the local provider engine."""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

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


@dataclass
class Session:
    """Backend connections for one sandbox. Tokens stay in this process."""

    sandbox_id: str
    provider: str
    envd_url: str
    token: Any
    http: Any
    process: Any
    files: Any
    sandbox_protocol: Any


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
            provider = (getattr(request, "provider", "") or "").strip()
            if getattr(request, "volume_mounts", {}) and provider not in {"", "alicloud-express"}:
                raise ProviderFeatureNotSupportedError(provider, "volume_mounts")
            if provider not in {"", "alicloud-express"}:
                from agent_sandbox.models.errors import ProviderNotFoundError

                raise ProviderNotFoundError(
                    "The local engine only creates alicloud-express sandboxes.",
                    suggestion=(
                        "Catalog providers run in the Python SDK. Install with "
                        "'python -m agent_sandbox.providers install registry:<id> --yes'."
                    ),
                )
            state, session = await _alicloud_create(request)
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
        async for frame in _ali_pty(session, first, request_iterator):
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


async def _alicloud_create(request: Any) -> tuple[Any, Session]:
    from agent_sandbox.api.sandbox import SandboxConfig, _build_infra
    from agent_sandbox.protocol.filesystem import FilesystemProtocol
    from agent_sandbox.protocol.process import ProcessProtocol
    from agent_sandbox.transport.auth import EnvdTokenManager
    from agent_sandbox.transport.http import stream_envelope_for_envd

    sandbox_config = SandboxConfig(
        template=request.template or "base",
        timeout=request.timeout or 300,
        metadata=dict(request.metadata),
        env_vars=dict(request.envs),
        cpu=request.cpu or None,
        memory=request.memory or None,
        disk=request.disk or None,
        gpu=request.gpu or None,
        volume_mounts=dict(getattr(request, "volume_mounts", {})),
    )
    _config, _auth, http_client, protocol = _build_infra(
        api_key=_opt(request.api_key),
        api_url=_opt(request.api_url),
        access_key_id=_opt(request.access_key_id),
        access_key_secret=_opt(request.access_key_secret),
        region=_opt(request.region),
    )
    try:
        info = await protocol.create(
            sandbox_config,
            request_timeout=request.request_timeout or None,
        )
    except Exception:
        await _close(http_client)
        raise
    if not info.envd_url and info.sandbox_id:
        info.envd_url = _config.build_envd_url(info.sandbox_id)
    http_client._stream_envelope = stream_envelope_for_envd(info.envd_version)
    token = EnvdTokenManager(info.envd_access_token, sandbox_id=info.sandbox_id)
    session = Session(
        sandbox_id=info.sandbox_id,
        provider="alicloud-express",
        envd_url=info.envd_url or "",
        token=token,
        http=http_client,
        process=ProcessProtocol(http_client),
        files=FilesystemProtocol(http_client),
        sandbox_protocol=protocol,
    )
    return _state(info), session


async def _kill(request: Any) -> None:
    session = SESSIONS.get(request.sandbox_id)
    if session is not None and session.sandbox_protocol is not None:
        await session.sandbox_protocol.kill(request.sandbox_id)
    else:
        from agent_sandbox.api.sandbox import _build_infra

        _config, _auth, http_client, protocol = _build_infra(
            api_key=_opt(request.api_key),
            api_url=_opt(request.api_url),
            access_key_id=_opt(request.access_key_id),
            access_key_secret=_opt(request.access_key_secret),
            region=_opt(request.region),
        )
        try:
            await protocol.kill(request.sandbox_id)
        finally:
            await _close(http_client)
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
    raise ProviderFeatureNotSupportedError("alicloud-express", op or "files.rw")


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
    raise ProviderFeatureNotSupportedError("alicloud-express", op or "sandbox.lifecycle")


async def _ali_pty(
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


def _grpc_status() -> Any:
    return grpc.StatusCode.FAILED_PRECONDITION
