"""Sandbox — the primary user-facing class.

Usage:
    async with await Sandbox.create(template="python-base") as sb:
        result = await sb.run_code("print('hello')")
        print(result.text)

    # Or without context manager:
    sb = await Sandbox.create(template="python-base")
    result = await sb.commands.run("echo hello")
    await sb.kill()
"""

from __future__ import annotations

import functools
import json
import shlex
from typing import TYPE_CHECKING, Any, Literal, NoReturn, cast

from agent_sandbox.api.capability import (
    ResolvedCapabilities,
)
from agent_sandbox.models.sandbox import (
    SandboxConfig,
    SandboxInfo,
    SandboxStatus,
    validate_volume_mounts,
)
from agent_sandbox.models.template import DEFAULT_CAPABILITIES
from agent_sandbox.providers.registry import get_provider
from agent_sandbox.transport.config import TransportConfig, load_config
from agent_sandbox.utils.async_bridge import make_classmethod_sync, make_sync
from agent_sandbox.utils.logging import get_logger

if TYPE_CHECKING:
    import builtins
    from asyncio import Task
    from collections.abc import Callable

    from agent_sandbox.api.code import CodeContextModule as CodeContextModule
    from agent_sandbox.api.commands import CommandsModule as CommandsModule
    from agent_sandbox.api.files import FilesModule as FilesModule
    from agent_sandbox.api.network import NetworkModule as NetworkModule
    from agent_sandbox.api.server_client import ServerClient as ServerClient
    from agent_sandbox.models.process import (
        CodeResult,
    )
    from agent_sandbox.models.server import ServerCommand
    from agent_sandbox.protocol.contracts import (
        CodeInterpreterProtocol,
        FilesystemProtocol,
        ProcessProtocol,
        SandboxProtocol,
    )
    from agent_sandbox.protocol.contracts import TerminalSession as TerminalSession
    from agent_sandbox.providers.base import Provider
    from agent_sandbox.transport.auth_contract import AuthProvider
    from agent_sandbox.transport.auth_contract import DataPlaneAuth as EnvdTokenManager
    from agent_sandbox.transport.http import HttpClient
    from agent_sandbox.transport.streaming import StreamReader as StreamReader

logger = get_logger("api.sandbox")


def _select_provider(provider: Any, sandbox_id: str | None = None) -> tuple[Any, str | None]:
    """Resolve a real Provider instance, including for the bundled default.

    Also splits a qualified ``provider:sandbox_id`` reference. A qualified prefix that
    contradicts an explicit *provider* raises :class:`ProviderMismatchError` (E8030).
    """
    from agent_sandbox.models.errors import ProviderMismatchError
    from agent_sandbox.providers import registry
    from agent_sandbox.providers.base import Provider

    bare = sandbox_id
    ref_provider: str | None = None
    if sandbox_id and ":" in sandbox_id:
        ref_provider, bare = registry.parse_sandbox_ref(sandbox_id)
    explicit: str | None
    if isinstance(provider, Provider):
        registry.register_provider(provider, replace=True)
        explicit = provider.id
    else:
        explicit = provider
    if explicit and ref_provider and explicit != ref_provider:
        raise ProviderMismatchError(
            f"Sandbox reference '{sandbox_id}' conflicts with provider '{explicit}'.",
            suggestion="Drop the 'provider:' prefix or the provider argument.",
        )
    pid = registry.resolve_provider_id(explicit or ref_provider)
    return registry.get_provider(pid), bare


class _InfraCloser:
    """Stands in for ``HttpClient.close()`` so :class:`Sandbox` can release provider resources."""

    def __init__(self, infra: Any) -> None:
        self._infra = infra

    async def close(self) -> None:
        if self._infra.close is not None:
            await self._infra.close()
        elif self._infra.http_client is not None:
            await self._infra.http_client.close()


async def _provider_infra(
    prov: Any, overrides: dict[str, Any], options: dict[str, Any] | None
) -> Any:
    """Resolve config for *prov* and build its infrastructure."""
    config = load_config(provider=prov.id, provider_options=options or {}, **overrides)
    return await prov.build_infra(config)


def _endpoint_overrides(
    *,
    sandbox_api_key: str | None,
    sandbox_base_url: str | None,
    access_key_id: str | None,
    access_key_secret: str | None,
    region: str | None,
) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for name, value in (
        ("sandbox_api_key", sandbox_api_key),
        ("sandbox_base_url", sandbox_base_url),
        ("access_key_id", access_key_id),
        ("access_key_secret", access_key_secret),
        ("region", region),
    ):
        if value is not None:
            overrides[name] = value
    return overrides


def _reject_signature_only_file_url(method: str) -> NoReturn:
    """The default envd refuses ``/files`` unless ``X-Access-Token`` is set.

    A browser-only signed URL was requested against a live sandbox. The data
    plane answered 403 ``AccessDenied``: ``X-Access-Token header is required``,
    and ignored the ``signature`` query parameter.
    """
    from agent_sandbox.models.errors import FileOperationError

    raise FileOperationError(
        f"{method} cannot return a URL that authorizes a file by itself. "
        "The sandbox data plane requires the X-Access-Token header on /files "
        "and does not accept a signature-only request.",
        suggestion="Use files.write(), files.read(), files.upload(), or files.download().",
    )


class Sandbox:
    """Primary user-facing class for sandbox lifecycle management.

    Provides async context manager support and convenient access to
    commands, files, network, and code sub-modules.
    """

    def __init__(
        self,
        info: SandboxInfo,
        config: TransportConfig,
        http_client: HttpClient,
        auth: AuthProvider,
        envd_token: EnvdTokenManager,
        *,
        sandbox_protocol: SandboxProtocol | None = None,
        process_protocol: ProcessProtocol | None = None,
        filesystem_protocol: FilesystemProtocol | None = None,
        code_interpreter_protocol: CodeInterpreterProtocol | None = None,
        secure: bool = True,
        domain: str | None = None,
        resolved_capabilities: ResolvedCapabilities | None = None,
        declared_capabilities: frozenset[str] | None = None,
        provider_id: str | None = None,
    ) -> None:
        self._info = info
        self._config = config
        self._provider_id = provider_id or config.provider

        from agent_sandbox.providers.registry import get_provider

        # The backend owns URL derivation and protocol construction.
        if not self._info.envd_url and self._info.sandbox_id:
            self._info.envd_url = get_provider(self._provider_id).resolve_session_url(
                self._info, self._config
            )
        self._http_client = http_client
        self._killed = False
        self._server_stream_tasks: set[Task[None]] = set()
        self._auth = auth
        self._envd_token = envd_token
        self._domain = domain if domain is not None else config.sandbox_domain
        self._secure = secure
        defaults = (
            get_provider(self._provider_id).session_protocols(http_client)
            if any(
                p is None
                for p in (
                    sandbox_protocol,
                    process_protocol,
                    filesystem_protocol,
                    code_interpreter_protocol,
                )
            )
            else {}
        )
        self._sandbox_protocol = (
            sandbox_protocol if sandbox_protocol is not None else defaults["sandbox_protocol"]
        )
        self._process_protocol = (
            process_protocol if process_protocol is not None else defaults["process_protocol"]
        )
        self._filesystem_protocol = (
            filesystem_protocol
            if filesystem_protocol is not None
            else defaults["filesystem_protocol"]
        )
        self._code_interpreter_protocol = (
            code_interpreter_protocol
            if code_interpreter_protocol is not None
            else defaults["code_interpreter_protocol"]
        )

        # Capability model
        if resolved_capabilities is not None:
            self._resolved = resolved_capabilities
        else:
            self._resolved = ResolvedCapabilities()
        self._capabilities: set[str] = set(self._resolved.capabilities)
        # What a provider declares; the module gates stay permissive so the provider's own
        # protocol gate refuses a missing feature with E8004 naming it.
        self._declared_capabilities = declared_capabilities

    # ---- Properties ----

    @property
    def id(self) -> str:
        """Sandbox ID."""
        return self._info.sandbox_id

    @property
    def provider(self) -> str:
        """Id of the provider that owns this sandbox (``alicloud-express`` by default)."""
        return self._provider_id

    @property
    def status(self) -> SandboxStatus:
        """Current sandbox status (cached, call refresh_info() to update)."""
        return self._info.status

    @property
    def url(self) -> str:
        """The envd URL for this sandbox."""
        return self._info.envd_url or ""

    @property
    def info(self) -> SandboxInfo:
        """Full sandbox info."""
        return self._info

    @property
    def capabilities(self) -> frozenset[str]:
        """Effective capability set for this sandbox."""
        return frozenset(
            self._capabilities
            if self._declared_capabilities is None
            else self._declared_capabilities
        )

    @property
    def operations(self) -> frozenset[str]:
        """Exact operations implemented by this provider's Python consumer."""
        from agent_sandbox.providers.registry import get_provider

        return frozenset(get_provider(self.provider).operations)

    # ---- Sub-modules (lazy cached properties) ----

    @functools.cached_property
    def commands(self) -> CommandsModule:
        """Commands sub-module for running shell commands."""
        from agent_sandbox.api.commands import CommandsModule

        return CommandsModule(
            envd_url=self.url,
            envd_token=self._envd_token,
            process_protocol=self._process_protocol,
            capabilities=self._capabilities,
            operations=self.operations,
            provider_id=self.provider,
        )

    @functools.cached_property
    def files(self) -> FilesModule:
        """Files sub-module for filesystem operations."""
        from agent_sandbox.api.files import FilesModule

        return FilesModule(
            envd_url=self.url,
            envd_token=self._envd_token,
            filesystem_protocol=self._filesystem_protocol,
            sandbox_protocol=self._sandbox_protocol,
            sandbox_id=self.id,
            capabilities=self._capabilities,
            provider_id=self._provider_id,
        )

    def _port_resolver(self) -> Any:
        """Bind the provider's ``ports.url`` (if it declares one) to this sandbox's id."""
        resolve = getattr(self._sandbox_protocol, "port_url", None)
        if resolve is None or not getattr(self._sandbox_protocol, "has_port_url", False):
            return None
        sandbox_id = self.id

        async def _resolver(port: int) -> tuple[str, dict[str, str]]:
            return await resolve(sandbox_id, port)  # type: ignore[no-any-return]

        return _resolver

    @functools.cached_property
    def network(self) -> NetworkModule:
        """Network sub-module for port URL calculation."""
        from agent_sandbox.api.network import NetworkModule
        from agent_sandbox.protocol.port_contract import PortContext
        from agent_sandbox.providers.registry import get_provider

        return NetworkModule(
            sandbox_id=self.id,
            domain=self._domain,
            secure=self._secure,
            access_token=self._envd_token.token if self._envd_token else None,
            capabilities=self._capabilities,
            port_resolver=self._port_resolver(),
            port_access=get_provider(self._provider_id).create_port_access(
                PortContext(
                    self.id,
                    self._domain,
                    self._secure,
                    self._envd_token.token if self._envd_token else None,
                ),
                self._sandbox_protocol,
            ),
        )

    @functools.cached_property
    def code(self) -> CodeContextModule:
        """Code sub-module for code interpretation."""
        from agent_sandbox.api.code import CodeContextModule

        return CodeContextModule(
            sandbox_id=self.id,
            envd_url=self.url,
            envd_token=self._envd_token,
            code_interpreter_protocol=self._code_interpreter_protocol,
            operations=self.operations,
            provider_id=self.provider,
        )

    # ---- In-sandbox SandboxServer ----

    @functools.cached_property
    def server(self) -> ServerClient:
        """Typed client for the template's SandboxServer on port 9000.

        Does not send the sandbox access token. On Express that header is
        forwarded to the process, and an ``agent-sandbox-server`` with no
        ``ABX_SERVER_TOKEN`` answers HTTP 401. Pass ``token=`` to
        :meth:`server_at` when the server has its own token. Discovery is
        explicit: call ``await sandbox.server.discover()``.
        """
        return self.server_at(9000)

    def server_at(
        self,
        port: int = 9000,
        *,
        token: str | None = None,
        pty_port: int = 9001,
        timeout: float = 30.0,
    ) -> ServerClient:
        """A :class:`ServerClient` bound to *port* of this sandbox.

        Args:
            port: SandboxServer HTTP port.
            token: Server token (sent as ``Authorization: Bearer``) when the server
                was started with ``ABX_SERVER_TOKEN``. Omit it on Express: the
                sandbox access token is not a server credential, and sending it
                is HTTP 401.
            pty_port: Port of the PTY WebSocket server.
            timeout: Default per-request timeout in seconds.
        """
        from agent_sandbox.api.server_client import ServerClient

        return ServerClient(
            self.network.get_url(port),
            token=token,
            headers=self.network.get_server_headers() or None,
            pty_url=self.network.get_url(pty_port),
            timeout=timeout,
        )

    async def application_client(
        self, port: int = 9000, *, token: str | None = None, timeout: float = 30.0
    ) -> ServerClient:
        """Resolve application HTTP independently of the sandbox control/data transport.

        The provider supplies this sandbox's port URL and minimal gateway headers.
        Application credentials are explicit and never inherited from API keys.
        """
        from datetime import datetime, timezone

        from agent_sandbox.api.server_client import ServerClient
        from agent_sandbox.protocol.port_contract import PortContext
        from agent_sandbox.providers.registry import get_provider

        descriptor = await get_provider(self.provider).application_endpoint(
            PortContext(
                self.id,
                self._domain,
                self._secure,
                self._envd_token.token if self._envd_token else None,
            ),
            port,
            self._sandbox_protocol,
        )
        if (
            not isinstance(descriptor, dict)
            or type(descriptor.get("port")) is not int
            or any(
                descriptor.get(key) != expected
                for key, expected in {
                    "provider_id": self.provider,
                    "sandbox_id": self.id,
                    "port": port,
                    "authentication_audience": "gateway",
                }.items()
            )
        ):
            raise ValueError("Application endpoint does not match this provider, sandbox and port")
        expires = descriptor.get("expires_at")
        if expires is not None:
            if not isinstance(expires, str):
                raise ValueError("Endpoint expiry must be an ISO 8601 timestamp")
            deadline = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if deadline.tzinfo is None or deadline <= datetime.now(timezone.utc):
                raise ValueError("Application endpoint has expired")
        url, headers = descriptor.get("url"), descriptor.get("headers")
        if not isinstance(url, str) or not isinstance(headers, dict):
            raise ValueError("Application endpoint URL and gateway headers are required")
        path_mode = descriptor.get("path_mode")
        if not isinstance(path_mode, str):
            raise ValueError("Application endpoint path mode is required")
        return ServerClient(
            url,
            headers=headers,
            token=token,
            timeout=timeout,
            path_mode=path_mode,
            expires_at=expires,
        )

    async def start_server(
        self,
        *,
        port: int = 9000,
        commands: str | None = None,
        policy: dict[str, Any] | str | None = None,
        token: str | None = None,
        env: dict[str, str] | None = None,
        command: str | None = None,
        wait: bool = True,
        timeout: float = 30.0,
    ) -> ServerClient:
        """Start ``agent-sandbox-server`` inside the sandbox and return a client for it.

        Runs the server as a background command over envd (the template must contain
        ``agent-sandbox-server``) and, with ``wait=True``, polls ``/health`` until it answers.

        Args:
            port: HTTP port (default 9000).
            commands: Python file/module in the sandbox registering custom commands.
            policy: Policy dict (serialised into ``ABX_SERVER_POLICY``) or a preset name.
            token: Sets ``ABX_SERVER_TOKEN`` for the server and authenticates the client.
            env: Extra environment variables for the server process.
            command: Full command line override (default ``agent-sandbox-server serve``).
            wait: Wait until healthy. Process startup is acknowledged even when False.
            timeout: Seconds to wait for health.

        Raises:
            ConnectionError_: The server did not become healthy within *timeout*.
        """
        import asyncio

        from agent_sandbox.models.errors import ConnectionError_
        from agent_sandbox.models.process import ProcessChunkType
        from agent_sandbox.transport.streaming import StreamReader

        server_env: dict[str, str] = dict(env or {})
        if token:
            server_env["ABX_SERVER_TOKEN"] = token
        if isinstance(policy, dict):
            server_env["ABX_SERVER_POLICY"] = json.dumps(policy)
        cmd = command or f"agent-sandbox-server serve --port {port}"
        if command is None:
            if commands:
                cmd += f" --commands {shlex.quote(commands)}"
            if isinstance(policy, str):
                cmd += f" --preset {shlex.quote(policy)}"
        client = await self.application_client(port, token=token)
        stream = await self.commands._start_for_startup(cmd, env=server_env or None, timeout=86400)
        if not isinstance(stream, StreamReader):
            raise ConnectionError_("SandboxServer did not return a process stream")
        self._server_process = stream
        started: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

        async def drain() -> None:
            try:
                async for chunk in stream:
                    if chunk.pid and not started.done():
                        started.set_result(True)
                    if chunk.type == ProcessChunkType.EXIT:
                        break
            except Exception:
                # Process output and transport errors can contain command secrets.
                logger.debug("SandboxServer process stream stopped")
            finally:
                if not started.done():
                    started.set_result(False)
                await stream.cancel()

        task = asyncio.create_task(drain())
        self._server_stream_tasks.add(task)
        task.add_done_callback(self._server_stream_tasks.discard)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        try:
            try:
                acknowledged = await asyncio.wait_for(started, timeout)
            except asyncio.TimeoutError:
                raise ConnectionError_(
                    "SandboxServer process did not acknowledge startup"
                ) from None
            if not acknowledged or task.done():
                raise ConnectionError_(
                    "SandboxServer process stopped before startup",
                    suggestion="Check the server executable and process PATH, or pass command= "
                    "with an absolute path or python3 -m agent_sandbox.server serve.",
                )
            if not wait:
                return client
            while True:
                if task.done():
                    raise ConnectionError_("SandboxServer process stopped before becoming healthy")
                if await client.health():
                    if task.done():
                        raise ConnectionError_(
                            "SandboxServer process stopped before becoming healthy"
                        )
                    return client
                if loop.time() >= deadline:
                    raise ConnectionError_(
                        f"SandboxServer did not become healthy on port {port} within {timeout:g}s",
                        suggestion="Is agent-sandbox-server installed in the template image?",
                    )
                await asyncio.sleep(0.5)
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self._server_stream_tasks.discard(task)
            await client.aclose()
            raise

    # ---- Factory classmethods ----

    @classmethod
    async def create(
        cls,
        template: str = "base",
        *,
        timeout: int = 300,
        request_timeout: float | None = None,
        metadata: dict[str, str] | None = None,
        envs: dict[str, str] | None = None,
        volume_mounts: dict[str, str] | None = None,
        cpu: int | None = None,
        memory: int | None = None,
        disk: int | None = None,
        gpu: str | None = None,
        secure: bool | None = None,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        sandbox_api_key: str | None = None,
        sandbox_base_url: str | None = None,
        sandbox_domain: str | None = None,
        region: str | None = None,
        provider: str | Provider | None = None,
        provider_options: dict[str, Any] | None = None,
        on_created: Callable[[str], None] | None = None,
    ) -> Sandbox:
        """Create a new sandbox.

        Args:
            template: Sandbox template name.
            timeout: Sandbox lifetime (TTL) in seconds — how long the sandbox
                stays alive on the platform.  This is **not** an HTTP timeout;
                use *request_timeout* to bound how long the client waits for
                the create HTTP response.
            request_timeout: Per-request HTTP timeout override, in seconds,
                applied only to the ``POST /sandboxes`` create call.  When
                *None* (default), the client-level default is used unchanged
                (``SANDBOX_HTTP_TIMEOUT`` / ``Config.http_timeout``).  Aligns
                with the E2B SDK's ``request_timeout``.  Note: raising this
                value does not work around platform-side create stalls — it
                only controls how long the client waits before timing out.
            metadata: Arbitrary metadata key-value pairs.
            volume_mounts: Absolute sandbox paths mapped to existing Volume names,
                for example ``{"/mnt/data": "my-volume"}``. Supported only by the
                built-in provider; the Volume and API key must belong to the same Team.
            envs: Environment variables injected into the envd root process.
                These are inherited by all subsequent ``commands.run()``,
                ``run_code()``, and terminal sessions.  Per-call overrides
                can be passed via ``commands.run(env=)`` or
                ``run_code(envs=)``.  Note: envd uses **direct exec**;
                shell expansion (``$VAR``, pipes, redirects) requires
                ``sh -c '...'``.  Use ``printenv VAR`` to read a single
                variable.  See the Environment Variables guide for details.
            cpu: Number of CPU cores (optional).
            memory: Memory in MB (optional).
            disk: Disk size in MB (optional).
            gpu: GPU specification, e.g. ``'A10'`` (optional).
            secure: Whether to enable secure mode. ``None`` (default) means "not specified":
                the built-in provider behaves as ``True`` (port access requires an access
                token) and plugin providers receive no ``secure`` hint, so their own default
                applies. Pass ``True``/``False`` to send an explicit request.
            access_key_id: AK/SK access key ID.
            access_key_secret: AK/SK access key secret.
            sandbox_api_key: Sandbox platform API key override.
            sandbox_base_url: Sandbox platform API base URL override.
            sandbox_domain: Provider data-plane domain.
            region: Built-in provider region (derives the API URL and domain).
            provider: Provider id (or a ``Provider`` object). Default: ``ABX_PROVIDER`` /
                ``[core] provider`` / ``alicloud-express``. A qualified ``provider:id``
                sandbox reference also selects the provider.
            provider_options: Provider-scoped option values (see ``abx provider info``). Besides
                configuring the provider, exec providers receive them (secret fields excluded)
                as ``options`` in ``sandbox.create``, so a plugin can honour per-create
                settings such as a network policy or an image pull policy.

        Returns:
            A connected Sandbox instance.

        Raises:
            ValueError: If *request_timeout* is not None and not a positive
                number.
        """
        if request_timeout is not None and request_timeout <= 0:
            raise ValueError(
                f"request_timeout must be a positive number of seconds, got {request_timeout!r}"
            )

        mounts = validate_volume_mounts(volume_mounts)
        prov, _ = _select_provider(provider)
        if mounts and "volume_mounts" not in prov.create_options:
            from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

            raise ProviderFeatureNotSupportedError(prov.id, "volume_mounts")
        return await cls._create_via_provider(
            prov,
            template=template,
            timeout=timeout,
            request_timeout=request_timeout,
            metadata=metadata,
            envs=envs,
            cpu=cpu,
            memory=memory,
            disk=disk,
            gpu=gpu,
            volume_mounts=mounts,
            secure=secure,
            domain=sandbox_domain,
            overrides=_endpoint_overrides(
                sandbox_api_key=sandbox_api_key,
                sandbox_base_url=sandbox_base_url,
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                region=region,
            ),
            options=provider_options,
            on_created=on_created,
        )

    @classmethod
    async def connect(
        cls,
        sandbox_id: str,
        *,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        sandbox_api_key: str | None = None,
        sandbox_base_url: str | None = None,
        sandbox_domain: str | None = None,
        region: str | None = None,
        provider: str | Provider | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> Sandbox:
        """Connect to an existing sandbox by ID.

        Args:
            sandbox_id: The ID of the sandbox to connect to.
            access_key_id: AK/SK access key ID.
            access_key_secret: AK/SK access key secret.
            sandbox_api_key: Sandbox platform API key override.
            sandbox_base_url: Sandbox platform API base URL override.
            sandbox_domain: Provider data-plane domain.
            region: Built-in provider region (derives the API URL and domain).
            provider: Provider id (or a ``Provider`` object). Default: ``ABX_PROVIDER`` /
                ``[core] provider`` / ``alicloud-express``. A qualified ``provider:id``
                sandbox reference also selects the provider.
            provider_options: Provider-scoped option values (see ``abx provider info``).

        Returns:
            A connected Sandbox instance.
        """
        prov, bare_id = _select_provider(provider, sandbox_id)
        return await cls._connect_via_provider(
            prov,
            bare_id or sandbox_id,
            domain=sandbox_domain,
            overrides=_endpoint_overrides(
                sandbox_api_key=sandbox_api_key,
                sandbox_base_url=sandbox_base_url,
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                region=region,
            ),
            options=provider_options,
        )

    @classmethod
    async def list(
        cls,
        *,
        status: SandboxStatus | None = None,
        limit: int = 100,
        offset: int = 0,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        sandbox_api_key: str | None = None,
        sandbox_base_url: str | None = None,
        sandbox_domain: str | None = None,
        region: str | None = None,
        provider: str | Provider | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> list[SandboxInfo]:
        """List sandboxes (class method, no instance required).

        Args:
            status: Filter by sandbox status.
            limit: Maximum number of sandboxes to return.
            offset: Pagination offset.
            access_key_id: AK/SK access key ID.
            access_key_secret: AK/SK access key secret.
            sandbox_api_key: Sandbox platform API key override.
            sandbox_base_url: Sandbox platform API base URL override.
            sandbox_domain: Provider data-plane domain.
            region: Built-in provider region (derives the API URL and domain).
            provider: Provider id (or a ``Provider`` object). Default: ``ABX_PROVIDER`` /
                ``[core] provider`` / ``alicloud-express``. A qualified ``provider:id``
                sandbox reference also selects the provider.
            provider_options: Provider-scoped option values (see ``abx provider info``).

        Returns:
            List of SandboxInfo objects.
        """
        prov, _ = _select_provider(provider)
        infra = await _provider_infra(
            prov,
            _endpoint_overrides(
                sandbox_api_key=sandbox_api_key,
                sandbox_base_url=sandbox_base_url,
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                region=region,
            ),
            provider_options,
        )
        try:
            return await infra.sandbox_protocol.list(status=status, limit=limit, offset=offset)  # type: ignore[no-any-return]
        finally:
            await _InfraCloser(infra).close()

    @classmethod
    async def get_info_by_id(
        cls,
        sandbox_id: str,
        *,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        sandbox_api_key: str | None = None,
        sandbox_base_url: str | None = None,
        region: str | None = None,
        provider: str | Provider | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> SandboxInfo:
        """Fetch metadata without connecting, resuming, renewing or adopting the sandbox.

        Credential/provider overrides follow ``kill_by_id``. This method only
        queries the control plane and does not create an envd/data-plane client.

        Args:
            sandbox_id: Existing sandbox ID, optionally qualified with ``provider:``.
        Returns:
            Current provider-reported sandbox metadata.
        """
        result = await cls._control_plane_by_id(
            sandbox_id,
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            sandbox_api_key=sandbox_api_key,
            sandbox_base_url=sandbox_base_url,
            region=region,
            provider=provider,
            provider_options=provider_options,
            operation="get_info",
        )
        return cast("SandboxInfo", result)

    @classmethod
    async def set_timeout_by_id(
        cls,
        sandbox_id: str,
        timeout: int,
        *,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        sandbox_api_key: str | None = None,
        sandbox_base_url: str | None = None,
        region: str | None = None,
        provider: str | Provider | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> None:
        """Set timeout directly without a connect operation that could resume the sandbox.

        Credential/provider overrides follow ``kill_by_id``.

        Args:
            sandbox_id: Existing sandbox ID, optionally qualified with ``provider:``.
            timeout: Remaining sandbox lifetime from now, in seconds.
        """
        await cls._control_plane_by_id(
            sandbox_id,
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            sandbox_api_key=sandbox_api_key,
            sandbox_base_url=sandbox_base_url,
            region=region,
            provider=provider,
            provider_options=provider_options,
            operation="set_timeout",
            timeout=timeout,
        )

    @classmethod
    async def _control_plane_by_id(
        cls,
        sandbox_id: str,
        *,
        operation: str,
        timeout: int | None = None,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        sandbox_api_key: str | None = None,
        sandbox_base_url: str | None = None,
        region: str | None = None,
        provider: str | Provider | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> Any:
        prov, bare = _select_provider(provider, sandbox_id)
        target = bare or sandbox_id
        closer: _InfraCloser | HttpClient
        infra = await _provider_infra(
            prov,
            _endpoint_overrides(
                sandbox_api_key=sandbox_api_key,
                sandbox_base_url=sandbox_base_url,
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                region=region,
            ),
            provider_options,
        )
        protocol = infra.sandbox_protocol
        closer = _InfraCloser(infra)
        try:
            if operation == "get_info":
                return await protocol.get_info(target)
            assert timeout is not None
            return await protocol.set_timeout(target, timeout)
        finally:
            await closer.close()

    @classmethod
    async def kill_by_id(
        cls,
        sandbox_id: str,
        *,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        sandbox_api_key: str | None = None,
        sandbox_base_url: str | None = None,
        region: str | None = None,
        provider: str | Provider | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> None:
        """Kill a sandbox by ID (class method, no instance required).

        Args:
            sandbox_id: The ID of the sandbox to kill.
            access_key_id: AK/SK access key ID.
            access_key_secret: AK/SK access key secret.
            sandbox_api_key: Sandbox platform API key override.
            sandbox_base_url: Sandbox platform API base URL override.
            region: Built-in provider region (derives the API URL and domain).
            provider: Provider id (or a ``Provider`` object). Default: ``ABX_PROVIDER`` /
                ``[core] provider`` / ``alicloud-express``. A qualified ``provider:id``
                sandbox reference also selects the provider.
            provider_options: Provider-scoped option values (see ``abx provider info``).
        """
        prov, bare_id = _select_provider(provider, sandbox_id)
        sandbox_id = bare_id or sandbox_id
        infra = await _provider_infra(
            prov,
            _endpoint_overrides(
                sandbox_api_key=sandbox_api_key,
                sandbox_base_url=sandbox_base_url,
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                region=region,
            ),
            provider_options,
        )
        try:
            await infra.sandbox_protocol.kill(sandbox_id)
            logger.info("Sandbox killed (by ID): %s", sandbox_id)
        finally:
            await _InfraCloser(infra).close()
        return

    @classmethod
    async def _create_via_provider(
        cls,
        prov: Any,
        *,
        template: str,
        timeout: int,
        request_timeout: float | None,
        metadata: dict[str, str] | None,
        envs: dict[str, str] | None,
        cpu: int | None,
        memory: int | None,
        disk: int | None,
        gpu: str | None,
        volume_mounts: dict[str, str],
        secure: bool | None,
        domain: str | None,
        overrides: dict[str, Any],
        options: dict[str, Any] | None,
        on_created: Callable[[str], None] | None = None,
    ) -> Sandbox:
        infra = await _provider_infra(prov, overrides, options)
        closer = _InfraCloser(infra)
        created: SandboxInfo | None = None
        try:
            sandbox_config = SandboxConfig(  # type: ignore[call-arg]
                template=template,
                timeout=timeout,
                metadata=metadata or {},
                env_vars=envs or {},
                cpu=cpu,
                memory=memory,
                disk=disk,
                gpu=gpu,
                volume_mounts=volume_mounts,
                secure=secure,
                provider_options=dict(options or {}),
            )
            info = await infra.sandbox_protocol.create(
                sandbox_config, request_timeout=request_timeout
            )
            created = info
            if on_created is not None:
                on_created(info.sandbox_id)
            binding = await prov.prepare_session(infra, info, operation="create", template=template)
            logger.info("Sandbox created: %s (provider %s)", info.sandbox_id, prov.id)
            resolved = ResolvedCapabilities(
                capabilities=set(DEFAULT_CAPABILITIES) | set(prov.capabilities())
            )
            return cls(
                info=info,
                config=infra.config,
                http_client=closer,  # type: ignore[arg-type]
                auth=infra.auth,
                envd_token=binding.pop("envd_token"),
                sandbox_protocol=infra.sandbox_protocol,
                process_protocol=binding.pop("process_protocol", infra.process_protocol),
                filesystem_protocol=binding.pop("filesystem_protocol", infra.filesystem_protocol),
                code_interpreter_protocol=binding.pop(
                    "code_interpreter_protocol", infra.code_interpreter_protocol
                ),
                domain=domain or infra.config.sandbox_domain,
                secure=True if secure is None else secure,
                resolved_capabilities=binding.pop("resolved_capabilities", resolved),
                declared_capabilities=binding.pop(
                    "declared_capabilities", frozenset(prov.capabilities())
                ),
                provider_id=prov.id,
                **binding,
            )
        except BaseException as exc:
            if created is not None:
                exc.owned_resource = {"provider_id": prov.id, "sandbox_id": created.sandbox_id}  # type: ignore[attr-defined]
                try:
                    await infra.sandbox_protocol.kill(created.sandbox_id)
                except BaseException:
                    exc.resource_cleanup_complete = False  # type: ignore[attr-defined]
                else:
                    exc.resource_cleanup_complete = True  # type: ignore[attr-defined]
            try:
                await closer.close()
            except BaseException:
                exc.connection_cleanup_failed = True  # type: ignore[attr-defined]
            raise

    @classmethod
    async def _connect_via_provider(
        cls,
        prov: Any,
        sandbox_id: str,
        *,
        domain: str | None,
        overrides: dict[str, Any],
        options: dict[str, Any] | None,
    ) -> Sandbox:
        infra = await _provider_infra(prov, overrides, options)
        closer = _InfraCloser(infra)
        try:
            info = await infra.sandbox_protocol.connect(sandbox_id)
            binding = await prov.prepare_session(
                infra, info, operation="connect", template=info.template
            )
            logger.info("Connected to sandbox: %s (provider %s)", sandbox_id, prov.id)
            resolved = ResolvedCapabilities(
                capabilities=set(DEFAULT_CAPABILITIES) | set(prov.capabilities())
            )
            return cls(
                info=info,
                config=infra.config,
                http_client=closer,  # type: ignore[arg-type]
                auth=infra.auth,
                envd_token=binding.pop("envd_token"),
                sandbox_protocol=infra.sandbox_protocol,
                process_protocol=binding.pop("process_protocol", infra.process_protocol),
                filesystem_protocol=binding.pop("filesystem_protocol", infra.filesystem_protocol),
                code_interpreter_protocol=binding.pop(
                    "code_interpreter_protocol", infra.code_interpreter_protocol
                ),
                domain=domain or infra.config.sandbox_domain,
                resolved_capabilities=binding.pop("resolved_capabilities", resolved),
                declared_capabilities=binding.pop(
                    "declared_capabilities", frozenset(prov.capabilities())
                ),
                provider_id=prov.id,
                **binding,
            )
        except Exception:
            await closer.close()
            raise

    # ---- Lifecycle ----

    async def kill(self) -> None:
        """Kill the sandbox and release resources.

        A second call is a no-op. The first call closes the client, so retrying
        the provider would otherwise see a dead plugin process.
        """
        if self._killed:
            return
        try:
            await self._sandbox_protocol.kill(self.id)
            self._killed = True
            logger.info("Sandbox killed: %s", self.id)
        finally:
            await self._close_server_streams()
            await self._http_client.close()

    async def close(self) -> None:
        """Release client-side resources (connections, plugin process); the sandbox stays up."""
        await self._close_server_streams()
        await self._http_client.close()

    async def _close_server_streams(self) -> None:
        """Release local readers without killing the remote server or sandbox."""
        import asyncio

        tasks = list(self._server_stream_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._server_stream_tasks.difference_update(tasks)

    async def set_timeout(self, timeout: int) -> None:
        """Update sandbox timeout."""
        await self._sandbox_protocol.set_timeout(self.id, timeout)

    async def is_running(self) -> bool:
        """Check if the sandbox is currently running (makes API call).

        Fetches current info from the platform and checks status.
        """
        return await self._sandbox_protocol.is_running(self.id)

    async def pause(self) -> None:
        """Pause the sandbox.

        # 注意：REST 路径基于 E2B SDK 逆向推断，未经官方文档确认
        """
        await self._sandbox_protocol.pause(self.id)
        logger.info("Sandbox paused: %s", self.id)

    async def resume(self) -> None:
        """Resume a paused sandbox.

        # 注意：REST 路径基于 E2B SDK 逆向推断，未经官方文档确认
        """
        await self._sandbox_protocol.resume(self.id)
        logger.info("Sandbox resumed: %s", self.id)

    async def refresh_info(self) -> SandboxInfo:
        """Refresh sandbox info from the platform."""
        self._info = await self._sandbox_protocol.get_info(self.id)
        # Re-derive envd URL if the platform still omits it
        if not self._info.envd_url and self._info.sandbox_id:
            self._info.envd_url = get_provider(self._provider_id).resolve_session_url(
                self._info, self._config
            )
        return self._info

    # ---- Convenience methods ----

    async def run_code(
        self,
        code: str,
        *,
        language: str = "python",
        timeout: int = 30,
        context_id: str | None = None,
        mode: Literal["stateless", "default-context"] = "stateless",
        envs: dict[str, str] | None = None,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
        on_result: Callable[..., None] | None = None,
    ) -> CodeResult:
        """Run code in the sandbox using the code interpreter.

        Args:
            code: Source code to execute.
            language: Programming language (default: python).
            timeout: Execution timeout in seconds.
            envs: Optional environment variables for this execution
                (envd scope, single-invocation lifetime).  These are
                merged with creation-time envs for this call only.
            on_stdout: Optional callback invoked with stdout content.
            on_stderr: Optional callback invoked with stderr content.
            on_result: Optional callback invoked with the execution result dict.

        Returns:
            CodeResult with stdout, stderr, and output files.
        """
        return await self.code.run(
            code,
            language=language,
            timeout=timeout,
            context_id=context_id,
            mode=mode,
            envs=envs,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            on_result=on_result,
        )

    async def get_terminal(
        self,
        *,
        cols: int = 80,
        rows: int = 24,
        shell: str = "/bin/bash",
    ) -> TerminalSession:
        """Open an interactive PTY terminal session.

        Returns a :class:`TerminalSession` connected via WebSocket.

        Args:
            cols: Terminal columns (default 80).
            rows: Terminal rows (default 24).
            shell: Shell binary (default ``/bin/bash``).
        """
        from agent_sandbox.providers.registry import get_provider

        return cast(
            "TerminalSession",
            await get_provider(self._provider_id).open_terminal(
                self, cols=cols, rows=rows, shell=shell
            ),
        )

    # ---- Named commands (registered on the in-sandbox SandboxServer) ----

    async def list_commands(
        self,
        *,
        server_port: int = 9000,
    ) -> builtins.list[ServerCommand]:
        """List the named commands registered on the sandbox's SandboxServer.

        Commands are registered in the sandbox with ``@sandbox.register`` (or the server's
        ``CommandRegistry``); this is ``GET /commands`` on *server_port*.

        Raises:
            ProviderFeatureNotSupportedError: The provider has no HTTP data plane.
            ConnectionError_: The SandboxServer is not reachable.
        """
        async with await self.application_client(server_port) as client:
            return await client.commands.list()

    async def run(
        self,
        name: str,
        /,
        *,
        server_port: int = 9000,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Call a named command registered on the sandbox's SandboxServer.

        ``await sandbox.run("hello", name="Bob")`` is ``POST /commands/hello`` and returns
        the command's value (a string, number, list, or object). This is the one call that
        runs a template command. A raw shell command is ``sandbox.commands.run``, which can
        stream with ``on_stdout``. Named commands return when the function returns; pass
        ``timeout`` when that may take longer than the default 30s HTTP timeout.

        The server must be running in the sandbox (see :meth:`start_server`).  A server
        protected by its own token needs ``sandbox.server_at(port, token=...).commands.run(...)``.

        Args:
            name: Registered command name.
            server_port: SandboxServer port (default 9000).  Not forwarded to the command.
            timeout: HTTP timeout in seconds. Not forwarded to the command.
            **kwargs: Command arguments, sent as the JSON body.

        Returns:
            The command's JSON result value.

        Raises:
            CommandNotFoundError: The server has no command *name*.
            CommandArgumentError: The arguments failed validation.
            CommandExecutionError: The command function raised.
            ProviderFeatureNotSupportedError: The provider has no HTTP data plane.
            ConnectionError_: The SandboxServer is not reachable.
        """
        async with await self.application_client(server_port) as client:
            return await client.commands.run(name, timeout=timeout, **kwargs)

    # ---- E2B-shaped URL stubs ----

    async def upload_url(self, path: str, **_kwargs: object) -> str:
        """E2B ``Sandbox.upload_url``. This data plane does not accept a signature-only URL."""
        _ = path
        _reject_signature_only_file_url("upload_url")

    async def download_url(self, path: str, **_kwargs: object) -> str:
        """E2B ``Sandbox.download_url``. This data plane does not accept a signature-only URL."""
        _ = path
        _reject_signature_only_file_url("download_url")

    async def get_upload_url(self, path: str, **_kwargs: object) -> str:
        """Alias of :meth:`upload_url`."""
        _ = path
        _reject_signature_only_file_url("get_upload_url")

    async def get_download_url(self, path: str, **_kwargs: object) -> str:
        """Alias of :meth:`download_url`."""
        _ = path
        _reject_signature_only_file_url("get_download_url")

    # ---- Context manager ----

    async def __aenter__(self) -> Sandbox:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            await self.kill()
        except Exception:
            logger.warning("Error during sandbox cleanup on __aexit__", exc_info=True)

    # ---- Sync variants ----

    create_sync = make_classmethod_sync(create.__func__)  # type: ignore[attr-defined]
    connect_sync = make_classmethod_sync(connect.__func__)  # type: ignore[attr-defined]
    list_sync = make_classmethod_sync(list.__func__)  # type: ignore[attr-defined]
    kill_by_id_sync = make_classmethod_sync(kill_by_id.__func__)  # type: ignore[attr-defined]
    kill_sync = make_sync(kill)
    close_sync = make_sync(close)
    run_code_sync = make_sync(run_code)
    get_info_by_id_sync = make_classmethod_sync(get_info_by_id.__func__)  # type: ignore[attr-defined]
    set_timeout_by_id_sync = make_classmethod_sync(set_timeout_by_id.__func__)  # type: ignore[attr-defined]
    set_timeout_sync = make_sync(set_timeout)
    is_running_sync = make_sync(is_running)
    pause_sync = make_sync(pause)
    resume_sync = make_sync(resume)
    refresh_info_sync = make_sync(refresh_info)
    get_terminal_sync = make_sync(get_terminal)
    upload_url_sync = make_sync(upload_url)
    download_url_sync = make_sync(download_url)
    get_upload_url_sync = make_sync(get_upload_url)
    get_download_url_sync = make_sync(get_download_url)
    run_sync = make_sync(run)
    list_commands_sync = make_sync(list_commands)

    def __repr__(self) -> str:
        return f"<Sandbox id={self.id!r} status={self.status.value!r}>"


# Avoid circular imports — these are used only for type annotation in cached_property
