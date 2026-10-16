"""Client of the local provider engine (``abx provider engine serve``, protocol ``abx-engine/1``).

The engine is a Node process that hosts the provider layer for every SDK and the CLI.
This module finds it through ``~/.abx/engine.json``, starts it when none is running, and
speaks its HTTP, SSE and WebSocket routes. Which account a call belongs to travels with
each request (the *connection*), so the engine never guesses.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import shlex
import shutil
import subprocess  # nosec B404 - audited argv-only subprocess boundary; no shell
import time
import weakref
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from agent_sandbox.models import errors as _errors
from agent_sandbox.models.errors import ProviderProtocolError, SandboxError
from agent_sandbox.transport import config as _config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

PROTOCOL = "abx-engine/1"
_ENV_BIN = "ABX_BIN"
_START_TIMEOUT = 30.0


@dataclass(frozen=True)
class EngineRecord:
    pid: int
    host: str
    port: int
    token: str
    version: str = ""

    @property
    def base(self) -> str:
        return f"http://{self.host}:{self.port}"


def abx_dir() -> Path:
    return _config._CONFIG_FILE.parent


def read_record() -> EngineRecord | None:
    try:
        data = json.loads((abx_dir() / "engine.json").read_text(encoding="utf-8"))
        if data.get("protocol") != PROTOCOL:
            return None
        return EngineRecord(
            pid=int(data["pid"]),
            host=str(data.get("host", "127.0.0.1")),
            port=int(data["port"]),
            token=str(data["token"]),
            version=str(data.get("version", "")),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def abx_command() -> list[str]:
    """The ``abx`` launcher: ``ABX_BIN`` (may include arguments), else ``abx`` on ``PATH``."""
    override = os.environ.get(_ENV_BIN, "").strip()
    if override:
        return shlex.split(override)
    found = shutil.which("abx")
    if found:
        return [found]
    raise ProviderProtocolError(
        "The provider engine needs the abx CLI, and it was not found.",
        suggestion=(
            "Install it with 'npm install -g @agent-sandbox/cli', or set ABX_BIN to its path."
        ),
    )


async def _healthy(record: EngineRecord) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(
                f"{record.base}/v1/health", headers={"Authorization": f"Bearer {record.token}"}
            )
        return res.status_code == 200 and res.json().get("protocol") == PROTOCOL
    except (httpx.HTTPError, ValueError):
        return False


_GONE = (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError)
_start_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


async def discover(*, spawn: bool = True) -> EngineRecord:
    """The running engine, started on demand."""
    record = read_record()
    if record is not None and _pid_alive(record.pid) and await _healthy(record):
        return record
    if not spawn:
        raise ProviderProtocolError("No provider engine is running.")
    loop = asyncio.get_running_loop()
    lock = _start_locks.setdefault(loop, asyncio.Lock())
    async with lock:
        record = read_record()
        if record is not None and _pid_alive(record.pid) and await _healthy(record):
            return record
        return await _spawn()


async def _spawn() -> EngineRecord:
    argv = [*abx_command(), "provider", "engine", "serve"]
    directory = abx_dir()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "engine.log").open("ab") as log:
        try:
            # ABX_BIN/PATH selects the user's trusted local engine, never a remote command.
            subprocess.Popen(  # noqa: S603  # nosec B603 - argv only; shell defaults to False
                argv,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            raise ProviderProtocolError(
                f"Could not start the provider engine ({argv[0]}): {exc}",
                suggestion="Check that abx runs, or set ABX_BIN.",
            ) from exc
    deadline = time.monotonic() + _START_TIMEOUT
    while time.monotonic() < deadline:
        record = read_record()
        if record is not None and _pid_alive(record.pid) and await _healthy(record):
            return record
        await asyncio.sleep(0.1)
    raise ProviderProtocolError(
        "The provider engine did not start in time.",
        suggestion=f"See {directory / 'engine.log'}.",
    )


def encode_connection(connection: dict[str, Any]) -> str:
    raw = json.dumps(connection, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def raise_engine_error(payload: Any, status: int) -> None:
    """Re-raise an engine ``{error: {type, code, message}}`` as the SDK exception of that type."""
    err = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(err, dict):
        raise ProviderProtocolError(f"The provider engine answered HTTP {status}.")
    cls = getattr(_errors, str(err.get("type", "")), None)
    if not (isinstance(cls, type) and issubclass(cls, SandboxError)):
        cls = SandboxError
    exc = cls.__new__(cls)
    SandboxError.__init__(
        exc,
        str(err.get("message", "")),
        code=str(err["code"]) if err.get("code") else None,
        suggestion=str(err["suggestion"]) if err.get("suggestion") else None,
        docs_url=str(err["docs_url"]) if err.get("docs_url") else None,
    )
    raise exc


class EngineClient:
    """One connection (provider, options, credentials) to the engine."""

    def __init__(self, connection: dict[str, Any]) -> None:
        self.connection = connection
        self._header = encode_connection(connection)
        self._record: EngineRecord | None = None
        self._http = httpx.AsyncClient(timeout=None)

    async def close(self) -> None:
        await self._http.aclose()

    async def _record_now(self, *, fresh: bool = False) -> EngineRecord:
        if fresh or self._record is None:
            self._record = await discover()
        return self._record

    def _headers(self, record: EngineRecord, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {record.token}", "X-Abx-Connection": self._header}
        if extra:
            headers.update(extra)
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        content: bytes | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        connection: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> httpx.Response:
        """Send one request; disable retries for mutations that must never be replayed."""
        extra: dict[str, str] = {}
        if connection is not None:
            extra["X-Abx-Connection"] = encode_connection(connection)
        if content is not None:
            extra["Content-Type"] = "application/octet-stream"
        last: Exception | None = None
        for attempt in range(2 if retry else 1):
            record = await self._record_now(fresh=attempt > 0)
            try:
                res = await self._http.request(
                    method,
                    f"{record.base}{path}",
                    headers=self._headers(record, extra),
                    json=json_body,
                    content=content,
                    params=params,
                    timeout=timeout,
                )
            except _GONE as exc:
                last = exc
                continue
            if retry and res.status_code == 401 and attempt == 0:
                continue
            return res
        raise ProviderProtocolError(f"The provider engine is not reachable: {last}")

    async def call(self, method: str, path: str, **kwargs: Any) -> Any:
        """JSON in, JSON out; an engine error becomes the SDK exception."""
        res = await self.request(method, path, **kwargs)
        if res.status_code >= 400:
            raise_engine_error(_json_or_none(res), res.status_code)
        return _json_or_none(res)

    async def stream(
        self, method: str, path: str, *, json_body: Any = None, params: dict[str, Any] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Server-sent events as dicts. An ``error`` event raises the SDK exception."""
        record = await self._record_now()
        started = False
        for attempt in range(2):
            try:
                async with self._http.stream(
                    method,
                    f"{record.base}{path}",
                    headers=self._headers(record),
                    json=json_body,
                    params=params,
                ) as res:
                    if res.status_code >= 400:
                        await res.aread()
                        if res.status_code == 401 and attempt == 0:
                            record = await self._record_now(fresh=True)
                            continue
                        raise_engine_error(_json_or_none(res), res.status_code)
                    event = "message"
                    async for line in res.aiter_lines():
                        if line.startswith("event: "):
                            event = line[7:].strip()
                        elif line.startswith("data: "):
                            data = json.loads(line[6:])
                            if event == "error":
                                raise_engine_error(data, 500)
                            if event == "end":
                                return
                            started = True
                            yield data
                            event = "message"
                    return
            except _GONE as exc:
                if attempt == 1 or started:
                    raise ProviderProtocolError(
                        f"The provider engine is not reachable: {exc}"
                    ) from exc
                record = await self._record_now(fresh=True)

    async def websocket(self, path: str, params: dict[str, Any] | None = None) -> Any:
        import websockets

        record = await self._record_now()
        query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
        url = f"ws://{record.host}:{record.port}{path}" + (f"?{query}" if query else "")
        headers = self._headers(record)
        kwargs: dict[str, Any] = {"additional_headers": headers}
        try:
            return await websockets.connect(url, **kwargs)
        except TypeError:  # websockets < 14 names the argument extra_headers
            return await websockets.connect(url, extra_headers=headers)


def _json_or_none(res: httpx.Response) -> Any:
    if not res.content:
        return None
    with contextlib.suppress(ValueError):
        return res.json()
    return None
