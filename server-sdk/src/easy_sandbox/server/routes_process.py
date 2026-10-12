"""Process management and streaming shell endpoints.

Provides:
- Streaming shell execution via SSE (``POST /shell/stream``)
- Background process start (``POST /process/start``)
- Process listing (``GET /process/list``)
- Process detail (``GET /process/{pid}``)
- Signal delivery (``POST /process/{pid}/signal``)

All routes are registered under :data:`CapabilityGroup.PROCESS`.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import os
import queue
import shlex
import subprocess
import threading
import time
from typing import Any

from .policy import PolicyDenied
from .router import CapabilityGroup, default_table
from .routes import enforce_exec_policy
from .runtime import context_of
from .types import ServerRequest, ServerResponse, SSEResponse

__all__: list[str] = []

# ---------------------------------------------------------------------------
# Internal process bookkeeping
# ---------------------------------------------------------------------------

_MAX_PROCESSES = 100

_ALLOWED_SIGNALS: frozenset[int] = frozenset({2, 9, 15, 18, 20})


@dataclasses.dataclass
class _ProcessInfo:
    """Metadata about a background process managed by the server."""

    pid: int
    popen: subprocess.Popen[bytes]
    command: str
    started_at: float
    capture: _Capture | None = None
    stdin_open: bool = False


class _Capture:
    """Bounded, cursor-addressable log of a process's stdout/stderr chunks."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self.cond = threading.Condition()
        self.events: list[tuple[int, str, str]] = []
        self.size = 0
        self.next_seq = 0
        self.dropped = False
        self.readers = 0

    def add(self, stream: str, text: str) -> None:
        with self.cond:
            self.events.append((self.next_seq, stream, text))
            self.next_seq += 1
            self.size += len(text)
            while self.size > self.max_bytes and len(self.events) > 1:
                _seq, _stream, old = self.events.pop(0)
                self.size -= len(old)
                self.dropped = True
            self.cond.notify_all()


_DEFAULT_CAPTURE_BYTES = 1024 * 1024


_process_table: dict[int, _ProcessInfo] = {}
_process_lock = threading.Lock()


def _poll_process(info: _ProcessInfo) -> str:
    """Return ``"running"`` or ``"exited"`` after polling the process."""
    if info.popen.poll() is None:
        return "running"
    return "exited"


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_shell_stream(request: ServerRequest) -> SSEResponse | ServerResponse:
    """``POST /shell/stream`` — execute a command and stream output via SSE."""
    body = request.body or {}
    command = body.get("command")
    if not command or not isinstance(command, str):
        return ServerResponse.error(400, "Missing or invalid 'command'", "ValueError")

    try:
        args = shlex.split(command)
    except ValueError as exc:
        return ServerResponse.error(400, f"Invalid command: {exc}", "ValueError")

    ctx = context_of(request)
    try:
        cwd, timeout, env = enforce_exec_policy(ctx, args, body)
    except ValueError as exc:
        return ServerResponse.error(400, str(exc), "ValueError")
    out_limit = ctx.limit("max_output_bytes") if ctx else None

    def event_gen() -> Any:
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=env,
                shell=False,
            )
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            return

        start = time.monotonic()
        emitted = 0

        # Use a thread-safe queue to merge stdout and stderr concurrently.
        q: queue.Queue[tuple[str, str | None]] = queue.Queue()

        def _reader(stream: Any, event_name: str) -> None:
            """Read lines from *stream* and push them onto the queue."""
            try:
                for raw_line in stream:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                    q.put((event_name, line))
            except Exception:
                pass
            finally:
                q.put((event_name, None))  # sentinel

        stdout_thread = threading.Thread(
            target=_reader,
            args=(proc.stdout, "stdout"),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_reader,
            args=(proc.stderr, "stderr"),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        finished_streams = 0
        while finished_streams < 2:
            if time.monotonic() - start > timeout:
                proc.kill()
                yield f"event: error\ndata: {json.dumps({'error': 'timeout'})}\n\n"
                proc.wait()
                yield f"event: exit\ndata: {json.dumps({'exit_code': proc.returncode})}\n\n"
                return
            try:
                event_name, line = q.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                finished_streams += 1
                continue
            emitted += len(line) + 1
            if out_limit is not None and emitted > int(out_limit):
                proc.kill()
                yield f"event: error\ndata: {json.dumps({'error': 'output_limit'})}\n\n"
                proc.wait()
                yield f"event: exit\ndata: {json.dumps({'exit_code': proc.returncode})}\n\n"
                return
            yield f"event: {event_name}\ndata: {json.dumps({'data': line})}\n\n"

        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        proc.wait()
        yield f"event: exit\ndata: {json.dumps({'exit_code': proc.returncode})}\n\n"

    return SSEResponse(event_iterator=event_gen())


def _handle_process_start(request: ServerRequest) -> ServerResponse:
    """``POST /process/start`` — start a background process."""
    body = request.body or {}
    command = body.get("command")
    if not command or not isinstance(command, str):
        return ServerResponse.error(400, "Missing or invalid 'command'", "ValueError")

    ctx = context_of(request)
    max_processes = int(ctx.limit("max_processes", _MAX_PROCESSES)) if ctx else _MAX_PROCESSES
    max_processes = min(max_processes, _MAX_PROCESSES)
    with _process_lock:
        # Lazily clean up already-exited processes before checking the limit.
        exited = [pid for pid, info in _process_table.items() if info.popen.poll() is not None]
        for pid in exited:
            _process_table.pop(pid, None)

        if len(_process_table) >= max_processes:
            return ServerResponse.error(
                429,
                f"Process limit reached ({max_processes})",
                "ResourceError",
            )

    try:
        args = shlex.split(command)
    except ValueError as exc:
        return ServerResponse.error(400, f"Invalid command: {exc}", "ValueError")

    try:
        cwd, _timeout, env = enforce_exec_policy(ctx, args, body)
    except ValueError as exc:
        return ServerResponse.error(400, str(exc), "ValueError")

    capture_output = bool(body.get("capture_output", False))
    want_stdin = bool(body.get("stdin", False))
    capture_limit = (
        int(ctx.limit("max_output_bytes", _DEFAULT_CAPTURE_BYTES))
        if ctx
        else _DEFAULT_CAPTURE_BYTES
    )

    try:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if want_stdin else None,
            stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
            stderr=subprocess.PIPE if capture_output else subprocess.DEVNULL,
            cwd=cwd,
            env=env,
            shell=False,
            bufsize=0,
        )
    except Exception as exc:
        return ServerResponse.error(500, str(exc), type(exc).__name__)

    info = _ProcessInfo(
        pid=proc.pid,
        popen=proc,
        command=command,
        started_at=time.time(),
        stdin_open=want_stdin,
    )
    if capture_output:
        info.capture = _Capture(capture_limit)
        info.capture.readers = 2
        for stream, name in ((proc.stdout, "stdout"), (proc.stderr, "stderr")):
            threading.Thread(target=_pump, args=(stream, name, info.capture), daemon=True).start()
    with _process_lock:
        _process_table[proc.pid] = info

    return ServerResponse.ok({"pid": proc.pid, "command": command})


def _pump(stream: Any, name: str, capture: _Capture) -> None:
    """Copy *stream* into *capture* until EOF."""
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            capture.add(name, chunk.decode("utf-8", errors="replace"))
    except (OSError, ValueError):
        pass
    finally:
        with capture.cond:
            capture.readers -= 1
            capture.cond.notify_all()


def _handle_process_list(request: ServerRequest) -> ServerResponse:
    """``GET /process/list`` — list managed background processes."""
    processes: list[dict[str, Any]] = []
    with _process_lock:
        # Clean up exited processes while holding the lock.
        exited = [pid for pid, info in _process_table.items() if info.popen.poll() is not None]
        for pid in exited:
            _process_table.pop(pid, None)
        snapshot = list(_process_table.values())
    for info in snapshot:
        state = _poll_process(info)
        processes.append(
            {
                "pid": info.pid,
                "command": info.command,
                "state": state,
                "started_at": info.started_at,
            }
        )
    return ServerResponse.ok({"processes": processes})


def _handle_process_detail(request: ServerRequest) -> ServerResponse:
    """``GET /process/{pid}`` — get details of a single managed process."""
    raw_pid = request.path_params.get("pid", "")
    try:
        pid = int(raw_pid)
    except (ValueError, TypeError):
        return ServerResponse.error(400, f"Invalid pid: {raw_pid!r}", "ValueError")

    with _process_lock:
        info = _process_table.get(pid)
    if info is None:
        return ServerResponse.error(404, f"Process {pid} not found", "NotFoundError")

    state = _poll_process(info)
    result: dict[str, Any] = {
        "pid": info.pid,
        "command": info.command,
        "state": state,
        "started_at": info.started_at,
    }
    if state == "exited":
        result["exit_code"] = info.popen.returncode
    else:
        result["exit_code"] = None
    return ServerResponse.ok(result)


def _handle_process_signal(request: ServerRequest) -> ServerResponse:
    """``POST /process/{pid}/signal`` — send a signal to a managed process."""
    raw_pid = request.path_params.get("pid", "")
    try:
        pid = int(raw_pid)
    except (ValueError, TypeError):
        return ServerResponse.error(400, f"Invalid pid: {raw_pid!r}", "ValueError")

    body = request.body or {}
    sig = body.get("signal")
    if sig is None:
        return ServerResponse.error(400, "Missing 'signal' in body", "ValueError")

    try:
        sig = int(sig)
    except (ValueError, TypeError):
        return ServerResponse.error(400, f"Invalid signal value: {sig!r}", "ValueError")

    if sig not in _ALLOWED_SIGNALS:
        return ServerResponse.error(
            400,
            f"Signal {sig} not allowed; permitted: {sorted(_ALLOWED_SIGNALS)}",
            "ValueError",
        )
    ctx = context_of(request)
    if ctx is not None:
        allowed = ctx.param("allowed_signals")
        if allowed is not None and sig not in allowed:
            raise PolicyDenied("signal_not_allowed", f"Signal {sig} is not permitted by policy")

    # Safety: refuse to kill PID 1 or own process.
    if pid == 1 or pid == os.getpid():
        return ServerResponse.error(403, f"Refusing to signal pid {pid}", "PermissionError")

    with _process_lock:
        info = _process_table.get(pid)
    if info is None:
        return ServerResponse.error(404, f"Process {pid} not found", "NotFoundError")

    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return ServerResponse.error(404, f"Process {pid} not found (os)", "NotFoundError")
    except PermissionError as exc:
        return ServerResponse.error(403, str(exc), "PermissionError")
    except Exception as exc:
        return ServerResponse.error(500, str(exc), type(exc).__name__)

    return ServerResponse.ok({"pid": pid, "signal": sig})


def _parse_pid(request: ServerRequest) -> int | ServerResponse:
    raw_pid = request.path_params.get("pid", "")
    try:
        return int(raw_pid)
    except (ValueError, TypeError):
        return ServerResponse.error(400, f"Invalid pid: {raw_pid!r}", "ValueError")


def _handle_process_stdin(request: ServerRequest) -> ServerResponse:
    """``POST /process/{pid}/stdin`` — write to (or close) a process started with ``stdin``."""
    pid = _parse_pid(request)
    if isinstance(pid, ServerResponse):
        return pid
    body = request.body or {}
    with _process_lock:
        info = _process_table.get(pid)
    if info is None:
        return ServerResponse.error(404, f"Process {pid} not found", "NotFoundError")
    stdin = info.popen.stdin
    if stdin is None or not info.stdin_open:
        return ServerResponse.error(
            409, f"Process {pid} was not started with stdin enabled", "ConflictError"
        )
    data: bytes = b""
    if "data_base64" in body:
        try:
            data = base64.b64decode(str(body["data_base64"]), validate=True)
        except Exception as exc:
            return ServerResponse.error(400, f"Invalid base64: {exc}", "ValueError")
    elif "data" in body:
        if not isinstance(body["data"], str):
            return ServerResponse.error(400, "'data' must be a string", "ValueError")
        data = body["data"].encode("utf-8")
    eof = bool(body.get("eof", False))
    if not data and not eof:
        return ServerResponse.error(400, "Provide 'data', 'data_base64' or 'eof'", "ValueError")
    try:
        if data:
            stdin.write(data)
            stdin.flush()
        if eof:
            stdin.close()
            info.stdin_open = False
    except (BrokenPipeError, OSError, ValueError) as exc:
        return ServerResponse.error(409, f"stdin closed: {exc}", "ConflictError")
    return ServerResponse.ok({"pid": pid, "written": len(data), "closed": eof})


def _handle_process_output(request: ServerRequest) -> ServerResponse:
    """``GET /process/{pid}/output?since=<seq>&wait=<seconds>`` — read captured output."""
    pid = _parse_pid(request)
    if isinstance(pid, ServerResponse):
        return pid
    with _process_lock:
        info = _process_table.get(pid)
    if info is None:
        return ServerResponse.error(404, f"Process {pid} not found", "NotFoundError")
    capture = info.capture
    if capture is None:
        return ServerResponse.error(
            409,
            f"Process {pid} was started without capture_output",
            "ConflictError",
        )
    try:
        since = max(0, int(request.query.get("since", ["0"])[0]))
        wait = min(30.0, max(0.0, float(request.query.get("wait", ["0"])[0])))
    except ValueError:
        return ServerResponse.error(400, "Invalid 'since' or 'wait'", "ValueError")
    deadline = time.monotonic() + wait
    with capture.cond:
        while capture.next_seq <= since and (info.popen.poll() is None or capture.readers > 0):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            capture.cond.wait(timeout=min(remaining, 0.25))
        events = [
            {"seq": seq, "stream": stream, "data": text}
            for seq, stream, text in capture.events
            if seq >= since
        ]
        next_seq = capture.next_seq
        dropped = capture.dropped
    state = _poll_process(info)
    return ServerResponse.ok(
        {
            "pid": pid,
            "events": events,
            "next": next_seq,
            "state": state,
            "exit_code": info.popen.returncode if state == "exited" else None,
            "dropped": dropped,
        }
    )


# ---------------------------------------------------------------------------
# Route registration (import side-effect)
# ---------------------------------------------------------------------------

_table = default_table()
_table.register(
    "POST",
    "/shell/stream",
    _handle_shell_stream,
    group=CapabilityGroup.PROCESS,
    streaming=True,
    name="shell_stream",
)
_table.register(
    "POST",
    "/process/start",
    _handle_process_start,
    group=CapabilityGroup.PROCESS,
    name="process_start",
)
_table.register(
    "GET",
    "/process/list",
    _handle_process_list,
    group=CapabilityGroup.PROCESS,
    name="process_list",
)
_table.register(
    "GET",
    "/process/{pid}",
    _handle_process_detail,
    group=CapabilityGroup.PROCESS,
    name="process_detail",
)
_table.register(
    "POST",
    "/process/{pid}/signal",
    _handle_process_signal,
    group=CapabilityGroup.PROCESS,
    name="process_signal",
)
_table.register(
    "POST",
    "/process/{pid}/stdin",
    _handle_process_stdin,
    group=CapabilityGroup.PROCESS,
    name="process_stdin",
)
_table.register(
    "GET",
    "/process/{pid}/output",
    _handle_process_output,
    group=CapabilityGroup.PROCESS,
    name="process_output",
)
