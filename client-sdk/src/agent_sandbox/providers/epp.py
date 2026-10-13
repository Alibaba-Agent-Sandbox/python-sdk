"""EPP/1 client: JSON-RPC 2.0 over a plugin's stdin/stdout (NDJSON), plus error mapping."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import signal
import sys
from collections import deque
from typing import TYPE_CHECKING, Any

from agent_sandbox.models import errors as E  # noqa: N812
from agent_sandbox.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

logger = get_logger("providers.epp")

PROTOCOL = "epp/1"
MAX_LINE_BYTES = 8 * 1024 * 1024
STDERR_RING_BYTES = 64 * 1024

_ENV_ALLOW = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "SYSTEMROOT",
    "COMSPEC",
    "ComSpec",
)
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


# ------------------------------------------------------------------ errors

#: sdk_code -> exception class (codes a plugin may name in ``error.data.sdk_code``).
_SDK_CODE_CLASSES: dict[str, type[E.SandboxError]] = {
    cls.code: cls
    for cls in (
        E.InvalidAPIKeyError,
        E.TokenExpiredError,
        E.InvalidCredentialsError,
        E.TokenExchangeError,
        E.TemplateNotFoundError,
        E.SandboxNotFoundError,
        E.QuotaExceededError,
        E.RegionUnavailableError,
        E.CommandTimeoutError,
        E.FileNotFoundError_,
        E.PermissionDeniedError,
        E.NetworkError,
        E.ConnectionError_,
    )
}


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _flatten(value: object) -> str:
    return _CTRL.sub("", _ANSI.sub("", str(value)))


def sanitize_text(text: str, secrets: Sequence[str] = ()) -> str:
    """Strip ANSI/control characters and redact *secrets* from plugin-supplied text."""
    out = _ANSI.sub("", text)
    for secret in secrets:
        if secret and len(secret) >= 4:
            out = out.replace(secret, "***")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", out)


def map_error(
    err: Mapping[str, Any], provider_id: str, secrets: Sequence[str] = ()
) -> E.SandboxError:
    """Map a JSON-RPC ``error`` object to the SDK exception hierarchy (design §7.4)."""
    code = err.get("code")
    message = sanitize_text(_flatten(err.get("message", "provider error")), secrets)
    data = _as_dict(err.get("data"))
    sdk_code = data.get("sdk_code") if isinstance(data.get("sdk_code"), str) else None
    suggestion = (
        sanitize_text(_flatten(data["suggestion"]), secrets) if data.get("suggestion") else None
    )
    kwargs: dict[str, Any] = {}
    if suggestion:
        kwargs["suggestion"] = suggestion

    def by_sdk_code(default: type[E.SandboxError]) -> E.SandboxError:
        cls = _SDK_CODE_CLASSES.get(sdk_code or "", default)
        if cls is E.CommandTimeoutError:
            return E.CommandTimeoutError(message, **kwargs)
        return cls(message, **kwargs)

    if code == -32001:
        return by_sdk_code(E.AuthenticationError)
    if code == -32002:
        if sdk_code in _SDK_CODE_CLASSES:
            return by_sdk_code(E.ProviderResourceNotFoundError)
        return E.ProviderResourceNotFoundError(message, **kwargs)
    if code == -32003:
        details = _as_dict(data.get("details"))
        feature = str(details.get("feature") or data.get("feature") or "unknown")
        return E.ProviderFeatureNotSupportedError(provider_id, feature, message=message, **kwargs)
    if code == -32004:
        return E.QuotaExceededError(message, **kwargs)
    if code == -32005:
        return E.ProviderTimeoutError(message, **kwargs)
    if code == -32006:
        return E.ProviderConfigError(message, **kwargs)
    if code == -32000:
        if sdk_code in _SDK_CODE_CLASSES:
            return by_sdk_code(E.ProviderError)
        return E.ProviderError(message, **kwargs)
    exc = E.ProviderProtocolError(message, **kwargs)
    exc.rpc_code = code  # type: ignore[attr-defined]
    return exc


def is_method_not_found(exc: BaseException) -> bool:
    """True for a ``-32601`` answer: the plugin does not implement the (optional) method."""
    return getattr(exc, "rpc_code", None) == -32601


def exit_code_for(exc: BaseException) -> int:
    """CLI exit code (0-6) for an SDK exception, extended with the E8xxx classes."""
    if isinstance(exc, E.AuthenticationError):
        return 3
    if isinstance(
        exc,
        (
            E.TemplateNotFoundError,
            E.SandboxNotFoundError,
            E.FileNotFoundError_,
            E.ProviderNotFoundError,
            E.ProviderResourceNotFoundError,
        ),
    ):
        return 4
    if isinstance(exc, (E.CommandTimeoutError, E.ProviderTimeoutError)):
        return 5
    if isinstance(exc, E.QuotaExceededError):
        return 6
    if isinstance(
        exc,
        (E.ProviderConfigError, E.ProviderTrustError, E.ProviderMismatchError),
    ):
        return 2
    return 1


# ------------------------------------------------------------------ client


def scrubbed_env(
    data_dir: Path, passthrough: Sequence[str] = (), environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The only environment a plugin process gets (design §8.3)."""
    src = os.environ if environ is None else environ
    env: dict[str, str] = {}
    for name in (*_ENV_ALLOW, *passthrough):
        if name in src:
            env[name] = src[name]
    for name, value in src.items():
        if name.startswith("LC_"):
            env[name] = value
    env["ABX_PROVIDER_DATA_DIR"] = str(data_dir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def resolve_command(command: Sequence[str], plugin_root: Path) -> list[str]:
    """Resolve ``./``-prefixed argv elements inside the plugin directory (no escape)."""
    root = plugin_root.resolve()
    argv: list[str] = []
    for item in command:
        if item.startswith(("./", ".\\")):
            resolved = (root / item).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                raise E.ProviderManifestError(
                    f"Invalid abx-provider.toml: '{item}' escapes the plugin directory."
                ) from None
            argv.append(str(resolved))
        else:
            argv.append(item)
    return argv


class EppClient:
    """One plugin process speaking EPP/1. Create with :meth:`start`; always :meth:`close`."""

    def __init__(
        self,
        provider_id: str,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        startup_timeout: float = 10.0,
        call_timeout: float = 60.0,
        secrets: Sequence[str] = (),
    ) -> None:
        self.provider_id = provider_id
        self._argv = list(argv)
        self._cwd = cwd
        self._env = dict(env)
        self._startup_timeout = startup_timeout
        self._call_timeout = call_timeout
        self._secrets = [s for s in secrets if s]
        self._proc: asyncio.subprocess.Process | None = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr: deque[bytes] = deque()
        self._stderr_size = 0
        self._queues: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}
        self._early: dict[str, list[dict[str, Any]]] = {}
        self._failure: E.SandboxError | None = None
        self._closed = False
        self.plugin_info: dict[str, Any] = {}
        self.features: frozenset[str] = frozenset()

    # -- lifecycle

    @property
    def stderr_tail(self) -> str:
        raw = b"".join(self._stderr).decode("utf-8", "replace")
        return sanitize_text(raw, self._secrets).strip()

    async def start(self, init_params: Mapping[str, Any]) -> dict[str, Any]:
        """Spawn the plugin and perform ``initialize``; returns its result."""
        kwargs: dict[str, Any] = {}
        if sys.platform == "win32":  # pragma: no cover - Windows only
            import subprocess

            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
        else:
            kwargs["start_new_session"] = True
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._cwd),
                env=self._env,
                limit=MAX_LINE_BYTES + 1,
                **kwargs,
            )
        except (OSError, ValueError) as exc:
            raise E.ProviderProcessError(
                f"Cannot start provider '{self.provider_id}': {sanitize_text(str(exc))}.",
                suggestion=f"Run 'abx provider doctor {self.provider_id}'.",
            ) from exc
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())
        try:
            result = await self.call(
                "initialize", dict(init_params), timeout=self._startup_timeout, _startup=True
            )
        except E.ProviderTimeoutError:
            await self.close()
            raise E.ProviderTimeoutError(
                f"Provider '{self.provider_id}' did not initialize within "
                f"{self._startup_timeout:g}s.",
                suggestion=self._with_tail(),
            ) from None
        except BaseException:
            await self.close()
            raise
        if not isinstance(result, dict) or result.get("protocol") != PROTOCOL:
            await self.close()
            answered = result.get("protocol") if isinstance(result, dict) else None
            raise E.ProviderVersionError(
                f"Provider '{self.provider_id}' answered protocol '{answered}', "
                f"expected '{PROTOCOL}'."
            )
        self.plugin_info = dict(result.get("plugin") or {})
        feats = result.get("features")
        self.features = (
            frozenset(f for f in feats if isinstance(f, str))
            if isinstance(feats, list)
            else frozenset()
        )
        return result

    def _with_tail(self) -> str:
        tail = self.stderr_tail
        return f"Plugin stderr: {tail[-500:]}" if tail else ""

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        proc = self._proc
        if proc is not None and proc.returncode is None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._notify_request("shutdown"), 2.0)
            with contextlib.suppress(Exception):
                if proc.stdin is not None:
                    proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), 3.0)
            except asyncio.TimeoutError:
                self._signal(signal.SIGTERM if sys.platform != "win32" else None)
                try:
                    await asyncio.wait_for(proc.wait(), 3.0)
                except asyncio.TimeoutError:
                    self._signal(None, kill=True)
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(proc.wait(), 3.0)
        self._reap_group()
        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._fail_all(E.ProviderProcessError(f"Provider '{self.provider_id}' was closed."))

    def _reap_group(self) -> None:
        """Kill children the plugin left behind (POSIX: the plugin leads its own session)."""
        proc = self._proc
        if proc is None or sys.platform == "win32":
            return
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.killpg(proc.pid, signal.SIGKILL)

    def _signal(self, sig: int | None, *, kill: bool = False) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        try:
            if sys.platform == "win32":  # pragma: no cover - Windows only
                import subprocess

                subprocess.run(  # noqa: S603
                    ["taskkill", "/T", "/F", "/PID", str(proc.pid)],  # noqa: S607
                    capture_output=True,
                    check=False,
                )
            else:
                os.killpg(proc.pid, signal.SIGKILL if kill else (sig or signal.SIGTERM))
        except (ProcessLookupError, PermissionError, OSError):
            with contextlib.suppress(Exception):
                proc.kill() if kill else proc.terminate()

    async def _notify_request(self, method: str) -> None:
        await self.call(method, {}, timeout=2.0)

    # -- I/O

    async def _stderr_loop(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        try:
            while True:
                chunk = await self._proc.stderr.read(4096)
                if not chunk:
                    return
                self._stderr.append(chunk)
                self._stderr_size += len(chunk)
                while self._stderr_size > STDERR_RING_BYTES and self._stderr:
                    self._stderr_size -= len(self._stderr.popleft())
        except Exception:  # pragma: no cover - defensive
            return

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        stdout = self._proc.stdout
        try:
            while True:
                try:
                    line = await stdout.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    self._violation("Plugin sent a protocol line larger than 8 MiB.")
                    return
                if not line:
                    break
                if len(line) > MAX_LINE_BYTES:
                    self._violation("Plugin sent a protocol line larger than 8 MiB.")
                    return
                text = line.strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except ValueError:
                    self._violation("Plugin sent a malformed (non-JSON) protocol line.")
                    return
                if not isinstance(msg, dict):
                    self._violation("Plugin sent a protocol line that is not a JSON object.")
                    return
                self._dispatch(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            self._violation(f"Plugin I/O failed: {exc}")
            return
        rc = await self._proc.wait()
        self._fail_all(
            E.ProviderProcessError(
                f"Provider '{self.provider_id}' exited unexpectedly (code {rc}).",
                suggestion=self._with_tail(),
            ),
            end_streams=True,
        )

    def _violation(self, message: str) -> None:
        self._signal(None, kill=True)
        self._fail_all(
            E.ProviderProtocolError(
                f"Provider '{self.provider_id}': {message}", suggestion=self._with_tail()
            ),
            end_streams=True,
        )

    def _fail_all(self, exc: E.SandboxError, *, end_streams: bool = False) -> None:
        if self._failure is None:
            self._failure = exc
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()
        if end_streams:
            for q in self._queues.values():
                q.put_nowait(None)

    def _dispatch(self, msg: dict[str, Any]) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.pop(msg["id"], None) if isinstance(msg["id"], int) else None
            if fut is None or fut.done():
                return
            if "error" in msg and isinstance(msg["error"], dict):
                fut.set_exception(map_error(msg["error"], self.provider_id, self._secrets))
            else:
                fut.set_result(msg.get("result"))
            return
        method = msg.get("method")
        params = _as_dict(msg.get("params"))
        if method == "log":
            logger.debug(
                "[%s] %s",
                self.provider_id,
                sanitize_text(str(params.get("message", "")), self._secrets),
            )
            return
        pid = params.get("process_id")
        if isinstance(method, str) and pid is not None:
            key = str(pid)
            note = {"method": method, **params}
            queue = self._queues.get(key)
            if queue is None:
                self._early.setdefault(key, []).append(note)
            else:
                queue.put_nowait(note)

    # -- API

    async def call(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
        _startup: bool = False,
    ) -> Any:
        """Send a request and await its result (errors are mapped to SDK exceptions)."""
        if self._failure is not None:
            raise self._failure
        proc = self._proc
        if proc is None or proc.stdin is None or proc.returncode is not None:
            raise E.ProviderProcessError(f"Provider '{self.provider_id}' is not running.")
        self._next_id += 1
        rid = self._next_id
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": rid, "method": method, "params": dict(params or {})}
        )
        try:
            proc.stdin.write(payload.encode("utf-8") + b"\n")
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            self._pending.pop(rid, None)
            raise E.ProviderProcessError(
                f"Provider '{self.provider_id}' closed its input.", suggestion=self._with_tail()
            ) from exc
        limit = timeout if timeout is not None else self._call_timeout
        try:
            return await asyncio.wait_for(fut, limit)
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            if not _startup:
                with contextlib.suppress(Exception):
                    proc.stdin.write(
                        json.dumps(
                            {"jsonrpc": "2.0", "method": "$/cancel", "params": {"id": rid}}
                        ).encode()
                        + b"\n"
                    )
            raise E.ProviderTimeoutError(
                f"Provider '{self.provider_id}' did not answer '{method}' within {limit:g}s.",
                suggestion=self._with_tail(),
            ) from None

    def open_stream(self, process_id: str) -> asyncio.Queue[dict[str, Any] | None]:
        """Register a notification queue for a process id (drains early notifications)."""
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._queues[process_id] = queue
        for note in self._early.pop(process_id, []):
            queue.put_nowait(note)
        if self._failure is not None:
            queue.put_nowait(None)
        return queue

    def close_stream(self, process_id: str) -> None:
        self._queues.pop(process_id, None)

    @property
    def failure(self) -> E.SandboxError | None:
        return self._failure
