"""SDK protocols that forward commands, files and the terminal to the engine."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agent_sandbox.engine.client import Engine
from agent_sandbox.models.filesystem import FileInfo, FileType, WatchEvent, WatchEventType
from agent_sandbox.models.process import ProcessChunk, ProcessChunkType, ProcessInfo
from agent_sandbox.transport.streaming import StreamReader

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def sandbox_id_from(envd_url: str, explicit: str | None) -> str:
    """The engine session id. ``abx-engine://`` URLs carry it; otherwise use *explicit*."""
    if envd_url.startswith("abx-engine://"):
        return envd_url.removeprefix("abx-engine://").split("/", 1)[0]
    if explicit:
        return explicit
    raise RuntimeError("engine data-plane call is missing a sandbox id")


def _chunk(event: Any) -> ProcessChunk:
    kind = str(event.kind or "stdout")
    if kind not in {"stdout", "stderr", "exit"}:
        kind = "stdout"
    return ProcessChunk(
        type=ProcessChunkType(kind),
        data=bytes(event.data).decode("utf-8", "replace"),
        exit_code=int(event.exit_code) if event.has_exit else None,
        pid=int(event.pid) or None,
    )


def _info(row: dict[str, Any]) -> FileInfo:
    kind = FileType.DIRECTORY if row.get("type") in {"directory", "dir"} else FileType.FILE
    return FileInfo(
        name=str(row.get("name") or ""),
        path=str(row.get("path") or ""),
        type=kind,
        size=int(row.get("size") or 0),
    )


class EngineProcessProtocol:
    """``ProcessProtocol`` shape. HTTP stays inside the engine."""

    def __init__(self, sandbox_id: str | None = None) -> None:
        self._sandbox_id = sandbox_id

    def _id(self, envd_url: str) -> str:
        return sandbox_id_from(envd_url, self._sandbox_id)

    async def start(
        self,
        envd_url: str,
        envd_token: Any,
        *,
        cmd: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str = "",
        timeout: int = 60,
        user: str = "",
    ) -> StreamReader[ProcessChunk]:
        del envd_token
        sandbox_id = self._id(envd_url)

        async def frames() -> AsyncIterator[dict[str, Any]]:
            async for event in Engine().exec_start(
                sandbox_id,
                cmd=cmd,
                args=args,
                env=env,
                cwd=cwd,
                user=user,
                timeout=timeout,
            ):
                yield {"event": event}

        return StreamReader(frames(), lambda frame: _chunk(frame["event"]))

    async def list_processes(self, envd_url: str, envd_token: Any) -> list[ProcessInfo]:
        del envd_token
        result = await Engine().op("process_list", sandbox_id=self._id(envd_url))
        return [ProcessInfo.model_validate(row) for row in result.get("processes", [])]

    async def send_input(
        self, envd_url: str, envd_token: Any, *, pid: int | str, data: str
    ) -> None:
        del envd_token
        await Engine().op(
            "process_stdin", sandbox_id=self._id(envd_url), payload={"pid": pid, "data": data}
        )

    async def send_signal(
        self, envd_url: str, envd_token: Any, *, pid: int | str, signal: int = 15
    ) -> None:
        del envd_token
        await Engine().op(
            "process_signal",
            sandbox_id=self._id(envd_url),
            payload={"pid": pid, "signal": signal},
        )

    async def kill(self, envd_url: str, envd_token: Any, *, pid: int | str) -> None:
        await self.send_signal(envd_url, envd_token, pid=pid, signal=9)

    async def send_stdin(
        self, envd_url: str, envd_token: Any, *, pid: int | str, data: str
    ) -> None:
        await self.send_input(envd_url, envd_token, pid=pid, data=data)


class EngineFilesystemProtocol:
    """``FilesystemProtocol`` shape. File bytes are raw gRPC payloads."""

    def __init__(self, sandbox_id: str | None = None) -> None:
        self._sandbox_id = sandbox_id

    def _id(self, envd_url: str) -> str:
        return sandbox_id_from(envd_url, self._sandbox_id)

    async def read(self, envd_url: str, envd_token: Any, *, path: str) -> bytes:
        del envd_token
        return await Engine().file_read(self._id(envd_url), path)

    async def read_text(
        self, envd_url: str, envd_token: Any, *, path: str, encoding: str = "utf-8"
    ) -> str:
        return (await self.read(envd_url, envd_token, path=path)).decode(encoding)

    async def write(
        self, envd_url: str, envd_token: Any, *, path: str, content: str | bytes
    ) -> None:
        del envd_token
        raw = content.encode("utf-8") if isinstance(content, str) else content
        await Engine().file_write(self._id(envd_url), path, raw)

    async def upload_file(
        self,
        envd_url: str,
        envd_token: Any,
        *,
        path: str,
        content: bytes,
        username: str = "user",
    ) -> None:
        del username
        await self.write(envd_url, envd_token, path=path, content=content)

    async def download_file(
        self, envd_url: str, envd_token: Any, *, path: str, username: str = "user"
    ) -> bytes:
        del username
        return await self.read(envd_url, envd_token, path=path)

    async def stat(self, envd_url: str, envd_token: Any, *, path: str) -> FileInfo:
        del envd_token
        rows = await Engine().file_op(self._id(envd_url), "stat", path)
        return _info(rows[0] if rows else {"path": path})

    async def get_info(self, envd_url: str, envd_token: Any, *, path: str) -> FileInfo:
        return await self.stat(envd_url, envd_token, path=path)

    async def list_dir(self, envd_url: str, envd_token: Any, *, path: str = "/") -> list[FileInfo]:
        del envd_token
        rows = await Engine().file_op(self._id(envd_url), "list", path)
        return [_info(row) for row in rows]

    async def make_dir(self, envd_url: str, envd_token: Any, *, path: str) -> None:
        del envd_token
        await Engine().file_op(self._id(envd_url), "mkdir", path)

    async def remove(self, envd_url: str, envd_token: Any, *, path: str) -> None:
        del envd_token
        await Engine().file_op(self._id(envd_url), "remove", path)

    async def move(self, envd_url: str, envd_token: Any, *, source: str, destination: str) -> None:
        del envd_token
        await Engine().file_op(self._id(envd_url), "move", source, destination)

    async def rename(self, envd_url: str, envd_token: Any, *, old_path: str, new_path: str) -> None:
        await self.move(envd_url, envd_token, source=old_path, destination=new_path)

    async def exists(self, envd_url: str, envd_token: Any, *, path: str) -> bool:
        try:
            await self.stat(envd_url, envd_token, path=path)
        except Exception:
            return False
        return True

    async def watch_dir(
        self, envd_url: str, envd_token: Any, *, path: str
    ) -> StreamReader[WatchEvent]:
        del envd_token
        sandbox_id = self._id(envd_url)

        async def frames() -> AsyncIterator[dict[str, Any]]:
            from agent_sandbox.engine import engine_pb2 as pb2
            from agent_sandbox.engine import engine_pb2_grpc as pb2_grpc
            from agent_sandbox.engine.client import _channel
            from agent_sandbox.engine.rpcutil import reraise

            channel = _channel()
            try:
                call = pb2_grpc.ProviderEngineStub(channel).WatchDir(
                    pb2.FilePath(sandbox_id=sandbox_id, path=path)
                )
                async for event in call:
                    yield {
                        "type": event.type,
                        "path": event.path,
                        "old_path": event.old_path or None,
                    }
            except Exception as exc:
                if type(exc).__name__ == "AioRpcError":
                    reraise(exc)
                raise
            finally:
                await channel.close()

        def transform(frame: dict[str, Any]) -> WatchEvent:
            raw = str(frame.get("type") or "modified")
            try:
                kind = WatchEventType(raw)
            except ValueError:
                kind = WatchEventType.MODIFIED
            return WatchEvent(
                type=kind, path=str(frame.get("path") or ""), old_path=frame.get("old_path")
            )

        return StreamReader(frames(), transform)


class EngineTerminal:
    """PTY session whose WebSocket is owned by the engine."""

    def __init__(self, sandbox_id: str, *, cols: int, rows: int) -> None:
        self._sandbox_id = sandbox_id
        self._cols = cols
        self._rows = rows
        self._send: asyncio.Queue[Any] | None = None
        self._recv: asyncio.Queue[Any] | None = None
        self._task: asyncio.Task[None] | None = None
        self._connected = False

    async def connect(self) -> EngineTerminal:
        from agent_sandbox.engine import engine_pb2 as pb2
        from agent_sandbox.engine import engine_pb2_grpc as pb2_grpc
        from agent_sandbox.engine.client import _channel

        self._send = asyncio.Queue(maxsize=4)
        self._recv = asyncio.Queue(maxsize=4)
        channel = _channel()

        async def outgoing() -> AsyncIterator[Any]:
            assert self._send is not None
            yield pb2.PtyFrame(
                sandbox_id=self._sandbox_id, op="open", cols=self._cols, rows=self._rows
            )
            while True:
                frame = await self._send.get()
                if frame is None:
                    break
                yield frame

        async def pump() -> None:
            assert self._recv is not None
            try:
                call = pb2_grpc.ProviderEngineStub(channel).Pty(outgoing())
                async for frame in call:
                    self._connected = True
                    await self._recv.put(frame)
            finally:
                self._connected = False
                await self._recv.put(None)
                await channel.close()

        self._task = asyncio.create_task(pump())
        first = await self._recv.get()
        if first is None:
            raise RuntimeError("terminal stream ended before it opened")
        self._connected = True
        return self

    async def send(self, data: str) -> None:
        await self.send_bytes(data.encode())

    async def send_bytes(self, data: bytes) -> None:
        from agent_sandbox.engine import engine_pb2 as pb2

        assert self._send is not None
        await self._send.put(pb2.PtyFrame(op="data", data=data))

    async def receive(self, timeout: float | None = None) -> str | bytes:
        import asyncio

        assert self._recv is not None
        if timeout is None:
            frame = await self._recv.get()
        else:
            frame = await asyncio.wait_for(self._recv.get(), timeout)
        if frame is None:
            raise RuntimeError("terminal stream closed")
        return bytes(frame.data)

    async def resize(self, cols: int, rows: int) -> None:
        from agent_sandbox.engine import engine_pb2 as pb2

        assert self._send is not None
        await self._send.put(pb2.PtyFrame(op="resize", cols=cols, rows=rows))

    async def output_stream(self) -> AsyncIterator[bytes]:
        assert self._recv is not None
        while True:
            frame = await self._recv.get()
            if frame is None:
                return
            yield bytes(frame.data)

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def close(self) -> None:
        from agent_sandbox.engine import engine_pb2 as pb2

        if self._send is not None:
            await self._send.put(pb2.PtyFrame(op="close"))
            await self._send.put(None)
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except Exception:
                self._task.cancel()
        self._connected = False

    async def __aenter__(self) -> EngineTerminal:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


async def open_terminal(sandbox_id: str, *, cols: int = 80, rows: int = 24) -> EngineTerminal:
    """Open a PTY. The engine holds the WebSocket."""
    return await EngineTerminal(sandbox_id, cols=cols, rows=rows).connect()
