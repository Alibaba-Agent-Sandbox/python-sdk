"""``exec`` providers: manifest-described plugin processes spoken to over EPP/1."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from easy_sandbox._version import __version__
from easy_sandbox.models.errors import (
    CommandTimeoutError,
    ProviderFeatureNotSupportedError,
    ProviderProtocolError,
    ProviderResourceNotFoundError,
    SandboxError,
)
from easy_sandbox.models.filesystem import FileInfo, FileType
from easy_sandbox.models.process import ProcessChunk, ProcessChunkType
from easy_sandbox.models.sandbox import SandboxConfig, SandboxInfo, SandboxStatus
from easy_sandbox.providers import store
from easy_sandbox.providers.base import Provider, ProviderInfra
from easy_sandbox.providers.epp import (
    PROTOCOL,
    EppClient,
    is_method_not_found,
    resolve_command,
    scrubbed_env,
)
from easy_sandbox.transport.streaming import StreamReader

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

    from easy_sandbox.providers.manifest import Manifest
    from easy_sandbox.transport.auth import EnvdTokenManager
    from easy_sandbox.transport.config import TransportConfig

_ENVD_SCHEMES = ("http://", "https://")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def record_to_info(rec: dict[str, Any], provider_id: str) -> SandboxInfo:
    """Convert an EPP ``SandboxRecord`` to the SDK's :class:`SandboxInfo`."""
    sandbox_id = str(rec.get("sandbox_id", ""))
    if not sandbox_id:
        raise ProviderProtocolError(f"Provider '{provider_id}' returned a sandbox without an id.")
    try:
        status = SandboxStatus(str(rec.get("status", "running")))
    except ValueError:
        status = SandboxStatus.RUNNING
    envd_url = rec.get("envd_url") or rec.get("url")
    raw_meta = rec.get("metadata")
    metadata: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    kwargs: dict[str, Any] = {
        "sandbox_id": sandbox_id,
        "template": str(rec.get("template", "")),
        "status": status,
        "metadata": {str(k): str(v) for k, v in metadata.items()},
        # Non-envd providers get a marker URL; adapters recognise it and route over EPP.
        "envd_url": envd_url
        if isinstance(envd_url, str) and envd_url
        else f"epp://{provider_id}/{sandbox_id}",
        "envd_access_token": rec.get("envd_access_token"),
        "started_at": _parse_time(rec.get("created_at")),
        "end_at": _parse_time(rec.get("expires_at")),
    }
    if rec.get("region"):
        kwargs["region"] = str(rec["region"])
    return SandboxInfo(**kwargs)


def is_epp_url(url: str) -> bool:
    return url.startswith("epp://")


class _Unsupported:
    """Adapter for a feature group the plugin does not provide (raises E8004)."""

    def __init__(self, provider_id: str, feature: str) -> None:
        self._provider_id = provider_id
        self._feature = feature

    def __getattr__(self, name: str) -> Callable[..., Any]:
        async def _raise(*_a: Any, **_k: Any) -> Any:
            raise ProviderFeatureNotSupportedError(self._provider_id, self._feature)

        return _raise


class ExecSandboxProtocol:
    """``SandboxProtocol`` over EPP."""

    def __init__(
        self,
        client: EppClient,
        supported: frozenset[str],
        secret_option_keys: frozenset[str] = frozenset(),
    ) -> None:
        self._c = client
        self._features = supported
        self._pid = client.provider_id
        self._secret_option_keys = secret_option_keys
        self._has_connect = True

    @property
    def has_port_url(self) -> bool:
        return "ports.url" in self._features

    async def port_url(self, sandbox_id: str, port: int) -> tuple[str, dict[str, str]]:
        """Ask the plugin for the public URL (and access headers) of *port*."""
        self._need("ports.url")
        res = await self._c.call("ports.url", {"sandbox_id": sandbox_id, "port": int(port)})
        url = res.get("url")
        if not isinstance(url, str) or not url:
            raise ProviderProtocolError(f"Provider '{self._pid}' returned no url for ports.url.")
        raw = res.get("headers")
        headers = {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
        return url, headers

    def _need(self, feature: str) -> None:
        if feature not in self._features:
            raise ProviderFeatureNotSupportedError(self._pid, feature)

    async def create(
        self, config: SandboxConfig, *, request_timeout: float | None = None
    ) -> SandboxInfo:
        self._need("sandbox.lifecycle")
        params = {
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
            params["secure"] = config.secure
        options = {
            k: v for k, v in config.provider_options.items() if k not in self._secret_option_keys
        }
        if options:
            params["options"] = options
        rec = await self._c.call("sandbox.create", params, timeout=request_timeout)
        return record_to_info(rec, self._pid)

    async def connect(self, sandbox_id: str) -> SandboxInfo:
        """``sandbox.connect`` when the plugin has it (it may resume), else ``sandbox.get``."""
        self._need("sandbox.lifecycle")
        if self._has_connect:
            try:
                return record_to_info(
                    await self._c.call("sandbox.connect", {"sandbox_id": sandbox_id}), self._pid
                )
            except ProviderProtocolError as exc:
                if not is_method_not_found(exc):
                    raise
                self._has_connect = False
        return record_to_info(
            await self._c.call("sandbox.get", {"sandbox_id": sandbox_id}), self._pid
        )

    async def get_info(self, sandbox_id: str) -> SandboxInfo:
        self._need("sandbox.lifecycle")
        return record_to_info(
            await self._c.call("sandbox.get", {"sandbox_id": sandbox_id}), self._pid
        )

    async def list(
        self, *, status: SandboxStatus | None = None, limit: int = 100, offset: int = 0
    ) -> list[SandboxInfo]:
        self._need("sandbox.lifecycle")
        out: list[SandboxInfo] = []
        cursor: str | None = None
        while len(out) < limit + offset:
            params: dict[str, Any] = {"limit": limit + offset}
            if status is not None:
                params["status"] = status.value
            if cursor:
                params["cursor"] = cursor
            res = await self._c.call("sandbox.list", params)
            out.extend(record_to_info(r, self._pid) for r in res.get("sandboxes", []))
            cursor = res.get("next")
            if not cursor:
                break
        return out[offset : offset + limit]

    async def kill(self, sandbox_id: str) -> None:
        self._need("sandbox.lifecycle")
        try:
            await self._c.call("sandbox.kill", {"sandbox_id": sandbox_id})
        except ProviderResourceNotFoundError:
            return  # idempotent, like the built-in provider's 404 handling

    async def set_timeout(self, sandbox_id: str, timeout: int) -> None:
        self._need("sandbox.timeout")
        await self._c.call("sandbox.set_timeout", {"sandbox_id": sandbox_id, "timeout": timeout})

    async def is_running(self, sandbox_id: str) -> bool:
        info = await self.get_info(sandbox_id)
        return info.status == SandboxStatus.RUNNING

    async def pause(self, sandbox_id: str) -> None:
        self._need("sandbox.pause")
        await self._c.call("sandbox.pause", {"sandbox_id": sandbox_id})

    async def resume(self, sandbox_id: str) -> None:
        self._need("sandbox.pause")
        await self._c.call("sandbox.resume", {"sandbox_id": sandbox_id})


def _sandbox_id_from(envd_url: str) -> str:
    return envd_url.rsplit("/", 1)[-1]


class ExecProcessProtocol:
    """``ProcessProtocol`` over EPP; delegates to the native envd transport in hybrid mode."""

    def __init__(self, client: EppClient, supported: frozenset[str], native: Any | None) -> None:
        self._c = client
        self._features = supported
        self._native = native
        self._pid = client.provider_id

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
        if not is_epp_url(envd_url):
            assert self._native is not None
            native_stream: StreamReader[ProcessChunk] = await self._native.start(
                envd_url,
                envd_token,
                cmd=cmd,
                args=args,
                env=env,
                cwd=cwd,
                timeout=timeout,
                user=user,
            )
            return native_stream
        sandbox_id = _sandbox_id_from(envd_url)
        params: dict[str, Any] = {
            "sandbox_id": sandbox_id,
            "cmd": cmd,
            "args": list(args or []),
            "env": dict(env or {}),
            "cwd": cwd,
            "user": user,
            "timeout": timeout,
        }
        if "exec.stream" in self._features:
            return StreamReader(self._stream(params, timeout), _frame_to_chunk)
        if "exec.run" not in self._features:
            raise ProviderFeatureNotSupportedError(self._pid, "exec.run")
        return StreamReader(self._buffered(params, timeout), _frame_to_chunk)

    async def _buffered(
        self, params: dict[str, Any], timeout: int
    ) -> AsyncIterator[dict[str, Any]]:
        res = await self._c.call("exec.run", params, timeout=float(timeout) + 5.0)
        if res.get("stdout"):
            yield {"type": "stdout", "data": res["stdout"]}
        if res.get("stderr"):
            yield {"type": "stderr", "data": res["stderr"]}
        yield {"type": "exit", "exit_code": int(res.get("exit_code", 0))}

    async def _stream(self, params: dict[str, Any], timeout: int) -> AsyncIterator[dict[str, Any]]:
        res = await self._c.call("exec.start", params, timeout=float(timeout) + 5.0)
        process_id = str(res.get("process_id"))
        queue = self._c.open_stream(process_id)
        try:
            while True:
                try:
                    note = await asyncio.wait_for(queue.get(), float(timeout) + 5.0)
                except asyncio.TimeoutError:
                    raise CommandTimeoutError(
                        f"Command did not finish within {timeout}s (provider '{self._pid}' "
                        "reported no exit).",
                        suggestion="Raise the command timeout or fix the plugin's timeout handling",
                    ) from None
                if note is None:
                    if self._c.failure is not None:
                        raise self._c.failure
                    return
                if note.get("method") == "exec.output":
                    stream = "stderr" if note.get("stream") == "stderr" else "stdout"
                    yield {"type": stream, "data": str(note.get("data", ""))}
                elif note.get("method") == "exec.exit":
                    yield {"type": "exit", "exit_code": int(note.get("exit_code", 0))}
                    return
        finally:
            self._c.close_stream(process_id)

    async def list_processes(self, envd_url: str, envd_token: EnvdTokenManager) -> list[Any]:
        if not is_epp_url(envd_url):
            assert self._native is not None
            return await self._native.list_processes(envd_url, envd_token)  # type: ignore[no-any-return]
        if "process.manage" not in self._features:
            raise ProviderFeatureNotSupportedError(self._pid, "process.manage")
        from easy_sandbox.models.process import ProcessInfo

        res = await self._c.call("process.list", {"sandbox_id": _sandbox_id_from(envd_url)})
        return [ProcessInfo.model_validate(p) for p in res.get("processes", [])]

    async def _simple(
        self, method: str, envd_url: str, envd_token: EnvdTokenManager, **params: Any
    ) -> None:
        if "process.manage" not in self._features:
            raise ProviderFeatureNotSupportedError(self._pid, "process.manage")
        await self._c.call(method, {"sandbox_id": _sandbox_id_from(envd_url), **params})

    async def send_input(
        self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str, data: str
    ) -> None:
        if not is_epp_url(envd_url):
            assert self._native is not None
            await self._native.send_input(envd_url, envd_token, pid=pid, data=data)
            return
        await self._simple("process.stdin", envd_url, envd_token, pid=pid, data=data)

    async def send_signal(
        self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str, signal: int = 15
    ) -> None:
        if not is_epp_url(envd_url):
            assert self._native is not None
            await self._native.send_signal(envd_url, envd_token, pid=pid, signal=signal)
            return
        await self._simple("process.signal", envd_url, envd_token, pid=pid, signal=signal)

    async def send_stdin(
        self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str, data: str
    ) -> None:
        await self.send_input(envd_url, envd_token, pid=pid, data=data)

    async def kill(self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str) -> None:
        if not is_epp_url(envd_url):
            assert self._native is not None
            await self._native.kill(envd_url, envd_token, pid=pid)
            return
        await self._simple("process.kill", envd_url, envd_token, pid=pid)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if self._native is not None:
            return getattr(self._native, name)
        raise ProviderFeatureNotSupportedError(self._pid, "exec.stream")


def _frame_to_chunk(frame: dict[str, Any]) -> ProcessChunk:
    kind = frame.get("type", "stdout")
    ctype = (
        ProcessChunkType(kind) if kind in ("stdout", "stderr", "exit") else ProcessChunkType.STDOUT
    )
    return ProcessChunk(
        type=ctype, data=str(frame.get("data", "")), exit_code=frame.get("exit_code")
    )


class ExecFilesystemProtocol:
    """``FilesystemProtocol`` over EPP; delegates in hybrid mode."""

    def __init__(self, client: EppClient, supported: frozenset[str], native: Any | None) -> None:
        self._c = client
        self._features = supported
        self._native = native
        self._pid = client.provider_id

    def _call(self, method: str, envd_url: str, **params: Any) -> Any:
        if "files.rw" not in self._features:
            raise ProviderFeatureNotSupportedError(self._pid, "files.rw")
        return self._c.call(method, {"sandbox_id": _sandbox_id_from(envd_url), **params})

    @staticmethod
    def _info(entry: dict[str, Any]) -> FileInfo:
        kind = FileType.DIRECTORY if entry.get("type") in ("dir", "directory") else FileType.FILE
        return FileInfo(
            name=str(entry.get("name", "")),
            path=str(entry.get("path", "")),
            type=kind,
            size=int(entry.get("size", 0) or 0),
            modified=_parse_time(entry.get("mtime")),
        )

    async def stat(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> FileInfo:
        if not is_epp_url(envd_url):
            return await self._native.stat(envd_url, envd_token, path=path)  # type: ignore[no-any-return,union-attr]
        return self._info(await self._call("files.stat", envd_url, path=path))

    async def list_dir(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str = "/"
    ) -> list[FileInfo]:
        if not is_epp_url(envd_url):
            return await self._native.list_dir(envd_url, envd_token, path=path)  # type: ignore[no-any-return,union-attr]
        res = await self._call("files.list", envd_url, path=path)
        return [self._info(e) for e in res.get("entries", [])]

    async def make_dir(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> None:
        if not is_epp_url(envd_url):
            await self._native.make_dir(envd_url, envd_token, path=path)  # type: ignore[union-attr]
            return
        await self._call("files.mkdir", envd_url, path=path)

    async def remove(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> None:
        if not is_epp_url(envd_url):
            await self._native.remove(envd_url, envd_token, path=path)  # type: ignore[union-attr]
            return
        await self._call("files.remove", envd_url, path=path)

    async def move(
        self, envd_url: str, envd_token: EnvdTokenManager, *, source: str, destination: str
    ) -> None:
        if not is_epp_url(envd_url):
            await self._native.move(envd_url, envd_token, source=source, destination=destination)  # type: ignore[union-attr]
            return
        await self._call("files.move", envd_url, source=source, destination=destination)

    async def watch_dir(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> Any:
        if not is_epp_url(envd_url):
            return await self._native.watch_dir(envd_url, envd_token, path=path)  # type: ignore[union-attr]
        raise ProviderFeatureNotSupportedError(self._pid, "files.watch")

    async def upload_file(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
        content: bytes,
        username: str = "user",
    ) -> None:
        if not is_epp_url(envd_url):
            await self._native.upload_file(  # type: ignore[union-attr]
                envd_url, envd_token, path=path, content=content, username=username
            )
            return
        await self._call(
            "files.write",
            envd_url,
            path=path,
            content_b64=base64.b64encode(content).decode("ascii"),
        )

    async def download_file(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str, username: str = "user"
    ) -> bytes:
        if not is_epp_url(envd_url):
            return await self._native.download_file(  # type: ignore[no-any-return,union-attr]
                envd_url, envd_token, path=path, username=username
            )
        res = await self._call("files.read", envd_url, path=path)
        return base64.b64decode(res.get("content_b64", ""))

    async def exists(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> bool:
        try:
            await self.stat(envd_url, envd_token, path=path)
            return True
        except SandboxError:
            return False

    async def get_info(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> FileInfo:
        return await self.stat(envd_url, envd_token, path=path)

    async def read(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> bytes:
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


class ExecProvider(Provider):
    """A provider backed by an installed (or linked) plugin process."""

    kind = "exec"

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
        consented = set(
            (receipt or {})
            .get("consented", {})
            .get("inherit", manifest.inherit if receipt is None else [])
        )
        self.inherit = frozenset(set(manifest.inherit) & consented)

    async def build_infra(self, config: TransportConfig) -> ProviderInfra:
        self.validate_config(config)
        if self.receipt is not None:
            store.verify_integrity(self.id)
        argv = resolve_command(self.manifest.command, self.plugin_root)
        data_dir = store.data_dir(self.id)
        opts = dict(config.provider_options)
        init_config = {
            f.key: opts.get(f.key) for f in self.config_fields if opts.get(f.key) is not None
        }
        core: dict[str, Any] = {}
        for key in self.inherit:
            val = getattr(config, key, None)
            if val is not None:
                core[key] = val
        core.update(
            {
                "http_timeout": config.http_timeout,
                "max_retries": config.max_retries,
            }
        )
        secret_values = [
            str(v) for f in self.config_fields if f.secret and (v := init_config.get(f.key))
        ] + [str(core[k]) for k in ("sandbox_api_key",) if k in core]
        client = EppClient(
            self.id,
            argv,
            cwd=data_dir,
            env=scrubbed_env(data_dir, self.manifest.security.get("env_passthrough", [])),
            startup_timeout=self.manifest.startup_timeout_ms / 1000.0,
            call_timeout=self.manifest.call_timeout_ms / 1000.0,
            secrets=secret_values,
        )
        await client.start(
            {
                "protocol": PROTOCOL,
                "host": {"name": "easy-sandbox", "version": __version__},
                "provider_id": self.id,
                "config": init_config,
                "core": core,
                "locale": "en",
                "data_dir": str(data_dir),
            }
        )
        advertised = client.features or self.features
        supported = self.features & advertised
        native: dict[str, Any] = {}
        http_client = None
        auth = None
        if supported & {"exec.run", "exec.stream", "files.rw", "process.manage"}:
            from easy_sandbox.protocol.filesystem import FilesystemProtocol
            from easy_sandbox.protocol.process import ProcessProtocol
            from easy_sandbox.transport.http import HttpClient

            auth = _NoPlatformAuth()
            http_client = HttpClient(config, auth)
            native = {
                "process": ProcessProtocol(http_client),
                "files": FilesystemProtocol(http_client),
            }

        async def _close() -> None:
            await client.close()
            if http_client is not None:
                await http_client.close()

        return ProviderInfra(
            config=config,
            auth=auth,
            http_client=http_client,
            sandbox_protocol=ExecSandboxProtocol(
                client,
                supported,
                frozenset(f.key for f in self.config_fields if f.secret),
            ),
            process_protocol=ExecProcessProtocol(client, supported, native.get("process")),
            filesystem_protocol=ExecFilesystemProtocol(client, supported, native.get("files")),
            code_interpreter_protocol=_Unsupported(self.id, "code.interpret"),
            close=_close,
        )


class _NoPlatformAuth:
    """Platform auth placeholder: exec providers never call the Alibaba platform API."""

    async def get_headers(self) -> dict[str, str]:
        return {}

    async def refresh(self) -> None:
        return None
