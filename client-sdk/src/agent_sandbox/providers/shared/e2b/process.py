"""envd API protocol — process management (Connect protocol).

Uses Connect RPC over HTTP with application/connect+json content type.
Streaming endpoints (Start, Connect) return AsyncIterator of typed chunks.

RPC endpoints（已实测验证）:
- /process.Process/Start (streaming) — Start a process and stream output
- /process.Process/List — List running processes
- /process.Process/Connect (streaming) — Connect to existing process output
- /process.Process/Update — Update process settings
- /process.Process/SendInput — Send stdin to a process
- /process.Process/SendSignal — Send signal to a process
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import httpx

from agent_sandbox.models.errors import CommandTimeoutError
from agent_sandbox.models.process import (
    ProcessChunk,
    ProcessChunkType,
    ProcessInfo,
)
from agent_sandbox.transport.codec import ConnectCodec
from agent_sandbox.transport.http import envd_status_error
from agent_sandbox.transport.streaming import StreamReader
from agent_sandbox.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from agent_sandbox.providers.shared.e2b.auth import EnvdTokenManager
    from agent_sandbox.transport.http import HttpClient

logger = get_logger("protocol.process")

# Extra seconds added to the process-level timeout to derive the HTTP read
# timeout.  This avoids the HTTP layer timing out *before* the server-side
# process timeout fires, which would produce a misleading ReadTimeout
# instead of a clean process-timeout error.
_HTTP_TIMEOUT_BUFFER: float = 5.0

_codec = ConnectCodec()

# RPC paths（已实测验证）
_START = _codec.build_rpc_path("process", "Process", "Start")
_LIST = _codec.build_rpc_path("process", "Process", "List")
_CONNECT = _codec.build_rpc_path("process", "Process", "Connect")
_UPDATE = _codec.build_rpc_path("process", "Process", "Update")
_SEND_INPUT = _codec.build_rpc_path("process", "Process", "SendInput")
_SEND_SIGNAL = _codec.build_rpc_path("process", "Process", "SendSignal")


# envd ``Signal`` enum (process.proto): only these two can be delivered through ``SendSignal``.
_SIGNAL_NAMES: dict[int, str] = {9: "SIGNAL_SIGKILL", 15: "SIGNAL_SIGTERM"}


def _process_selector(pid: int | str) -> dict[str, Any]:
    """Build envd's ``ProcessSelector`` (``{"pid": N}`` or ``{"tag": "..."}``).

    A digit-only string is a pid (the CLI passes pids as text); any other string is a process tag.
    """
    if isinstance(pid, bool):
        raise TypeError("pid must be an int or str, not bool")
    if isinstance(pid, int):
        return {"pid": pid}
    text = str(pid).strip()
    if text.isdigit():
        return {"pid": int(text)}
    return {"tag": text}


def _parse_process_chunk(frame: dict[str, Any]) -> ProcessChunk:
    """Parse a streaming frame into a ProcessChunk.

    已实测验证的 NDJSON event 格式:
    - {"event":{"start":{"pid":N}}} — 进程启动
    - {"event":{"data":{"stdout":"base64"}}} — stdout 数据（base64 编码）
    - {"event":{"data":{"stderr":"base64"}}} — stderr 数据（base64 编码）
    - {"event":{"end":{"exitCode":N,"exited":bool,"status":"exited"}}} — 进程结束
    - {} — 空结束帧（忽略）
    """
    event = frame.get("event")
    if not event or not isinstance(event, dict):
        # 空帧或无 event 字段 — 忽略
        return ProcessChunk(type=ProcessChunkType.STDOUT, data="")

    # 进程启动事件
    if "start" in event:
        start_data = event["start"]
        pid = start_data.get("pid", 0)
        return ProcessChunk(
            type=ProcessChunkType.STDOUT,
            data="",
            exit_code=None,
            pid=pid,
        )

    # 数据输出事件（stdout/stderr，base64 编码）
    if "data" in event:
        data_obj = event["data"]
        if "stdout" in data_obj:
            raw = data_obj["stdout"]
            try:
                decoded = base64.b64decode(raw).decode("utf-8", errors="replace")
            except Exception:
                decoded = raw
            return ProcessChunk(type=ProcessChunkType.STDOUT, data=decoded)
        if "stderr" in data_obj:
            raw = data_obj["stderr"]
            try:
                decoded = base64.b64decode(raw).decode("utf-8", errors="replace")
            except Exception:
                decoded = raw
            return ProcessChunk(type=ProcessChunkType.STDERR, data=decoded)

    # 进程结束事件
    if "end" in event:
        end_data = event["end"]
        exit_code = end_data.get("exitCode")
        if exit_code is None:
            status = str(end_data.get("status") or "")
            tail = status.rsplit(" ", 1)[-1] if status else ""
            exit_code = int(tail) if tail.isdigit() else 0
        return ProcessChunk(
            type=ProcessChunkType.EXIT,
            exit_code=exit_code,
        )

    # 未知事件
    return ProcessChunk(type=ProcessChunkType.STDOUT, data="")


class ProcessProtocol:
    """Typed wrapper for envd process operations (Connect protocol).

    已实测验证的方法: Start, List, Connect, Update, SendInput, SendSignal
    """

    def __init__(self, http_client: HttpClient) -> None:
        self._http = http_client

    async def start(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        cmd: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str = "",
        timeout: int = 60,
        user: str = "",
    ) -> StreamReader[ProcessChunk]:
        """Start a process and return a streaming reader.

        POST envd_url + /process.Process/Start (Connect streaming)

        请求格式（已实测验证）: {"process": {"cmd": "...", "args": [...]}}

        Note: ``cwd`` and ``user`` are only included in the payload when
        explicitly provided (non-empty).  Sending ``user="user"`` to
        certain platform base images triggers ``fork/exec: no such file
        or directory`` because the envd uses a namespace that doesn't
        recognise that user account.
        """
        process_obj: dict[str, Any] = {
            "cmd": cmd,
        }
        if args:
            process_obj["args"] = args
        if env:
            process_obj["envs"] = env
        if cwd:
            process_obj["cwd"] = cwd
        if user:
            process_obj["user"] = user
        # StartRequest.stdin sits beside process. A missing flag defaults to
        # true, so a reader waits until the HTTP timeout. Proto JSON drops an
        # unknown field nested under process.
        payload: dict[str, Any] = {"process": process_obj, "stdin": False}

        # Derive the HTTP read timeout from the process-level timeout so
        # that long-running commands (e.g. ``pip install``) are not killed
        # prematurely by the HTTP layer's default 30 s timeout.
        http_timeout = float(timeout) + _HTTP_TIMEOUT_BUFFER

        raw_stream = self._http.envd_stream(
            envd_url,
            _START,
            payload=payload,
            envd_token=envd_token,
            request_timeout=http_timeout,
        )

        guarded = self._guard_command_timeout(
            raw_stream, envd_url, envd_token, timeout=timeout, http_timeout=http_timeout
        )
        return StreamReader(guarded, _parse_process_chunk)

    async def _guard_command_timeout(
        self,
        raw_stream: AsyncIterator[dict[str, Any]],
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        timeout: int,
        http_timeout: float,
    ) -> AsyncIterator[dict[str, Any]]:
        """Re-raise the HTTP read timeout of a command stream as :class:`CommandTimeoutError`.

        The HTTP read timeout is derived from the command timeout, so a silent command that
        outlives it surfaces from httpx as ``ReadTimeout``.  The process is killed on a
        best-effort basis (closing the HTTP stream does not stop it) and the SDK error is raised.
        """
        pid: int | None = None
        try:
            async for frame in raw_stream:
                started = (frame.get("event") or {}).get("start")
                if isinstance(started, dict) and isinstance(started.get("pid"), int):
                    pid = started["pid"]
                yield frame
        except httpx.ReadTimeout as exc:
            if pid is not None:
                try:
                    await self.send_signal(
                        envd_url, envd_token, pid=pid, signal=9, request_timeout=10.0
                    )
                except Exception:  # best effort: the timeout is what the caller must see
                    logger.debug("could not kill timed-out process %s", pid)
            detail = f"no output for {http_timeout:g}s"
            if pid is not None:
                detail += f"; pid {pid} was asked to stop"
            raise CommandTimeoutError(
                f"Command did not finish within {timeout}s ({detail})."
            ) from exc

    async def _unary(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        rpc_path: str,
        payload: dict[str, Any],
        *,
        request_timeout: float | None = None,
    ) -> dict[str, Any]:
        """Unary envd call whose HTTP errors surface as :class:`EnvdRpcError`."""
        try:
            return await self._http.envd_request(
                envd_url,
                rpc_path,
                payload=payload,
                envd_token=envd_token,
                request_timeout=request_timeout,
            )
        except httpx.HTTPStatusError as exc:
            raise envd_status_error(exc, rpc_path) from exc

    async def list_processes(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
    ) -> list[ProcessInfo]:
        """List running processes in the sandbox.

        POST envd_url + /process.Process/List (Connect unary, 已实测验证)
        """
        response = await self._unary(envd_url, envd_token, _LIST, {})

        processes = response.get("processes", response.get("result", {}).get("processes", []))
        return [ProcessInfo.model_validate(p) for p in processes]

    async def connect_to_process(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        pid: int | str,
    ) -> StreamReader[ProcessChunk]:
        """Connect to an existing process and stream its output.

        POST envd_url + /process.Process/Connect (Connect streaming, 已实测验证)
        """
        raw_stream = self._http.envd_stream(
            envd_url,
            _CONNECT,
            payload={"process": _process_selector(pid)},
            envd_token=envd_token,
        )
        return StreamReader(raw_stream, _parse_process_chunk)

    async def update(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        pid: int | str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update process settings.

        POST envd_url + /process.Process/Update (Connect unary, 已实测验证)
        """
        payload: dict[str, Any] = {"process": _process_selector(pid), **kwargs}
        return await self._unary(envd_url, envd_token, _UPDATE, payload)

    async def send_input(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        pid: int | str,
        data: str,
    ) -> None:
        """Send data to a process's stdin.

        POST envd_url + /process.Process/SendInput (Connect unary, 已实测验证)

        Body: ``{"process": {"pid": N}, "input": {"stdin": <base64>}}`` (``bytes`` fields are
        base64 in protobuf-JSON).
        """
        stdin = base64.b64encode(data.encode("utf-8")).decode("ascii")
        await self._unary(
            envd_url,
            envd_token,
            _SEND_INPUT,
            {"process": _process_selector(pid), "input": {"stdin": stdin}},
        )

    async def send_signal(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        pid: int | str,
        signal: int = 15,
        request_timeout: float | None = None,
    ) -> None:
        """Send a signal to a process (SIGTERM=15 or SIGKILL=9).

        POST envd_url + /process.Process/SendSignal (Connect unary, 已实测验证)

        Body: ``{"process": {"pid": N}, "signal": "SIGNAL_SIGTERM" | "SIGNAL_SIGKILL"}``.
        envd's ``Signal`` enum has only those two values.

        The pid is envd's process id (``Commands.list()`` / the ``start`` event), which is not
        necessarily the OS pid, so other signals cannot be emulated with ``kill``.

        Raises:
            ValueError: *signal* is neither 15 nor 9.
        """
        name = _SIGNAL_NAMES.get(signal)
        if name is None:
            raise ValueError(
                f"envd can only deliver SIGTERM (15) and SIGKILL (9) to a process; got {signal!r}"
            )
        await self._unary(
            envd_url,
            envd_token,
            _SEND_SIGNAL,
            {"process": _process_selector(pid), "signal": name},
            request_timeout=request_timeout,
        )
