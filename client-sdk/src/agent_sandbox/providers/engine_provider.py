"""``node`` providers: the provider code is an ES module that the local engine loads.

The same module serves the CLI and every other SDK, so a backend is written once. The SDK
resolves the configuration (environment, ``.env``, ``config.toml``) and sends it with every
call; the engine runs the provider.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from agent_sandbox.models.errors import ProviderFeatureNotSupportedError, SandboxNotFoundError
from agent_sandbox.models.filesystem import FileInfo, WatchEvent
from agent_sandbox.models.process import ProcessChunk, ProcessChunkType, ProcessInfo
from agent_sandbox.models.sandbox import SandboxConfig, SandboxInfo, SandboxStatus
from agent_sandbox.providers import store
from agent_sandbox.providers.base import Provider, ProviderInfra, consented_inherit
from agent_sandbox.providers.engine_client import EngineClient, raise_engine_error
from agent_sandbox.transport.streaming import StreamReader

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from agent_sandbox.providers.manifest import Manifest
    from agent_sandbox.transport.auth import EnvdTokenManager
    from agent_sandbox.transport.config import TransportConfig

_SCHEME = "engine://"


def is_engine_url(url: str) -> bool:
    return url.startswith(_SCHEME)


def _sandbox_id_from(envd_url: str) -> str:
    return envd_url.rsplit("/", 1)[-1]


def _quoted(sandbox_id: str) -> str:
    return quote(sandbox_id, safe="")


def _info(data: dict[str, Any], provider_id: str) -> SandboxInfo:
    """A :class:`SandboxInfo` for an engine record; ``envd_url`` becomes a marker URL."""
    body = dict(data.get("info", data))
    sandbox_id = str(body.get("sandbox_id") or data.get("sandbox_id") or "")
    body["envd_url"] = f"{_SCHEME}{provider_id}/{sandbox_id}"
    body["envd_access_token"] = None
    if not body.get("region"):
        body["region"] = ""
    if not body.get("timeout"):
        body["timeout"] = 0
    with contextlib.suppress(ValueError):
        body["status"] = SandboxStatus(str(body.get("status", "running")))
    for key in ("started_at", "end_at"):
        value = body.get(key)
        if isinstance(value, str):
            with contextlib.suppress(ValueError):
                body[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return SandboxInfo.model_validate(body)


def _chunk(frame: dict[str, Any]) -> ProcessChunk:
    kind = frame.get("type", "stdout")
    ctype = (
        ProcessChunkType(kind) if kind in ("stdout", "stderr", "exit") else ProcessChunkType.STDOUT
    )
    return ProcessChunk(
        type=ctype, data=str(frame.get("data", "")), exit_code=frame.get("exit_code")
    )


class EngineSandboxProtocol:
    """``SandboxProtocol`` over the engine."""

    def __init__(self, client: EngineClient, provider_id: str, features: frozenset[str]) -> None:
        self._c = client
        self._pid = provider_id
        self._features = features

    @property
    def has_port_url(self) -> bool:
        return "ports.url" in self._features

    def _need(self, feature: str) -> None:
        if feature not in self._features:
            raise ProviderFeatureNotSupportedError(self._pid, feature)

    async def create(
        self, config: SandboxConfig, *, request_timeout: float | None = None
    ) -> SandboxInfo:
        self._need("sandbox.lifecycle")
        body: dict[str, Any] = {
            "template": config.template,
            "timeout": config.timeout,
            "metadata": config.metadata,
            "envs": config.env_vars,
            "cpu": config.cpu,
            "memory": config.memory,
            "disk": config.disk,
            "gpu": config.gpu,
            "request_timeout": request_timeout,
        }
        if config.secure is not None:
            body["secure"] = config.secure
        connection = dict(self._c.connection)
        if config.provider_options:
            connection["provider_options"] = {
                **connection.get("provider_options", {}),
                **config.provider_options,
            }
        body = {k: v for k, v in body.items() if v is not None}
        data = await self._c.call(
            "POST", "/v1/sandboxes", json_body=body, connection=connection, timeout=request_timeout
        )
        return _info(data, self._pid)

    async def connect(self, sandbox_id: str) -> SandboxInfo:
        self._need("sandbox.lifecycle")
        data = await self._c.call("POST", f"/v1/sandboxes/{_quoted(sandbox_id)}/connect")
        return _info(data, self._pid)

    async def get_info(self, sandbox_id: str) -> SandboxInfo:
        self._need("sandbox.lifecycle")
        data = await self._c.call("GET", f"/v1/sandboxes/{_quoted(sandbox_id)}")
        return _info({"info": data}, self._pid)

    async def list(
        self, *, status: SandboxStatus | None = None, limit: int = 100, offset: int = 0
    ) -> list[SandboxInfo]:
        self._need("sandbox.lifecycle")
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status.value
        data = await self._c.call("GET", "/v1/sandboxes", params=params)
        return [_info({"info": item}, self._pid) for item in data.get("sandboxes", [])]

    async def kill(self, sandbox_id: str) -> None:
        self._need("sandbox.lifecycle")
        with contextlib.suppress(SandboxNotFoundError):
            await self._c.call("DELETE", f"/v1/sandboxes/{_quoted(sandbox_id)}")

    async def set_timeout(self, sandbox_id: str, timeout: int) -> None:
        self._need("sandbox.timeout")
        await self._c.call(
            "POST", f"/v1/sandboxes/{_quoted(sandbox_id)}/timeout", json_body={"timeout": timeout}
        )

    async def is_running(self, sandbox_id: str) -> bool:
        self._need("sandbox.lifecycle")
        data = await self._c.call("GET", f"/v1/sandboxes/{_quoted(sandbox_id)}/running")
        return bool(data.get("running"))

    async def pause(self, sandbox_id: str) -> None:
        self._need("sandbox.pause")
        await self._c.call("POST", f"/v1/sandboxes/{_quoted(sandbox_id)}/pause", json_body={})

    async def resume(self, sandbox_id: str) -> None:
        self._need("sandbox.pause")
        await self._c.call("POST", f"/v1/sandboxes/{_quoted(sandbox_id)}/resume", json_body={})

    async def port_url(self, sandbox_id: str, port: int) -> tuple[str, dict[str, str]]:
        self._need("ports.url")
        data = await self._c.call(
            "GET", f"/v1/sandboxes/{_quoted(sandbox_id)}/ports/{int(port)}/url"
        )
        return str(data["url"]), {str(k): str(v) for k, v in (data.get("headers") or {}).items()}


class EngineTerminal:
    """The ``TerminalSession`` interface over the engine's WebSocket."""

    def __init__(self, ws: Any) -> None:
        self._ws = ws

    async def send(self, data: str) -> None:
        await self._ws.send(data)

    async def send_bytes(self, data: bytes) -> None:
        await self._ws.send(data)

    async def receive(self, timeout: float | None = None) -> str | bytes:
        message: str | bytes
        if timeout is None:
            message = await self._ws.recv()
        else:
            message = await asyncio.wait_for(self._ws.recv(), timeout)
        return message

    async def output_stream(self) -> AsyncIterator[str | bytes]:
        async for message in self._ws:
            yield message

    async def resize(self, cols: int, rows: int) -> None:
        await self._ws.send(json.dumps({"type": "resize", "cols": cols, "rows": rows}))

    @property
    def is_connected(self) -> bool:
        state = getattr(self._ws, "state", None)
        if state is not None:
            return getattr(state, "name", "") == "OPEN"
        return not getattr(self._ws, "closed", False)

    async def close(self) -> None:
        await self._ws.close()

    async def __aenter__(self) -> EngineTerminal:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


class EngineProcessProtocol:
    """``ProcessProtocol`` over the engine."""

    def __init__(self, client: EngineClient, provider_id: str, features: frozenset[str]) -> None:
        self._c = client
        self._pid = provider_id
        self._features = features

    def _manage(self) -> None:
        if "process.manage" not in self._features:
            raise ProviderFeatureNotSupportedError(self._pid, "process.manage")

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
        if "exec.run" not in self._features and "exec.stream" not in self._features:
            raise ProviderFeatureNotSupportedError(self._pid, "exec.run")
        body = {
            "cmd": cmd,
            "args": list(args or []),
            "env": dict(env or {}),
            "cwd": cwd,
            "user": user,
            "timeout": timeout,
        }
        route = f"/v1/sandboxes/{_quoted(_sandbox_id_from(envd_url))}/commands/stream"
        return StreamReader(self._c.stream("POST", route, json_body=body), _chunk)

    async def list_processes(
        self, envd_url: str, envd_token: EnvdTokenManager
    ) -> list[ProcessInfo]:
        self._manage()
        data = await self._c.call(
            "GET", f"/v1/sandboxes/{_quoted(_sandbox_id_from(envd_url))}/processes"
        )
        return [ProcessInfo.model_validate(p) for p in data.get("processes", [])]

    async def _post(self, envd_url: str, pid: int | str, action: str, body: dict[str, Any]) -> None:
        self._manage()
        route = f"/v1/sandboxes/{_quoted(_sandbox_id_from(envd_url))}/processes/{pid}/{action}"
        await self._c.call("POST", route, json_body=body)

    async def send_input(
        self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str, data: str
    ) -> None:
        await self._post(envd_url, pid, "stdin", {"data": data})

    async def send_stdin(
        self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str, data: str
    ) -> None:
        await self.send_input(envd_url, envd_token, pid=pid, data=data)

    async def send_signal(
        self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str, signal: int = 15
    ) -> None:
        await self._post(envd_url, pid, "signal", {"signal": signal})

    async def kill(self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str) -> None:
        self._manage()
        route = f"/v1/sandboxes/{_quoted(_sandbox_id_from(envd_url))}/processes/{pid}"
        await self._c.call("DELETE", route)

    async def open_terminal(
        self, sandbox_id: str, *, cols: int = 80, rows: int = 24
    ) -> EngineTerminal:
        ws = await self._c.websocket(
            f"/v1/sandboxes/{_quoted(sandbox_id)}/terminal", {"cols": cols, "rows": rows}
        )
        return EngineTerminal(ws)


def _raise_for(res: Any) -> None:
    if res.status_code >= 400:
        try:
            payload = res.json()
        except ValueError:
            payload = None
        raise_engine_error(payload, res.status_code)


def _file_info(entry: dict[str, Any]) -> FileInfo:
    body = dict(entry)
    if isinstance(body.get("modified"), str):
        with contextlib.suppress(ValueError):
            body["modified"] = datetime.fromisoformat(body["modified"].replace("Z", "+00:00"))
    return FileInfo.model_validate(body)


class EngineFilesystemProtocol:
    """``FilesystemProtocol`` over the engine."""

    def __init__(self, client: EngineClient, provider_id: str, features: frozenset[str]) -> None:
        self._c = client
        self._pid = provider_id
        self._features = features

    def _route(self, envd_url: str, suffix: str) -> str:
        if "files.rw" not in self._features:
            raise ProviderFeatureNotSupportedError(self._pid, "files.rw")
        return f"/v1/sandboxes/{_quoted(_sandbox_id_from(envd_url))}/files{suffix}"

    async def stat(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> FileInfo:
        data = await self._c.call("GET", self._route(envd_url, "/info"), params={"path": path})
        return _file_info(data)

    async def list_dir(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str = "/"
    ) -> list[FileInfo]:
        data = await self._c.call("GET", self._route(envd_url, "/list"), params={"path": path})
        return [_file_info(e) for e in data.get("entries", [])]

    async def make_dir(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> None:
        await self._c.call("POST", self._route(envd_url, "/mkdir"), json_body={"path": path})

    async def remove(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> None:
        await self._c.call("DELETE", self._route(envd_url, ""), params={"path": path})

    async def move(
        self, envd_url: str, envd_token: EnvdTokenManager, *, source: str, destination: str
    ) -> None:
        await self._c.call(
            "POST",
            self._route(envd_url, "/move"),
            json_body={"source": source, "destination": destination},
        )

    async def watch_dir(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str
    ) -> StreamReader[WatchEvent]:
        if "files.watch" not in self._features:
            raise ProviderFeatureNotSupportedError(self._pid, "files.watch")
        route = self._route(envd_url, "/watch")
        return StreamReader(
            self._c.stream("GET", route, params={"path": path}),
            lambda frame: WatchEvent.model_validate(frame),
        )

    async def upload_file(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
        content: bytes,
        username: str = "user",
    ) -> None:
        res = await self._c.request(
            "PUT", self._route(envd_url, "/content"), params={"path": path}, content=content
        )
        _raise_for(res)

    async def download_file(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str, username: str = "user"
    ) -> bytes:
        res = await self._c.request("GET", self._route(envd_url, "/content"), params={"path": path})
        _raise_for(res)
        return res.content

    async def exists(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> bool:
        data = await self._c.call("GET", self._route(envd_url, "/exists"), params={"path": path})
        return bool(data.get("exists"))

    async def get_info(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> FileInfo:
        return await self.stat(envd_url, envd_token, path=path)

    async def read(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
        max_bytes: int | None = None,
    ) -> bytes:
        if max_bytes is not None:
            raise ProviderFeatureNotSupportedError(self._pid, "bounded file reads")
        return await self.download_file(envd_url, envd_token, path=path)

    async def read_text(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str, encoding: str = "utf-8"
    ) -> str:
        return (await self.read(envd_url, envd_token, path=path)).decode(encoding)

    async def write(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str, content: str | bytes
    ) -> None:
        raw = content.encode("utf-8") if isinstance(content, str) else content
        await self.upload_file(envd_url, envd_token, path=path, content=raw)

    async def rename(
        self, envd_url: str, envd_token: EnvdTokenManager, *, old_path: str, new_path: str
    ) -> None:
        await self.move(envd_url, envd_token, source=old_path, destination=new_path)


class EngineCodeProtocol:
    """``CodeInterpreterProtocol`` over the engine."""

    def __init__(self, client: EngineClient, provider_id: str, features: frozenset[str]) -> None:
        self._c = client
        self._pid = provider_id
        self._features = features

    async def run_code(
        self,
        sandbox_id: str,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        code: str,
        language: str = "python",
        context_id: str | None = None,
        timeout: int = 30,
        envs: dict[str, str] | None = None,
        on_stdout: Any = None,
        on_stderr: Any = None,
        on_result: Any = None,
    ) -> dict[str, Any]:
        if "code.interpret" not in self._features:
            raise ProviderFeatureNotSupportedError(self._pid, "code.interpret")
        body = {
            "code": code,
            "language": language,
            "context_id": context_id,
            "timeout": timeout,
            "envs": envs,
        }
        result: dict[str, Any] = await self._c.call(
            "POST",
            f"/v1/sandboxes/{_quoted(_sandbox_id_from(envd_url))}/code/run",
            json_body=body,
            timeout=float(timeout) + 15.0,
        )
        if on_stdout and result.get("stdout"):
            on_stdout(result["stdout"])
        if on_stderr and result.get("stderr"):
            on_stderr(result["stderr"])
        if on_result:
            on_result(result)
        return result

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        async def _raise(*_a: Any, **_k: Any) -> Any:
            raise ProviderFeatureNotSupportedError(self._pid, "code.interpret")

        return _raise


class EngineProvider(Provider):
    """A provider whose code is an installed ES module, run by the local engine."""

    kind = "node"
    envd_allow_missing = True

    def __init__(
        self,
        manifest: Manifest,
        plugin_root: Path,
        receipt: dict[str, Any] | None = None,
    ) -> None:
        self.manifest = manifest
        self.plugin_root = plugin_root
        self.receipt = receipt
        self.id = manifest.id
        self.display_name = manifest.name
        self.display_name_zh = manifest.name_zh
        self.version = manifest.version
        self.features = frozenset(manifest.features)
        self.config_fields = manifest.fields
        self.auth_any_of = manifest.auth_any_of
        self.inherit = consented_inherit(manifest.inherit, receipt)

    def connection(self, config: TransportConfig) -> dict[str, Any]:
        """What the engine needs to run this provider as the caller configured it."""
        opts = dict(config.provider_options)
        options = {
            f.key: opts[f.key] for f in self.config_fields if opts.get(f.key) not in (None, "")
        }
        connection: dict[str, Any] = {"provider": self.id, "provider_options": options}
        if "sandbox_api_key" in self.inherit and config.sandbox_api_key:
            connection["api_key"] = config.sandbox_api_key
        if "sandbox_base_url" in self.inherit and config.sandbox_base_url:
            connection["api_url"] = config.sandbox_base_url
        if "sandbox_domain" in self.inherit and config.sandbox_domain:
            connection["domain"] = config.sandbox_domain
        return connection

    async def build_infra(self, config: TransportConfig) -> ProviderInfra:
        self.validate_config(config)
        if self.receipt is not None and self.receipt.get("trust") != "link":
            store.verify_integrity(self.id)
        client = EngineClient(self.connection(config))
        features = self.features
        return ProviderInfra(
            config=config,
            auth=None,
            http_client=None,
            sandbox_protocol=EngineSandboxProtocol(client, self.id, features),
            process_protocol=EngineProcessProtocol(client, self.id, features),
            filesystem_protocol=EngineFilesystemProtocol(client, self.id, features),
            code_interpreter_protocol=EngineCodeProtocol(client, self.id, features),
            close=client.close,
        )
