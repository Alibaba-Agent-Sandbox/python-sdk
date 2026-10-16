"""Standard-library-only task supervisor copied into an authorized Linux sandbox.

This program runs inside the sandbox, never on the MCP host. Its files last only
as long as that sandbox. It does not interpret caller-supplied process IDs.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

CAP = 1024 * 1024


def _root() -> Path:
    root = Path("/tmp") / f"abx-mcp-tasks-{os.getuid()}"
    root.mkdir(mode=0o700, exist_ok=True)
    if root.is_symlink() or root.stat().st_uid != os.getuid():
        raise RuntimeError("Invalid task storage")
    root.chmod(0o700)
    return root


def _directory(task_id: str) -> Path:
    if re.fullmatch(r"[0-9a-f]{32}", task_id) is None:
        raise ValueError("Invalid task ID")
    path = _root() / task_id
    if path.is_symlink():
        raise RuntimeError("Invalid task directory")
    return path


def _write(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    with os.fdopen(
        os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w"
    ) as out:
        json.dump(data, out)
    tmp.replace(path)


def _read_status(directory: Path) -> dict[str, Any]:
    with os.fdopen(os.open(directory / "status.json", os.O_RDONLY | os.O_NOFOLLOW), "r") as stream:
        result = json.loads(stream.read(4096))
    if not isinstance(result, dict):
        raise RuntimeError("Invalid task status")
    return result


def _identity(pid: int) -> str:
    try:
        # comm may contain spaces or parentheses; fields follow the final ')'.
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return ""


def _supervise(request: dict[str, Any]) -> None:
    os.umask(0o077)
    directory = _directory(request["task_id"])
    status: dict[str, Any] = {
        "state": "running",
        "exit_code": None,
        "started_at": time.time(),
        "finished_at": None,
        "stdout_truncated": False,
        "stderr_truncated": False,
        "supervisor_pid": os.getpid(),
        "supervisor_identity": _identity(os.getpid()),
    }
    child: subprocess.Popen[bytes] | None = None
    selector = selectors.DefaultSelector()
    streams: dict[str, Any] = {}
    sizes = {"stdout": 0, "stderr": 0}
    secret_values = sorted(
        {
            v.encode()
            for k, v in os.environ.items()
            if v
            and len(v) >= 4
            and any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
        },
        key=len,
        reverse=True,
    )
    # Retain only a suffix that could still become a secret in the next chunk.
    # Ordinary progress logs flush immediately, even during a quiet long task.
    pending = {"stdout": b"", "stderr": b""}

    def append(name: str, data: bytes, final: bool = False) -> None:
        data = pending[name] + data
        for secret in secret_values:
            data = data.replace(secret, b"[REDACTED]")
        hold = 0
        if not final:
            for secret in secret_values:
                for length in range(min(len(data), len(secret) - 1), hold, -1):
                    if data.endswith(secret[:length]):
                        hold = length
                        break
        cut = len(data) - hold
        pending[name] = data[cut:]
        data = data[:cut]
        remaining = max(0, CAP - sizes[name])
        streams[name].write(data[:remaining])
        streams[name].flush()
        sizes[name] += min(len(data), remaining)
        if len(data) > remaining:
            status[name + "_truncated"] = True

    try:
        for name in sizes:
            streams[name] = os.fdopen(
                os.open(
                    directory / (name + ".log"),
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
                    0o600,
                ),
                "wb",
            )
        _write(directory / "status.json", status)
        child = subprocess.Popen(
            ["sh", "-c", request["command"]],
            cwd=request.get("cwd") or None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        for name in sizes:
            pipe = getattr(child, name)
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
        deadline = time.monotonic() + request["timeout"]
        reason = None
        term_at = None
        drained_until = None
        while True:
            for key, _ in selector.select(0.05):
                data = os.read(key.fd, 65536)
                if data:
                    append(key.data, data)
                else:
                    selector.unregister(key.fileobj)
            # WNOWAIT retains the child/session leader identity until group kill.
            exited = (
                True
                if drained_until is not None
                else os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            )
            now = time.monotonic()
            if exited is not None:
                if drained_until is None:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                    drained_until = now + 1
                if not selector.get_map() or now >= drained_until:
                    break
            elif reason is None and ((directory / "cancel").exists() or now >= deadline):
                reason = "cancelled" if (directory / "cancel").exists() else "timed_out"
                term_at = now
                os.killpg(child.pid, signal.SIGTERM)
            elif term_at is not None and now - term_at >= 0.25:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(child.pid, signal.SIGKILL)
        for name in sizes:
            append(name, b"", final=True)
        status.update(
            state=reason or ("succeeded" if child.returncode == 0 else "failed"),
            exit_code=child.returncode,
        )
    except BaseException:
        if child is not None and child.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        status.update(state="failed", exit_code=None)
    finally:
        selector.close()
        if child is not None:
            for pipe in (child.stdout, child.stderr):
                if pipe is not None:
                    pipe.close()
        for stream in streams.values():
            stream.close()
        status["finished_at"] = time.time()
        _write(directory / "status.json", status)


def _launch(request: dict[str, Any]) -> dict[str, Any]:
    os.umask(0o077)
    root = _root()
    if sum(p.is_dir() for p in root.iterdir()) >= 128:
        raise RuntimeError("Task capacity reached")
    directory = _directory(request["task_id"])
    directory.mkdir(mode=0o700)
    runtime = directory / "runtime.py"
    # The caller sends this module's source via python -c; it supplies the same
    # source to launch the detached supervisor without a package dependency.
    runtime.write_text(request.pop("runtime"), encoding="utf-8")
    subprocess.Popen(
        [sys.executable, str(runtime), json.dumps({**request, "action": "supervise"})],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 3
    while not (directory / "status.json").exists():
        if time.monotonic() >= deadline:
            return {"task_id": request["task_id"], "state": "unknown"}
        time.sleep(0.02)
    status = _read_status(directory)
    return {"task_id": request["task_id"], "state": status["state"]}


def _inspect(request: dict[str, Any]) -> dict[str, Any]:
    directory = _directory(request["task_id"])
    status = _read_status(directory)
    if status["state"] == "running" and (
        not status["supervisor_identity"]
        or _identity(status["supervisor_pid"]) != status["supervisor_identity"]
    ):
        status["state"] = "unknown"
    result = {k: v for k, v in status.items() if not k.startswith("supervisor_")}
    result["task_id"] = request["task_id"]
    for name in ("stdout", "stderr"):
        offset = request.get(name + "_offset", 0)
        path = directory / (name + ".log")
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
            stream.seek(offset)
            data = stream.read(request.get("limit", 16384))
            size = os.fstat(stream.fileno()).st_size
        result[name] = data.decode("utf-8", errors="replace")
        result[name + "_offset"] = offset + len(data)
        result[name + "_size"] = size
    return result


def _cancel(request: dict[str, Any]) -> dict[str, Any]:
    directory = _directory(request["task_id"])
    result = _inspect(request)
    if result["state"] != "running":
        return result
    fd = os.open(directory / "cancel", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    deadline = time.monotonic() + 3
    while result["state"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        result = _inspect(request)
    return result


if __name__ == "__main__":
    try:
        _request = json.loads(sys.argv[1])
        _action = _request["action"]
        if _action == "supervise":
            _supervise(_request)
        else:
            _handler = {"start": _launch, "get": _inspect, "cancel": _cancel}[_action]
            print(json.dumps(_handler(_request)))
    except Exception:
        # Never echo commands, paths, provider credentials or raw exceptions.
        print(json.dumps({"error": "Task operation failed; check task/sandbox availability."}))
        raise SystemExit(1) from None
