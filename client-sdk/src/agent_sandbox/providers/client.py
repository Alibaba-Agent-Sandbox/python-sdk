"""Explicit target binding with optional, lock-driven Provider preparation."""

from __future__ import annotations

import asyncio
import math
import platform
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_sandbox._version import __version__
from agent_sandbox.api.sandbox import Sandbox, _InfraCloser
from agent_sandbox.models.errors import (
    ProviderConfigError,
    ProviderFeatureNotSupportedError,
    ProviderMismatchError,
    ProviderTimeoutError,
    ProviderVersionError,
)
from agent_sandbox.models.sandbox import SandboxConfig, SandboxInfo
from agent_sandbox.providers.exec_provider import ExecProvider
from agent_sandbox.providers.manifest import check_requires, load_manifest
from agent_sandbox.providers.runtime_assets import ProviderArtifact, member_path, unpack

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Collection, Sequence

    from agent_sandbox.models.sandbox import SandboxStatus
    from agent_sandbox.providers.base import Provider, ProviderInfra
    from agent_sandbox.transport.config import TransportConfig


class ProviderRuntime(BaseModel):
    """A runtime archive and the two members needed for execution and attribution."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    artifact: ProviderArtifact
    executable: str
    license_file: str

    @field_validator("executable", "license_file")
    @classmethod
    def valid_member(cls, value: str) -> str:
        return member_path(value).as_posix()


class EppImplementation(BaseModel):
    """An approved standalone EPP/1 entry and its artifact dependencies."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    language: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    platform: str = Field(pattern=r"^linux-[a-z0-9_]+-glibc$")
    priority: int = Field(ge=0)
    features: tuple[str, ...]
    entrypoint: str
    artifact: ProviderArtifact
    runtime: ProviderRuntime | None = None
    required_options: tuple[str, ...] = ()

    @field_validator("entrypoint")
    @classmethod
    def valid_entrypoint(cls, entrypoint: str) -> str:
        return member_path(entrypoint).as_posix()


class ProviderLock(BaseModel):
    """A Provider release approved via a trusted channel outside the SDK."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: str = Field(min_length=1)
    implementations: tuple[EppImplementation, ...] = ()


def _host_platform() -> str:
    machine = platform.machine().lower()
    libc, _ = platform.libc_ver()
    return f"{sys.platform}-{machine}-{libc}"


def _select_epp(
    implementations: Sequence[EppImplementation], required: frozenset[str]
) -> EppImplementation:
    supported = [
        entry
        for entry in implementations
        if entry.platform == _host_platform() and required.issubset(entry.features)
    ]
    if not supported:
        raise ProviderConfigError(
            "No approved Provider implementation matches this host and features."
        )

    def order(entry: EppImplementation) -> tuple[bool, int]:
        return entry.language != "python", entry.priority

    winner = min(supported, key=order)
    if sum(order(entry) == order(winner) for entry in supported) > 1:
        raise ProviderConfigError("Compatible Provider implementations share a priority.")
    return winner


def _prepare_epp(
    lock: ProviderLock,
    selected: EppImplementation,
    cache: Path,
    workspace: Path,
    *,
    download: bool,
    deadline: float,
    features: frozenset[str],
    option_keys: frozenset[str],
) -> ExecProvider:
    plugin_root = workspace / "provider"
    unpack(
        selected.artifact,
        cache,
        plugin_root,
        download=download,
        deadline=deadline,
        executable=selected.entrypoint if selected.runtime is None else None,
    )
    manifest = load_manifest(plugin_root)
    if (manifest.id, manifest.version) != (lock.provider, lock.version):
        raise ProviderVersionError("Provider archive identity differs from its lock.")
    if (
        manifest.kind not in {"node", "exec"}
        or (manifest.kind == "node" and selected.language != "node")
        or not set(selected.features) <= set(manifest.features)
    ):
        raise ProviderVersionError("Provider archive does not declare the locked features.")
    check_requires(manifest, component="sdk", host_version=__version__)
    declared_options = {field.key for field in manifest.fields}
    if (
        not option_keys <= declared_options
        or not set(selected.required_options) <= declared_options
    ):
        raise ProviderConfigError("The bound Provider options differ from its manifest.")
    entry = plugin_root / selected.entrypoint
    if not entry.is_file():
        raise ProviderVersionError("Provider archive is missing its locked entrypoint.")
    runtime = selected.runtime
    argv: tuple[str, ...]
    if runtime is None:
        if manifest.kind == "node":
            raise ProviderConfigError("A Node Provider requires an approved runtime archive.")
        argv = (str(entry),)
    else:
        if runtime.executable == runtime.license_file:
            raise ProviderConfigError("Runtime executable and license must be different files.")
        runtime_root = workspace / "runtime"
        unpack(
            runtime.artifact,
            cache,
            runtime_root,
            download=download,
            deadline=deadline,
            executable=runtime.executable,
            license_file=runtime.license_file,
        )
        argv = (str(runtime_root / runtime.executable), str(entry))
    data_dir = workspace / "data"
    data_dir.mkdir(mode=0o700)
    provider = ExecProvider(
        manifest,
        plugin_root,
        prepared_argv=argv,
        prepared_data_dir=data_dir,
        required_features=features,
    )
    provider.features = frozenset(selected.features)
    return provider


class _BoundProtocol:
    def __init__(self, protocol: Any, check: Callable[[], None]) -> None:
        self._protocol = protocol
        self._check = check

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._protocol, name)
        if not callable(value):
            return value

        @wraps(value)
        def checked(*args: Any, **kwargs: Any) -> Any:
            self._check()
            return value(*args, **kwargs)

        return checked


class ProviderClient:
    """An explicit Provider and account bound to one event loop.

    Call :meth:`prepare` during application startup. Close sandbox handles before
    closing the client. Delete owned sandboxes explicitly.
    """

    def __init__(
        self,
        provider: Provider,
        config: TransportConfig,
        infra: ProviderInfra | None,
        workspace: tempfile.TemporaryDirectory[str] | None,
        implementation: str,
    ) -> None:
        self._provider = provider
        self._config = config
        self._infra = infra
        self._workspace = workspace
        self._implementation = implementation
        self._loop = asyncio.get_running_loop()
        self._closed = False
        self._session_lock = asyncio.Lock()
        self._sessions: dict[int, Callable[[], Awaitable[None]]] = {}
        self._close_task: asyncio.Task[None] | None = None

    @classmethod
    async def prepare(
        cls,
        lock: ProviderLock,
        config: TransportConfig,
        *,
        native: Provider | None = None,
        required_features: Collection[str] = (),
        cache_dir: Path | None = None,
        download: bool = False,
        timeout: float = 180.0,
    ) -> ProviderClient:
        """Bind an installed Python provider or a locked standalone implementation.

        An explicitly supplied compatible native provider wins before downloading.
        The cache is offline by default. Neither path discovers global plugins.
        """
        if config.provider != lock.provider:
            raise ProviderMismatchError("Provider configuration does not match the lock.")
        if not 0 < timeout <= 3600:
            raise ProviderConfigError("Provider preparation timeout must be in (0, 3600] seconds.")
        config = config.model_copy(deep=True)
        features = frozenset(required_features)
        if native is not None and (
            (native.id, native.version) != (lock.provider, lock.version)
            or native.kind not in {"builtin", "python"}
        ):
            raise ProviderVersionError("Native Provider identity or kind differs from the lock.")
        if native is not None and features <= native.features:
            if native.kind == "builtin" and (
                not (config.sandbox_api_key or "").strip()
                or config.access_key_id
                or config.access_key_secret
                or config.security_token
                or not {"sandbox_base_url", "sandbox_domain"} <= config.model_fields_set
                or not config.sandbox_base_url.strip()
                or not config.sandbox_domain.strip()
            ):
                raise ProviderConfigError(
                    "Bind the built-in Provider with an explicit Sandbox API key, URL and domain."
                )
            native.validate_config(config)
            return cls(native, config, None, None, "python-native")
        if cache_dir is None:
            raise ProviderConfigError("A cache_dir is required to prepare a standalone Provider.")
        selected = _select_epp(lock.implementations, features)
        missing = {
            option
            for option in selected.required_options
            if config.provider_options.get(option) is None
            or (isinstance(value := config.provider_options[option], str) and not value.strip())
        }
        if missing:
            raise ProviderConfigError(
                f"Missing explicit Provider options: {', '.join(sorted(missing))}."
            )
        workspace = tempfile.TemporaryDirectory(prefix="agent-sandbox-provider-")
        deadline = time.monotonic() + timeout
        task = asyncio.create_task(
            asyncio.to_thread(
                _prepare_epp,
                lock,
                selected,
                cache_dir.absolute(),
                Path(workspace.name),
                download=download,
                deadline=deadline,
                features=features,
                option_keys=frozenset(config.provider_options),
            )
        )
        try:
            provider = await asyncio.wait_for(asyncio.shield(task), timeout)
        except BaseException as exc:
            # The thread may still own files when its awaiter is cancelled.
            def cleanup(done: asyncio.Task[ExecProvider]) -> None:
                if not done.cancelled():
                    done.exception()
                workspace.cleanup()

            task.add_done_callback(cleanup)
            if isinstance(exc, asyncio.TimeoutError):
                raise ProviderTimeoutError("Provider artifact preparation timed out.") from None
            raise

        try:
            for field in provider.config_fields:
                if field.type != "url" or field.key not in config.provider_options:
                    continue
                value = config.provider_options[field.key]
                try:
                    url = urlsplit(value) if isinstance(value, str) else None
                    valid_url = (
                        url is not None
                        and url.scheme in {"http", "https"}
                        and url.hostname
                        and url.username is None
                        and url.password is None
                    )
                except ValueError:
                    valid_url = False
                if not valid_url:
                    raise ProviderConfigError(f"Provide an explicit HTTP(S) URL for {field.key}.")
            infra = await asyncio.wait_for(
                provider.build_infra(config), max(0.0, deadline - time.monotonic())
            )
        except BaseException:
            workspace.cleanup()
            raise
        return cls(provider, config, infra, workspace, selected.id)

    @property
    def implementation(self) -> str:
        return self._implementation

    @property
    def features(self) -> frozenset[str]:
        return self._provider.features

    def _check(self) -> None:
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError("Use a ProviderClient on the event loop that prepared it.")
        if self._closed:
            raise RuntimeError("ProviderClient is closed.")

    def _sandbox_id(self, sandbox_id: str) -> str:
        self._check()
        prefix, separator, bare = sandbox_id.partition(":")
        if separator and prefix != self._provider.id:
            raise ProviderMismatchError("Sandbox reference does not match the bound Provider.")
        target = bare if separator else prefix
        if not target.strip():
            raise ValueError("Sandbox ID must not be empty.")
        return target

    async def _sandbox_infra(self) -> tuple[Provider, ProviderInfra, Callable[[], None]]:
        async with self._session_lock:
            self._check()
            provider = self._provider
            if isinstance(provider, ExecProvider):
                # EPP/1 notifications use bare process IDs, which can collide across sandboxes.
                provider = provider._session_provider()
            infra = await provider.build_infra(self._config.model_copy(deep=True))
            closer = _InfraCloser(infra)
            # Capture the original cleanup before installing the handle's close callback.
            close_infra = infra.close
            http_client = infra.http_client
            if self._closed:
                await closer.close()
                raise RuntimeError("ProviderClient is closed.")
            key = id(infra)
            closing: asyncio.Task[None] | None = None

            async def dispose() -> None:
                try:
                    if close_infra is not None:
                        await close_infra()
                    elif http_client is not None:
                        await http_client.close()
                finally:
                    self._sessions.pop(key, None)

            async def close() -> None:
                nonlocal closing
                if closing is None:
                    closing = asyncio.create_task(dispose())
                await asyncio.shield(closing)

            def check_handle() -> None:
                self._check()
                if closing is not None:
                    raise RuntimeError("Sandbox handle is closed.")

            for field in (
                "sandbox_protocol",
                "process_protocol",
                "filesystem_protocol",
                "code_interpreter_protocol",
            ):
                protocol = getattr(infra, field)
                if protocol is not None:
                    setattr(infra, field, _BoundProtocol(protocol, check_handle))
            infra.close = close
            self._sessions[key] = close
            return provider, infra, check_handle

    @asynccontextmanager
    async def _control_infra(self) -> AsyncIterator[ProviderInfra]:
        self._check()
        if self._infra is not None:
            yield self._infra
        else:
            infra = await self._provider.build_infra(self._config.model_copy(deep=True))
            try:
                self._check()
                yield infra
            finally:
                await _InfraCloser(infra).close()

    async def create(
        self,
        config: SandboxConfig | None = None,
        *,
        request_timeout: float | None = None,
        on_created: Callable[[str], None] | None = None,
    ) -> Sandbox:
        self._check()
        if request_timeout is not None and (
            not math.isfinite(request_timeout) or request_timeout <= 0
        ):
            raise ValueError("request_timeout must be finite and positive.")
        sandbox_config = config if config is not None else SandboxConfig()
        # These inputs must never be silently dropped by a transport.
        for feature, requested in (
            ("volume_mounts", bool(sandbox_config.volume_mounts)),
            (
                "network",
                sandbox_config.network is not None
                or sandbox_config.allow_internet_access is not None,
            ),
            ("auto_pause", sandbox_config.auto_pause),
        ):
            if requested and feature not in self._provider.create_options:
                raise ProviderFeatureNotSupportedError(self._provider.id, feature)
        if sandbox_config.network is not None:
            from agent_sandbox.models.network import network_create_payload

            network_create_payload(sandbox_config.network)
            if (
                sandbox_config.network.get("allow_public_traffic") is False
                and sandbox_config.secure is False
            ):
                raise ValueError("Disabling public traffic requires secure=True.")
        provider, infra, check_handle = await self._sandbox_infra()
        return await Sandbox._create_from_infra(
            provider,
            infra,
            sandbox_config,
            request_timeout=request_timeout,
            on_created=on_created,
            bound_check=check_handle,
        )

    async def connect(self, sandbox_id: str, *, traffic_access_token: str | None = None) -> Sandbox:
        target = self._sandbox_id(sandbox_id)
        provider, infra, check_handle = await self._sandbox_infra()
        return await Sandbox._connect_from_infra(
            provider,
            infra,
            target,
            traffic_access_token=traffic_access_token,
            bound_check=check_handle,
        )

    async def list(
        self, *, status: SandboxStatus | None = None, limit: int = 100, offset: int = 0
    ) -> list[SandboxInfo]:
        async with self._control_infra() as infra:
            return cast(
                "list[SandboxInfo]",
                await infra.sandbox_protocol.list(status=status, limit=limit, offset=offset),
            )

    async def get(self, sandbox_id: str) -> SandboxInfo:
        target = self._sandbox_id(sandbox_id)
        async with self._control_infra() as infra:
            info = cast("SandboxInfo", await infra.sandbox_protocol.get_info(target))
            if info.sandbox_id != target:
                raise ValueError("Provider get returned a different sandbox identity.")
            return info

    async def delete(self, sandbox_id: str) -> None:
        target = self._sandbox_id(sandbox_id)
        async with self._control_infra() as infra:
            await infra.sandbox_protocol.kill(target)

    async def set_timeout(self, sandbox_id: str, timeout: int) -> None:
        target = self._sandbox_id(sandbox_id)
        async with self._control_infra() as infra:
            await infra.sandbox_protocol.set_timeout(target, timeout)

    async def close(self) -> None:
        if self._close_task is None:
            self._check()
            self._closed = True
            self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(self._close_task)

    async def _close(self) -> None:
        try:
            try:
                async with self._session_lock:
                    closing = tuple(self._sessions.values())
                results = await asyncio.gather(
                    *(close() for close in closing), return_exceptions=True
                )
                for result in results:
                    if isinstance(result, BaseException):
                        raise result
            finally:
                if self._infra is not None:
                    await _InfraCloser(self._infra).close()
        finally:
            if self._workspace is not None:
                self._workspace.cleanup()

    async def __aenter__(self) -> ProviderClient:
        self._check()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
