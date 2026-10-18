"""Typed client for the in-sandbox SandboxServer (``agent_sandbox.server``, port 9000).

The sandbox has two data planes: the platform-injected *envd* (what :attr:`Sandbox.commands`,
:attr:`Sandbox.files`, ... talk to) and the template-authored **SandboxServer**.  This module
covers the second one: every server endpoint has a typed method, with ``*_sync`` twins in the
same ``make_sync`` style as the rest of the SDK::

    server = sandbox.server                       # bound to port 9000 of the sandbox
    caps = await server.discover()                # what may this identity do?
    if caps.can("files_upload_stream"):
        await server.files.upload("/home/user/out/a.txt", b"hello")
    await server.files.download("/home/user/out/a.txt")

Errors are typed (:mod:`agent_sandbox.models.errors`, ``E9xxx``) and, where the semantics match,
subclass the SDK's existing exceptions (``PermissionDeniedError``, ``CapabilityNotSupportedError``,
``AuthenticationError``).  Discovery is *explicit*: no hidden ``GET /capabilities`` is ever
issued.  After :meth:`ServerClient.discover` the client fails fast (before the network round
trip) for endpoints the server disabled or the identity may not call; the server's answer
remains authoritative either way.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from agent_sandbox.api.server_capabilities import ServerCapabilities
from agent_sandbox.models.errors import (
    CommandArgumentError,
    CommandExecutionError,
    CommandNotFoundError,
    CommandTimeoutError,
    ConnectionError_,
    EndpointNotAvailableError,
    FileNotFoundError_,
    FilePolicyDeniedError,
    PayloadTooLargeError,
    PolicyDeniedError,
    RateLimitedError,
    ServerAPIError,
    ServerAuthError,
)
from agent_sandbox.models.server import (
    ArchiveResult,
    BrowserContent,
    BrowserPage,
    CodeRunResult,
    DeleteResult,
    GitDiff,
    GitStatus,
    ListeningPort,
    MkdirResult,
    MoveResult,
    PackageList,
    PathDecision,
    ProcessOutput,
    ProcessOutputEvent,
    PtyCreated,
    PtyMessage,
    PtySessionInfo,
    SearchResult,
    ServerCommand,
    ServerFileEntry,
    ServerFileInfo,
    ServerProcess,
    ServerWatchEvent,
    ShellEvent,
    ShellEventType,
    ShellResult,
    SignalResult,
    StdinResult,
    SystemInfo,
    SystemMetrics,
    TransferResult,
)
from agent_sandbox.utils.async_bridge import make_sync
from agent_sandbox.utils.logging import get_logger

if TYPE_CHECKING:
    import builtins
    from collections.abc import AsyncGenerator, AsyncIterator, Callable, Sequence
    from types import TracebackType

logger = get_logger("api.server_client")

DEFAULT_SERVER_PORT = 9000
DEFAULT_PTY_PORT = 9001

#: Policy denial codes that concern a path; mapped to :class:`FilePolicyDeniedError`.
_FILE_DENIAL_CODES = frozenset(
    {
        "path_not_allowed",
        "path_denied",
        "read_only",
        "symlink_denied",
        "extension_not_allowed",
        "file_exists",
        "path_invalid",
        "path_too_long",
    }
)

_SYNC_TIMEOUT_SLACK = 10.0


def error_from_response(
    status: int,
    body: Any,
    *,
    endpoint: str = "",
    headers: dict[str, str] | None = None,
) -> Exception:
    """Map a server error response to the matching typed exception (never raises itself)."""
    data: dict[str, Any] = body if isinstance(body, dict) else {}
    message = str(data.get("error") or (body if isinstance(body, str) and body else "")) or (
        f"Server returned HTTP {status}"
    )
    etype = str(data.get("type", ""))
    code = str(data.get("code", ""))
    ep = str(data.get("endpoint", "") or endpoint)
    common: dict[str, Any] = {
        "status_code": status,
        "error_type": etype,
        "error_code": code,
        "endpoint": ep,
        "rule": str(data.get("rule", "") or ""),
    }
    if status == 401:
        return ServerAuthError(message, **common)
    if status == 403 or (status == 409 and (etype == "PolicyDenied" or code in _FILE_DENIAL_CODES)):
        scope = str(data.get("scope", ""))
        if code in _FILE_DENIAL_CODES:
            return FilePolicyDeniedError(message, scope=scope, **common)
        return PolicyDeniedError(message, scope=scope, **common)
    if status == 404 and code == "endpoint_disabled":
        extra = {k: v for k, v in common.items() if k != "endpoint"}
        return EndpointNotAvailableError(ep, message=message, **extra)
    if status == 404 and etype in {"FileNotFoundError", "NotADirectoryError"}:
        return FileNotFoundError_(message)
    if status == 413:
        limit = data.get("limit")
        return PayloadTooLargeError(
            message, limit=int(limit) if isinstance(limit, (int, float)) else None, **common
        )
    if status == 429 and (
        etype == "RateLimited" or code in {"rate_limited", "concurrency_limited"}
    ):
        retry: float | None = None
        raw = data.get("retry_after")
        if raw is None and headers:
            raw = headers.get("retry-after")
        with contextlib.suppress(TypeError, ValueError):
            retry = float(raw) if raw is not None else None
        return RateLimitedError(message, retry_after=retry, **common)
    if etype == "TimeoutError":
        return CommandTimeoutError(message)
    return ServerAPIError(message, **common)


# --------------------------------------------------------------------------- #
# Server-Sent Events
# --------------------------------------------------------------------------- #


async def _iter_sse(response: httpx.Response) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
    """Yield ``(event, data)`` pairs from an SSE response."""
    event = "message"
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if data_lines:
                raw = "\n".join(data_lines)
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = {"data": raw}
                yield event, parsed if isinstance(parsed, dict) else {"data": parsed}
            event, data_lines = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:][1:] if line[5:6] == " " else line[5:])
    if data_lines:
        with contextlib.suppress(json.JSONDecodeError):
            parsed = json.loads("\n".join(data_lines))
            yield event, parsed if isinstance(parsed, dict) else {"data": parsed}


def _bool(value: bool) -> str:
    return "true" if value else "false"


# --------------------------------------------------------------------------- #
# Sub-APIs
# --------------------------------------------------------------------------- #


class _Api:
    def __init__(self, client: ServerClient) -> None:
        self._c = client


class ServerFilesApi(_Api):
    """File operations of the server (``/files/*``, plus the legacy ``/upload``/``/download``)."""

    async def list(
        self, path: str, *, recursive: bool = False, max_entries: int | None = None
    ) -> list[ServerFileEntry]:
        params: dict[str, Any] = {"path": path, "recursive": _bool(recursive)}
        if max_entries is not None:
            params["max_entries"] = max_entries
        data = await self._c._request("files_list", "GET", "/files/list", params=params)
        return [ServerFileEntry.model_validate(e) for e in data.get("entries", [])]

    async def stat(self, path: str) -> ServerFileInfo:
        data = await self._c._request("files_stat", "GET", "/files/stat", params={"path": path})
        return ServerFileInfo.model_validate(data)

    async def exists(self, path: str) -> bool:
        """Whether *path* exists.  Policy denials raise (they are never reported as ``False``)."""
        return (await self.stat(path)).exists

    async def mkdir(self, path: str) -> MkdirResult:
        data = await self._c._request(
            "files_mkdir", "POST", "/files/mkdir", json_body={"path": path}
        )
        return MkdirResult.model_validate(data)

    async def delete(self, path: str) -> DeleteResult:
        data = await self._c._request("files_delete", "DELETE", "/files", params={"path": path})
        return DeleteResult.model_validate(data if isinstance(data, dict) else {})

    async def move(self, source: str, destination: str) -> MoveResult:
        data = await self._c._request(
            "files_move",
            "POST",
            "/files/move",
            json_body={"source": source, "destination": destination},
        )
        return MoveResult.model_validate(data)

    async def search(
        self,
        path: str,
        pattern: str,
        *,
        max_depth: int | None = None,
        max_results: int | None = None,
    ) -> SearchResult:
        body: dict[str, Any] = {"path": path, "pattern": pattern}
        if max_depth is not None:
            body["max_depth"] = max_depth
        if max_results is not None:
            body["max_results"] = max_results
        data = await self._c._request("files_search", "POST", "/files/search", json_body=body)
        return SearchResult.model_validate(data)

    def _precheck_upload(self, endpoint: str, payload: bytes, path: str) -> None:
        caps = self._c.capabilities
        if caps is None:
            return
        max_bytes = caps.limit(endpoint, "max_bytes")
        if isinstance(max_bytes, (int, float)) and len(payload) > max_bytes:
            raise PayloadTooLargeError(
                f"Upload of {len(payload)} bytes exceeds the server limit of {int(max_bytes)} "
                f"bytes for {endpoint}",
                limit=int(max_bytes),
                error_code="payload_too_large",
                endpoint=endpoint,
            )
        max_request = caps.limit(endpoint, "max_request_bytes")
        encoded = (len(payload) + 2) // 3 * 4 + len(path) + 64
        if isinstance(max_request, (int, float)) and encoded > max_request:
            raise PayloadTooLargeError(
                f"Encoded upload (~{encoded} bytes) exceeds the server request limit of "
                f"{int(max_request)} bytes for {endpoint}",
                limit=int(max_request),
                error_code="payload_too_large",
                endpoint=endpoint,
            )

    async def upload(self, path: str, data: bytes | str) -> TransferResult:
        """Write *data* to *path* (``POST /files/upload-stream``, base64 over JSON)."""
        payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        self._c._precheck("files_upload_stream")
        self._precheck_upload("files_upload_stream", payload, path)
        body = {"path": path, "content_base64": base64.b64encode(payload).decode("ascii")}
        out = await self._c._request(
            "files_upload_stream", "POST", "/files/upload-stream", json_body=body
        )
        return TransferResult.model_validate(out)

    async def upload_file(self, local_path: str | Path, remote_path: str) -> TransferResult:
        """Upload a local file."""
        payload = await asyncio.to_thread(Path(local_path).read_bytes)
        return await self.upload(remote_path, payload)

    async def upload_legacy(self, path: str, data: bytes | str) -> TransferResult:
        """Write through the legacy ``POST /upload`` endpoint (own policy rules)."""
        payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        self._c._precheck("upload")
        self._precheck_upload("upload", payload, path)
        body = {"path": path, "content_base64": base64.b64encode(payload).decode("ascii")}
        out = await self._c._request("upload", "POST", "/upload", json_body=body)
        return TransferResult.model_validate(out)

    @staticmethod
    def _decode_content(data: dict[str, Any]) -> bytes:
        try:
            return base64.b64decode(str(data["content_base64"]))
        except (KeyError, ValueError) as exc:
            raise ServerAPIError(
                "Server returned an invalid download body", error_type="ProtocolError"
            ) from exc

    async def download(self, path: str) -> bytes:
        """Read *path* (``GET /files/download-stream``)."""
        data = await self._c._request(
            "files_download_stream", "GET", "/files/download-stream", params={"path": path}
        )
        return self._decode_content(data)

    async def read_text(self, path: str, encoding: str = "utf-8") -> str:
        return (await self.download(path)).decode(encoding)

    async def download_file(self, remote_path: str, local_path: str | Path) -> int:
        """Download to a local file; returns the number of bytes written."""
        payload = await self.download(remote_path)
        await asyncio.to_thread(Path(local_path).write_bytes, payload)
        return len(payload)

    async def download_legacy(self, path: str) -> bytes:
        """Read through the legacy ``GET /download`` endpoint (own policy rules)."""
        data = await self._c._request("download", "GET", "/download", params={"path": path})
        return self._decode_content(data)

    async def archive(self, paths: builtins.list[str], format: str = "tar.gz") -> ArchiveResult:
        """Create a ``tar.gz`` or ``zip`` archive of *paths* (returned in memory)."""
        data = await self._c._request(
            "files_archive",
            "POST",
            "/files/archive",
            json_body={"paths": list(paths), "format": format},
        )
        return ArchiveResult.model_validate(data)

    async def watch(
        self,
        path: str,
        *,
        recursive: bool = False,
        interval: float | None = None,
        timeout: float | None = None,
    ) -> AsyncGenerator[ServerWatchEvent, None]:
        """Stream created / modified / deleted events until the server's watch window ends.

        Use ``contextlib.aclosing(server.files.watch(...))`` to stop early deterministically.
        """
        params: dict[str, Any] = {"path": path, "recursive": _bool(recursive)}
        if interval is not None:
            params["interval"] = interval
        if timeout is not None:
            params["timeout"] = timeout
        http_timeout = (timeout if timeout is not None else 300.0) + _SYNC_TIMEOUT_SLACK
        async for event, data in self._c._stream(
            "files_watch", "GET", "/files/watch", params=params, timeout=http_timeout
        ):
            if event == "change":
                yield ServerWatchEvent.model_validate(data)
            elif event == "end":
                return

    async def watch_for(
        self,
        path: str,
        seconds: float,
        *,
        recursive: bool = False,
        interval: float | None = None,
    ) -> builtins.list[ServerWatchEvent]:
        """Collect the events of a *seconds*-long watch window."""
        events: list[ServerWatchEvent] = []
        async with contextlib.aclosing(
            self.watch(path, recursive=recursive, interval=interval, timeout=seconds)
        ) as stream:
            async for event in stream:
                events.append(event)
        return events

    list_sync = make_sync(list)
    stat_sync = make_sync(stat)
    exists_sync = make_sync(exists)
    mkdir_sync = make_sync(mkdir)
    delete_sync = make_sync(delete)
    move_sync = make_sync(move)
    search_sync = make_sync(search)
    upload_sync = make_sync(upload)
    upload_file_sync = make_sync(upload_file)
    upload_legacy_sync = make_sync(upload_legacy)
    download_sync = make_sync(download)
    read_text_sync = make_sync(read_text)
    download_file_sync = make_sync(download_file)
    download_legacy_sync = make_sync(download_legacy)
    archive_sync = make_sync(archive)
    watch_for_sync = make_sync(watch_for)


class ServerProcessApi(_Api):
    """Shell commands and background processes (``/shell*``, ``/process/*``)."""

    async def shell(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ShellResult:
        """Run *command* to completion (``POST /shell``); the command is tokenised, not shelled."""
        body = self._exec_body(command, cwd, env, timeout)
        data = await self._c._request(
            "shell",
            "POST",
            "/shell",
            json_body=body,
            timeout=(timeout if timeout is not None else 300.0) + _SYNC_TIMEOUT_SLACK,
        )
        return ShellResult.model_validate(data)

    @staticmethod
    def _exec_body(
        command: str, cwd: str | None, env: dict[str, str] | None, timeout: float | None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"command": command}
        if cwd is not None:
            body["cwd"] = cwd
        if env:
            body["env"] = dict(env)
        if timeout is not None:
            body["timeout"] = timeout
        return body

    async def shell_stream(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> AsyncGenerator[ShellEvent, None]:
        """Stream ``stdout`` / ``stderr`` lines and the final ``exit`` event (SSE)."""
        body = self._exec_body(command, cwd, env, timeout)
        http_timeout = (timeout if timeout is not None else 300.0) + _SYNC_TIMEOUT_SLACK
        async for event, data in self._c._stream(
            "shell_stream",
            "POST",
            "/shell/stream",
            json_body=body,
            timeout=http_timeout,
        ):
            try:
                kind = ShellEventType(event)
            except ValueError:
                continue
            yield ShellEvent(
                event=kind,
                data=str(data.get("data", "")),
                exit_code=data.get("exit_code"),
                error=str(data.get("error", "")),
            )

    async def run_stream(
        self,
        command: str,
        *,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ShellResult:
        """Run *command* streaming, invoking the callbacks per line; returns the collected result.

        Raises:
            CommandTimeoutError: The server killed the command on its timeout.
            PayloadTooLargeError: The server's ``max_output_bytes`` limit stopped the command.
        """
        out: list[str] = []
        err: list[str] = []
        exit_code = 0
        async with contextlib.aclosing(
            self.shell_stream(command, cwd=cwd, env=env, timeout=timeout)
        ) as stream:
            async for ev in stream:
                if ev.event == ShellEventType.STDOUT:
                    out.append(ev.data)
                    if on_stdout:
                        on_stdout(ev.data)
                elif ev.event == ShellEventType.STDERR:
                    err.append(ev.data)
                    if on_stderr:
                        on_stderr(ev.data)
                elif ev.event == ShellEventType.ERROR:
                    if ev.error == "timeout":
                        raise CommandTimeoutError(f"Command timed out: {command}")
                    if ev.error == "output_limit":
                        raise PayloadTooLargeError(
                            "Command output exceeded the server limit", endpoint="shell_stream"
                        )
                    raise ServerAPIError(ev.error or "stream error", endpoint="shell_stream")
                elif ev.event == ShellEventType.EXIT:
                    exit_code = ev.exit_code if ev.exit_code is not None else 0
        return ShellResult(
            stdout="".join(f"{line}\n" for line in out),
            stderr="".join(f"{line}\n" for line in err),
            exit_code=exit_code,
        )

    async def start(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        capture_output: bool = False,
        stdin: bool = False,
    ) -> ServerProcess:
        """Start a background process (``POST /process/start``)."""
        body = self._exec_body(command, cwd, env, None)
        if capture_output:
            body["capture_output"] = True
        if stdin:
            body["stdin"] = True
        data = await self._c._request("process_start", "POST", "/process/start", json_body=body)
        return ServerProcess(pid=int(data["pid"]), command=str(data.get("command", command)))

    async def list(self) -> list[ServerProcess]:
        data = await self._c._request("process_list", "GET", "/process/list")
        return [ServerProcess.model_validate(p) for p in data.get("processes", [])]

    async def get(self, pid: int) -> ServerProcess:
        data = await self._c._request("process_detail", "GET", f"/process/{int(pid)}")
        return ServerProcess.model_validate(data)

    async def signal(self, pid: int, sig: int = 15) -> SignalResult:
        """Send a signal (the server restricts it to ``allowed_signals``)."""
        data = await self._c._request(
            "process_signal", "POST", f"/process/{int(pid)}/signal", json_body={"signal": int(sig)}
        )
        return SignalResult.model_validate(data)

    async def kill(self, pid: int) -> SignalResult:
        """``SIGKILL``."""
        return await self.signal(pid, 9)

    async def terminate(self, pid: int) -> SignalResult:
        """``SIGTERM``."""
        return await self.signal(pid, 15)

    async def send_stdin(self, pid: int, data: str | bytes, *, eof: bool = False) -> StdinResult:
        """Write to stdin of a process started with ``stdin=True``."""
        body: dict[str, Any] = {}
        if isinstance(data, bytes):
            body["data_base64"] = base64.b64encode(data).decode("ascii")
        elif data:
            body["data"] = data
        if eof:
            body["eof"] = True
        out = await self._c._request(
            "process_stdin", "POST", f"/process/{int(pid)}/stdin", json_body=body
        )
        return StdinResult.model_validate(out)

    async def close_stdin(self, pid: int) -> StdinResult:
        return await self.send_stdin(pid, "", eof=True)

    async def output(self, pid: int, *, since: int = 0, wait: float = 0.0) -> ProcessOutput:
        """Read captured output (``capture_output=True``); long-polls up to *wait* seconds."""
        data = await self._c._request(
            "process_output",
            "GET",
            f"/process/{int(pid)}/output",
            params={"since": since, "wait": wait},
            timeout=wait + _SYNC_TIMEOUT_SLACK + self._c.timeout,
        )
        return ProcessOutput.model_validate(data)

    async def follow(
        self, pid: int, *, since: int = 0, poll: float = 5.0
    ) -> AsyncGenerator[ProcessOutputEvent, None]:
        """Yield output events of a captured process until it has exited and drained."""
        cursor = since
        while True:
            chunk = await self.output(pid, since=cursor, wait=poll)
            for ev in chunk.events:
                yield ev
            cursor = chunk.next
            if chunk.state != "running" and not chunk.events:
                return

    async def wait(self, pid: int, *, timeout: float | None = None, poll: float = 1.0) -> int:
        """Block until the process exits; returns the exit code.

        Raises:
            CommandTimeoutError: *timeout* elapsed first.
        """
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout
        while True:
            info = await self.get(pid)
            if info.state != "running":
                return info.exit_code if info.exit_code is not None else 0
            if deadline is not None and loop.time() >= deadline:
                raise CommandTimeoutError(f"Process {pid} still running after {timeout}s")
            await asyncio.sleep(poll)

    shell_sync = make_sync(shell)
    run_stream_sync = make_sync(run_stream)
    start_sync = make_sync(start)
    list_sync = make_sync(list)
    get_sync = make_sync(get)
    signal_sync = make_sync(signal)
    kill_sync = make_sync(kill)
    terminate_sync = make_sync(terminate)
    send_stdin_sync = make_sync(send_stdin)
    close_stdin_sync = make_sync(close_stdin)
    output_sync = make_sync(output)
    wait_sync = make_sync(wait)


class PtyConnection:
    """A live WebSocket attached to a server PTY session (async context manager).

    Example::

        created = await server.pty.create(shell="/bin/bash")
        async with server.pty.connect(created.session_id) as term:
            await term.send("echo hi\\n")
            text = await term.expect("hi", timeout=5)
    """

    def __init__(self, url: str, headers: dict[str, str], session_id: str) -> None:
        self.url = url
        self.session_id = session_id
        self._headers = headers
        self._ws: Any = None

    async def __aenter__(self) -> PtyConnection:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def open(self) -> None:
        try:
            import websockets.asyncio.client as ws_client
        except ImportError as exc:  # pragma: no cover - hard dependency
            raise ImportError("websockets package is required: pip install websockets") from exc
        try:
            self._ws = await ws_client.connect(self.url, additional_headers=self._headers)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 401:
                raise ServerAuthError(
                    "PTY WebSocket rejected the credentials", status_code=401
                ) from exc
            if status == 403:
                raise PolicyDeniedError(
                    "PTY WebSocket denied by policy", status_code=403, endpoint="pty_connect"
                ) from exc
            raise ConnectionError_(f"PTY WebSocket connection failed: {exc}") from exc

    async def send(self, data: str) -> None:
        """Send keystrokes / text to the terminal."""
        await self._send({"type": "input", "data": data})

    async def resize(self, cols: int, rows: int) -> None:
        await self._send({"type": "resize", "cols": int(cols), "rows": int(rows)})

    async def signal(self, name: str = "SIGINT") -> None:
        await self._send({"type": "signal", "signal": name})

    async def _send(self, message: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("PtyConnection is not open")
        await self._ws.send(json.dumps(message))

    async def recv(self, timeout: float | None = None) -> PtyMessage | None:
        """Next message, or ``None`` when the connection closed."""
        if self._ws is None:
            raise RuntimeError("PtyConnection is not open")
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout)
        except Exception as exc:
            if isinstance(exc, asyncio.TimeoutError):
                raise
            if type(exc).__name__.startswith("ConnectionClosed"):
                return None
            raise
        try:
            return PtyMessage.model_validate(json.loads(raw))
        except (ValueError, TypeError):
            return PtyMessage(type="output", data=str(raw))

    def __aiter__(self) -> AsyncIterator[PtyMessage]:
        return self._messages()

    async def _messages(self) -> AsyncGenerator[PtyMessage, None]:
        while True:
            msg = await self.recv()
            if msg is None:
                return
            yield msg

    async def expect(self, text: str, timeout: float = 10.0) -> str:
        """Collect output until *text* appears; returns everything read so far.

        Raises:
            CommandTimeoutError: *text* did not appear within *timeout* seconds.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        buffer = ""
        while text not in buffer:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise CommandTimeoutError(f"Did not see {text!r} within {timeout}s")
            try:
                msg = await self.recv(timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise CommandTimeoutError(f"Did not see {text!r} within {timeout}s") from exc
            if msg is None:
                break
            if msg.type == "output":
                buffer += msg.data
        return buffer

    async def close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()


class ServerPtyApi(_Api):
    """PTY sessions (``/pty/sessions*`` plus the WebSocket on the PTY port)."""

    async def create(
        self,
        shell: str = "/bin/bash",
        *,
        cols: int = 80,
        rows: int = 24,
        env: dict[str, str] | None = None,
    ) -> PtyCreated:
        body: dict[str, Any] = {"shell": shell, "cols": cols, "rows": rows}
        if env:
            body["env"] = dict(env)
        data = await self._c._request("pty_create_session", "POST", "/pty/sessions", json_body=body)
        return PtyCreated.model_validate(data)

    async def list(self) -> list[PtySessionInfo]:
        data = await self._c._request("pty_list_sessions", "GET", "/pty/sessions")
        return [PtySessionInfo.model_validate(s) for s in data.get("sessions", [])]

    async def get(self, session_id: str) -> PtySessionInfo:
        data = await self._c._request(
            "pty_detail", "GET", f"/pty/sessions/{quote(session_id, safe='')}"
        )
        return PtySessionInfo.model_validate(data)

    async def resize(self, session_id: str, cols: int, rows: int) -> PtySessionInfo:
        data = await self._c._request(
            "pty_resize",
            "POST",
            f"/pty/sessions/{quote(session_id, safe='')}/resize",
            json_body={"cols": int(cols), "rows": int(rows)},
        )
        return PtySessionInfo.model_validate(data)

    async def delete(self, session_id: str) -> None:
        await self._c._request(
            "pty_delete_session", "DELETE", f"/pty/sessions/{quote(session_id, safe='')}"
        )

    def connect(self, session_id: str) -> PtyConnection:
        """WebSocket attachment (use as ``async with``).  Requires ``pty_connect`` + scope."""
        self._c._precheck("pty_connect")
        url = f"{self._c.pty_url}/pty?session_id={quote(session_id, safe='')}"
        return PtyConnection(url, self._c.auth_headers(), session_id)

    create_sync = make_sync(create)
    list_sync = make_sync(list)
    get_sync = make_sync(get)
    resize_sync = make_sync(resize)
    delete_sync = make_sync(delete)


class ServerSystemApi(_Api):
    """System information and environment (``/system/*``, ``/env``, ``/ports``, ``/packages``)."""

    async def info(self) -> SystemInfo:
        return SystemInfo.model_validate(
            await self._c._request("system_info", "GET", "/system/info")
        )

    async def metrics(self) -> SystemMetrics:
        return SystemMetrics.model_validate(
            await self._c._request("system_metrics", "GET", "/system/metrics")
        )

    async def env(self, names: Sequence[str] | None = None) -> dict[str, str]:
        """Environment variables, optionally restricted to *names* (a server-side whitelist).

        The server redacts secrets and applies its ``allow_vars`` / ``deny_vars`` policy.
        """
        params = {"filter": ",".join(names)} if names else None
        data = await self._c._request("env_get", "GET", "/env", params=params)
        return {str(k): str(v) for k, v in (data.get("variables") or {}).items()}

    async def set_env(self, variables: dict[str, str]) -> list[str]:
        """Set variables in the server process; returns the updated names."""
        data = await self._c._request("env_set", "POST", "/env", json_body={"vars": variables})
        return [str(n) for n in data.get("updated", [])]

    async def ports(self) -> list[ListeningPort]:
        data = await self._c._request("ports", "GET", "/ports")
        return [ListeningPort.model_validate(p) for p in data.get("listening", [])]

    async def packages(self, manager: str = "pip") -> PackageList:
        data = await self._c._request("packages", "GET", "/packages", params={"manager": manager})
        return PackageList.model_validate(data)

    info_sync = make_sync(info)
    metrics_sync = make_sync(metrics)
    env_sync = make_sync(env)
    set_env_sync = make_sync(set_env)
    ports_sync = make_sync(ports)
    packages_sync = make_sync(packages)


class ServerDevtoolsApi(_Api):
    """Developer tools (opt-in server group ``dev_tools``)."""

    async def run_code(
        self, code: str, language: str = "python", *, timeout: float | None = None
    ) -> CodeRunResult:
        """Stateless code execution (``POST /code/run``); not the stateful code interpreter."""
        body: dict[str, Any] = {"code": code, "language": language}
        if timeout is not None:
            body["timeout"] = timeout
        data = await self._c._request(
            "code_run",
            "POST",
            "/code/run",
            json_body=body,
            timeout=(timeout if timeout is not None else 30.0) + _SYNC_TIMEOUT_SLACK,
        )
        return CodeRunResult.model_validate(data)

    async def git_status(self, path: str = ".") -> GitStatus:
        return GitStatus.model_validate(
            await self._c._request("git_status", "GET", "/git/status", params={"path": path})
        )

    async def git_diff(
        self, path: str = ".", *, staged: bool = False, file: str | None = None
    ) -> GitDiff:
        params: dict[str, Any] = {"path": path, "staged": _bool(staged)}
        if file:
            params["file"] = file
        return GitDiff.model_validate(
            await self._c._request("git_diff", "GET", "/git/diff", params=params)
        )

    run_code_sync = make_sync(run_code)
    git_status_sync = make_sync(git_status)
    git_diff_sync = make_sync(git_diff)


class ServerBrowserApi(_Api):
    """Headless browser (opt-in server group ``browser``; needs Playwright in the image)."""

    async def navigate(
        self, url: str, *, wait_until: str = "networkidle", timeout: int | None = None
    ) -> BrowserPage:
        body: dict[str, Any] = {"url": url, "wait_until": wait_until}
        if timeout is not None:
            body["timeout"] = timeout
        data = await self._c._request(
            "browser_navigate", "POST", "/browser/navigate", json_body=body
        )
        return BrowserPage.model_validate(data)

    async def screenshot(
        self, *, selector: str | None = None, full_page: bool = True, format: str = "png"
    ) -> bytes:
        body: dict[str, Any] = {"full_page": full_page, "format": format}
        if selector:
            body["selector"] = selector
        data = await self._c._request(
            "browser_screenshot", "POST", "/browser/screenshot", json_body=body
        )
        return base64.b64decode(str(data.get("image_base64", "")))

    async def content(self, type: str = "html") -> BrowserContent:
        data = await self._c._request(
            "browser_content", "GET", "/browser/content", params={"type": type}
        )
        return BrowserContent.model_validate(data)

    async def click(self, selector: str, *, timeout: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"selector": selector}
        if timeout is not None:
            body["timeout"] = timeout
        result: dict[str, Any] = await self._c._request(
            "browser_click", "POST", "/browser/click", json_body=body
        )
        return result

    async def type(
        self, selector: str, text: str, *, clear: bool = False, delay: int | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"selector": selector, "text": text, "clear": clear}
        if delay is not None:
            body["delay"] = delay
        result: dict[str, Any] = await self._c._request(
            "browser_type", "POST", "/browser/type", json_body=body
        )
        return result

    async def evaluate(self, script: str, *, timeout: int | None = None) -> Any:
        body: dict[str, Any] = {"script": script}
        if timeout is not None:
            body["timeout"] = timeout
        data = await self._c._request(
            "browser_evaluate", "POST", "/browser/evaluate", json_body=body
        )
        return data.get("result")

    async def pdf(self, *, format: str = "A4", landscape: bool = False) -> bytes:
        data = await self._c._request(
            "browser_pdf",
            "POST",
            "/browser/pdf",
            json_body={"format": format, "landscape": landscape},
        )
        return base64.b64decode(str(data.get("pdf_base64", "")))

    async def console(self) -> list[dict[str, Any]]:
        """Collected console messages (the server clears its buffer on read)."""
        data = await self._c._request("browser_console", "GET", "/browser/console")
        return [e for e in data.get("logs", []) if isinstance(e, dict)]

    navigate_sync = make_sync(navigate)
    screenshot_sync = make_sync(screenshot)
    content_sync = make_sync(content)
    click_sync = make_sync(click)
    type_sync = make_sync(type)
    evaluate_sync = make_sync(evaluate)
    pdf_sync = make_sync(pdf)
    console_sync = make_sync(console)


def _command_error(cls: type[ServerAPIError], exc: ServerAPIError) -> ServerAPIError:
    """Re-raise a command failure as a narrower ServerAPIError subclass."""
    message = exc.message
    if exc.error_type and exc.error_type not in message:
        message = f"{exc.error_type}: {message}"
    return cls(
        message,
        status_code=exc.status_code,
        error_type=exc.error_type,
        error_code=exc.error_code,
        endpoint=exc.endpoint,
        rule=exc.rule,
    )


class ServerCommandsApi(_Api):
    """Commands registered on the server (``/commands``)."""

    async def list(self) -> list[ServerCommand]:
        data = await self._c._request("list_commands", "GET", "/commands")
        return [ServerCommand.model_validate(c) for c in data.get("commands", [])]

    async def run(
        self,
        name: str,
        /,
        *,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Invoke command *name*; returns its result value.

        Args:
            name: Registered command name.
            timeout: HTTP timeout in seconds. The default is the client timeout
                (30s). Not sent to the command.
            **kwargs: Command arguments.

        Raises:
            CommandNotFoundError: The server has no such command. The message
                includes the server's list of available commands when it sent one.
            CommandArgumentError: The arguments failed validation (HTTP 400).
            CommandExecutionError: The command function raised (HTTP 500).
        """
        try:
            data = await self._c._request(
                "run_command",
                "POST",
                f"/commands/{quote(name, safe='')}",
                json_body=kwargs,
                timeout=timeout,
            )
        except ServerAPIError as exc:
            if exc.status_code == 404 and exc.error_code != "endpoint_disabled":
                raise CommandNotFoundError(
                    name,
                    detail=exc.message,
                    server_status="reachable but command not found (HTTP 404)",
                ) from exc
            if exc.status_code == 400:
                raise _command_error(CommandArgumentError, exc) from exc
            # 500 is the command function. 502/503 are the gateway, not the function.
            if exc.status_code == 500:
                raise _command_error(CommandExecutionError, exc) from exc
            raise
        return data.get("result")

    list_sync = make_sync(list)
    run_sync = make_sync(run)


# --------------------------------------------------------------------------- #
# The client
# --------------------------------------------------------------------------- #


class ServerClient:
    """Async client for one SandboxServer.

    Args:
        base_url: Server HTTP base URL (``http://host:9000``, or a gateway port URL).
        token: Server token; sent as ``Authorization: Bearer`` (matches ``ABX_SERVER_TOKEN`` or
            a ``auth.tokens`` identity).
        headers: Extra headers on every request, e.g. the gateway's ``X-Access-Token`` from
            ``Sandbox.network.get_access_headers()``.
        pty_url: Base URL of the PTY WebSocket server (default: *base_url* with port 9001, or
            the gateway-style ``9000-<sandbox>`` host rewritten to ``9001-<sandbox>``).
        timeout: Default per-request timeout in seconds.
        http_client: Inject a preconfigured ``httpx.AsyncClient`` (the caller owns its lifecycle).

    Sub-APIs: :attr:`files`, :attr:`process`, :attr:`pty`, :attr:`system`, :attr:`devtools`,
    :attr:`browser`, :attr:`commands`.
    """

    #: Server endpoint ID -> client method(s) ("api.method"; top-level methods have no prefix).
    #: A test asserts that every built-in server route appears here, so a new route cannot
    #: silently lose its client.
    ENDPOINT_METHODS: ClassVar[dict[str, tuple[str, ...]]] = {
        "health": ("health",),
        "capabilities": ("discover",),
        "capabilities_check": ("check",),
        "list_commands": ("commands.list",),
        "run_command": ("commands.run",),
        "upload": ("files.upload_legacy",),
        "download": ("files.download_legacy",),
        "shell": ("process.shell",),
        "files_list": ("files.list",),
        "files_stat": ("files.stat", "files.exists"),
        "files_mkdir": ("files.mkdir",),
        "files_delete": ("files.delete",),
        "files_move": ("files.move",),
        "files_search": ("files.search",),
        "files_upload_stream": ("files.upload", "files.upload_file"),
        "files_download_stream": ("files.download", "files.read_text", "files.download_file"),
        "files_archive": ("files.archive",),
        "files_watch": ("files.watch", "files.watch_for"),
        "shell_stream": ("process.shell_stream", "process.run_stream"),
        "process_start": ("process.start",),
        "process_list": ("process.list",),
        "process_detail": ("process.get", "process.wait"),
        "process_signal": ("process.signal", "process.kill", "process.terminate"),
        "process_stdin": ("process.send_stdin", "process.close_stdin"),
        "process_output": ("process.output", "process.follow"),
        "pty_create_session": ("pty.create",),
        "pty_list_sessions": ("pty.list",),
        "pty_detail": ("pty.get",),
        "pty_resize": ("pty.resize",),
        "pty_delete_session": ("pty.delete",),
        "pty_connect": ("pty.connect",),
        "system_info": ("system.info",),
        "system_metrics": ("system.metrics",),
        "env_get": ("system.env",),
        "env_set": ("system.set_env",),
        "ports": ("system.ports",),
        "packages": ("system.packages",),
        "code_run": ("devtools.run_code",),
        "git_status": ("devtools.git_status",),
        "git_diff": ("devtools.git_diff",),
        "browser_navigate": ("browser.navigate",),
        "browser_screenshot": ("browser.screenshot",),
        "browser_content": ("browser.content",),
        "browser_click": ("browser.click",),
        "browser_type": ("browser.type",),
        "browser_evaluate": ("browser.evaluate",),
        "browser_pdf": ("browser.pdf",),
        "browser_console": ("browser.console",),
    }

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        headers: dict[str, str] | None = None,
        pty_url: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._token = token
        self._headers = dict(headers or {})
        self._pty_url = pty_url.rstrip("/") if pty_url else None
        self._http: httpx.AsyncClient | None = http_client
        self._http_loop: asyncio.AbstractEventLoop | None = None
        self._owns_http = http_client is None
        self._caps: ServerCapabilities | None = None

        self.files = ServerFilesApi(self)
        self.process = ServerProcessApi(self)
        self.pty = ServerPtyApi(self)
        self.system = ServerSystemApi(self)
        self.devtools = ServerDevtoolsApi(self)
        self.browser = ServerBrowserApi(self)
        self.commands = ServerCommandsApi(self)

    # -- configuration ---------------------------------------------------- #

    @property
    def capabilities(self) -> ServerCapabilities | None:
        """The snapshot from the last :meth:`discover` (``None`` until discovered)."""
        return self._caps

    @property
    def pty_url(self) -> str:
        """Base URL of the PTY WebSocket server (``ws://`` / ``wss://``)."""
        url = self._pty_url or self._derive_pty_url()
        parts = urlsplit(url)
        scheme = {"http": "ws", "https": "wss"}.get(parts.scheme, parts.scheme)
        return urlunsplit((scheme, parts.netloc, parts.path.rstrip("/"), "", ""))

    def _derive_pty_url(self) -> str:
        from agent_sandbox._provider_schema import resolve_provider_schema
        from agent_sandbox.utils.config_keys import BUILTIN_PROVIDER_ID

        builder = resolve_provider_schema(BUILTIN_PROVIDER_ID).legacy_pty_url_builder
        if builder is None:
            raise RuntimeError("Supply an explicit pty_url for this distribution.")
        return builder(self.base_url, DEFAULT_SERVER_PORT, DEFAULT_PTY_PORT)

    def auth_headers(self) -> dict[str, str]:
        """Headers sent on every request (gateway headers plus the server bearer token)."""
        headers = dict(self._headers)
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def with_token(self, token: str | None) -> ServerClient:
        """A new client for the same server using another token (own HTTP session)."""
        return ServerClient(
            self.base_url,
            token=token,
            headers=self._headers,
            pty_url=self._pty_url,
            timeout=self.timeout,
        )

    # -- lifecycle ------------------------------------------------------------ #

    def _client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        if self._http is not None and not self._owns_http:
            return self._http
        if self._http is None or self._http.is_closed or self._http_loop is not loop:
            self._http = httpx.AsyncClient(
                base_url=self.base_url, timeout=httpx.Timeout(self.timeout)
            )
            self._http_loop = loop
        return self._http

    async def aclose(self) -> None:
        """Close the HTTP session (a no-op for an injected ``http_client``)."""
        http, self._http = self._http, None
        if http is not None and self._owns_http and not http.is_closed:
            with contextlib.suppress(Exception):
                await http.aclose()

    async def __aenter__(self) -> ServerClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    # -- core transport ------------------------------------------------------ #

    def _precheck(self, endpoint: str) -> None:
        if self._caps is not None:
            self._caps.require(endpoint)

    def _headers_for(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = self.auth_headers()
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _parse_body(response: httpx.Response) -> Any:
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    def _raise_connection(self, exc: httpx.HTTPError) -> ConnectionError_:
        if isinstance(exc, httpx.TimeoutException):
            return ConnectionError_(
                f"Timed out talking to the sandbox server at {self.base_url}",
                suggestion="Check the server is running or raise ServerClient(timeout=...).",
            )
        return ConnectionError_(
            f"Could not reach the sandbox server at {self.base_url}: {exc}",
            suggestion="Is the server running? Try Sandbox.start_server().",
        )

    async def _request(
        self,
        endpoint: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float | None = None,
        precheck: bool = True,
    ) -> Any:
        if precheck:
            self._precheck(endpoint)
        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = httpx.Timeout(timeout)
        if json_body is not None:
            kwargs["json"] = json_body
        try:
            response = await self._client().request(
                method, path, params=params, headers=self._headers_for(), **kwargs
            )
        except httpx.HTTPError as exc:
            raise self._raise_connection(exc) from exc
        body = self._parse_body(response)
        if response.status_code >= 400:
            raise error_from_response(
                response.status_code,
                body,
                endpoint=endpoint,
                headers={k.lower(): v for k, v in response.headers.items()},
            )
        if not isinstance(body, dict):
            raise ServerAPIError(
                f"Sandbox server returned a non-JSON body (HTTP {response.status_code})",
                status_code=response.status_code,
                error_type="ProtocolError",
                endpoint=endpoint,
                suggestion="Is something other than the SandboxServer answering on this port?",
            )
        return body

    async def _stream(
        self,
        endpoint: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
        self._precheck(endpoint)
        kwargs: dict[str, Any] = {}
        if json_body is not None:
            kwargs["json"] = json_body
        # No read timeout between events; the server bounds the stream, *timeout* bounds the
        # connect/write phases and (loosely) the whole window.
        http_timeout = httpx.Timeout(timeout or self.timeout, read=timeout or None)
        try:
            async with self._client().stream(
                method,
                path,
                params=params,
                headers=self._headers_for({"Accept": "text/event-stream"}),
                timeout=http_timeout,
                **kwargs,
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise error_from_response(
                        response.status_code,
                        self._parse_body(response),
                        endpoint=endpoint,
                        headers={k.lower(): v for k, v in response.headers.items()},
                    )
                async for item in _iter_sse(response):
                    yield item
        except httpx.HTTPError as exc:
            raise self._raise_connection(exc) from exc

    # -- top-level endpoints ------------------------------------------------ #

    async def health(self) -> bool:
        """``GET /health`` (unauthenticated).  ``True`` when the server answers ``ok``."""
        try:
            data = await self._request("health", "GET", "/health", precheck=False)
        except (ConnectionError_, ServerAPIError):
            return False
        return bool(data.get("status") == "ok")

    async def discover(self) -> ServerCapabilities:
        """Fetch ``GET /capabilities`` and remember it for fail-fast pre-checks."""
        document = await self._request("capabilities", "GET", "/capabilities", precheck=False)
        caps = ServerCapabilities(document, self)
        self._caps = caps
        return caps

    def forget_discovery(self) -> None:
        """Drop the cached snapshot (calls go straight to the server again)."""
        self._caps = None

    async def check(
        self,
        endpoint: str,
        *,
        path: str | None = None,
        paths: list[str] | None = None,
        op: str | None = None,
    ) -> PathDecision:
        """Ask the server for its decision on a hypothetical call (``POST /capabilities/check``)."""
        body: dict[str, Any] = {"endpoint": endpoint}
        if path is not None:
            body["path"] = path
        if paths is not None:
            body["paths"] = list(paths)
        if op is not None:
            body["op"] = op
        data = await self._request(
            "capabilities_check", "POST", "/capabilities/check", json_body=body
        )
        return PathDecision.model_validate(data)

    health_sync = make_sync(health)
    discover_sync = make_sync(discover)
    check_sync = make_sync(check)
    aclose_sync = make_sync(aclose)

    def __repr__(self) -> str:
        return f"ServerClient({self.base_url!r})"


__all__ = [
    "DEFAULT_PTY_PORT",
    "DEFAULT_SERVER_PORT",
    "PtyConnection",
    "ServerBrowserApi",
    "ServerClient",
    "ServerCommandsApi",
    "ServerDevtoolsApi",
    "ServerFilesApi",
    "ServerProcessApi",
    "ServerPtyApi",
    "ServerSystemApi",
    "error_from_response",
]
