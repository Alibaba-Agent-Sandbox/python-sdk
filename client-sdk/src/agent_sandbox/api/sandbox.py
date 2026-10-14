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
from typing import TYPE_CHECKING, Any, NoReturn

from agent_sandbox.api.capability import (
    ResolvedCapabilities,
    resolve_capabilities,
)
from agent_sandbox.models.sandbox import SandboxConfig, SandboxInfo, SandboxStatus
from agent_sandbox.models.template import DEFAULT_CAPABILITIES
from agent_sandbox.protocol.code_interpreter import CodeInterpreterProtocol
from agent_sandbox.protocol.filesystem import FilesystemProtocol
from agent_sandbox.protocol.process import ProcessProtocol
from agent_sandbox.protocol.sandbox import SandboxProtocol
from agent_sandbox.transport.auth import (
    AuthProvider,
    EnvdTokenManager,
    create_auth_provider,
)
from agent_sandbox.transport.config import TransportConfig, load_config
from agent_sandbox.transport.http import HttpClient
from agent_sandbox.utils.async_bridge import make_sync
from agent_sandbox.utils.config_keys import BUILTIN_PROVIDER_ID
from agent_sandbox.utils.logging import get_logger

if TYPE_CHECKING:
    import builtins
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
    from agent_sandbox.protocol.terminal import TerminalSession as TerminalSession
    from agent_sandbox.providers.base import Provider
    from agent_sandbox.transport.streaming import StreamReader as StreamReader

logger = get_logger("api.sandbox")


def _build_infra(
    *,
    api_key: str | None = None,
    api_url: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
    region: str | None = None,
    provider_options: dict[str, Any] | None = None,
) -> tuple[TransportConfig, AuthProvider, HttpClient, SandboxProtocol]:
    """Build config, auth, http client, and sandbox protocol from credentials.

    Shared helper for class methods that need standalone infra. This is the built-in
    (``alicloud-express``) path; other providers go through :func:`_provider_infra`.
    """
    config_overrides: dict[str, Any] = {}
    # Callers pass the already-resolved value (legacy ``api_key`` / ``api_url`` included).
    # ``load_config`` only honours the canonical override names.
    if api_key is not None:
        config_overrides["sandbox_api_key"] = api_key
    if api_url is not None:
        config_overrides["sandbox_base_url"] = api_url
    if access_key_id is not None:
        config_overrides["access_key_id"] = access_key_id
    if access_key_secret is not None:
        config_overrides["access_key_secret"] = access_key_secret
    if region is not None:
        config_overrides["region"] = region
    if provider_options:
        config_overrides["provider_options"] = dict(provider_options)

    config = load_config(**config_overrides)
    auth = create_auth_provider(
        api_key=config.sandbox_api_key,
        access_key_id=config.access_key_id,
        access_key_secret=config.access_key_secret,
    )
    http_client = HttpClient(config, auth)
    sandbox_protocol = SandboxProtocol(http_client)
    return config, auth, http_client, sandbox_protocol


def _same(canonical_name: str, canonical: Any, legacy_name: str, legacy: Any) -> Any:
    """Return whichever of the two equivalent kwargs is set; different values are a bug."""
    if canonical is not None and legacy is not None and canonical != legacy:
        raise ValueError(
            f"Conflicting values for '{canonical_name}' and its legacy name '{legacy_name}'; "
            "pass only one."
        )
    return canonical if canonical is not None else legacy


def _select_provider(provider: Any, sandbox_id: str | None = None) -> tuple[Any | None, str | None]:
    """Resolve the effective provider; ``(None, id)`` means the built-in default path.

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
    if pid == BUILTIN_PROVIDER_ID:
        return None, bare
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


def _envd_token(prov: Any, info: Any) -> Any:
    """A provider may accept a missing envd token and a non-default basic user."""
    from agent_sandbox.transport.auth import EnvdTokenManager

    kwargs: dict[str, Any] = {}
    if getattr(prov, "envd_allow_missing", False):
        kwargs = {
            "allow_missing": True,
            "basic_user": getattr(prov, "envd_basic_user", "root") or "root",
        }
    return EnvdTokenManager(info.envd_access_token, sandbox_id=info.sandbox_id, **kwargs)


async def _provider_infra(
    prov: Any, overrides: dict[str, Any], options: dict[str, Any] | None
) -> Any:
    """Resolve config for *prov* and build its infrastructure."""
    config = load_config(provider=prov.id, provider_options=options or {}, **overrides)
    return await prov.build_infra(config)


def _endpoint_overrides(
    *,
    api_key: str | None,
    sandbox_api_key: str | None,
    api_url: str | None,
    sandbox_base_url: str | None,
    access_key_id: str | None,
    access_key_secret: str | None,
    region: str | None,
) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for name, value in (
        ("sandbox_api_key", _same("sandbox_api_key", sandbox_api_key, "api_key", api_key)),
        ("sandbox_base_url", _same("sandbox_base_url", sandbox_base_url, "api_url", api_url)),
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
        domain: str = "e2b.dev",
        secure: bool = True,
        resolved_capabilities: ResolvedCapabilities | None = None,
        declared_capabilities: frozenset[str] | None = None,
        provider_id: str = BUILTIN_PROVIDER_ID,
        engine_data: bool = False,
    ) -> None:
        self._info = info
        self._config = config
        self._provider_id = provider_id

        # Derive envd URL when the platform response omits it (Bug 1 fix)
        if not self._info.envd_url and self._info.sandbox_id:
            self._info.envd_url = self._config.build_envd_url(self._info.sandbox_id)
        self._http_client = http_client
        self._killed = False
        self._auth = auth
        self._envd_token = envd_token
        self._domain = domain
        self._secure = secure
        self._sandbox_protocol = sandbox_protocol or SandboxProtocol(http_client)
        self._process_protocol = process_protocol or ProcessProtocol(http_client)
        self._filesystem_protocol = filesystem_protocol or FilesystemProtocol(http_client)
        self._code_interpreter_protocol = code_interpreter_protocol or CodeInterpreterProtocol(
            http_client
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
        self._engine_data = engine_data

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

        return NetworkModule(
            sandbox_id=self.id,
            domain=self._domain,
            secure=self._secure,
            access_token=self._envd_token.token if self._envd_token else None,
            capabilities=self._capabilities,
            port_resolver=self._port_resolver(),
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
            capabilities=self._capabilities,
            process_protocol=self._process_protocol,
        )

    # ---- In-sandbox SandboxServer ----

    @functools.cached_property
    def server(self) -> ServerClient:
        """Typed client for the template's SandboxServer on port 9000.

        Uses the sandbox's gateway headers.  For a server protected by its own token use
        :meth:`server_at` (``token=...``).  Discovery is explicit: call
        ``await sandbox.server.discover()`` to enable fail-fast capability checks.
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
            token: Server token (sent as ``Authorization: Bearer``), if the server has one.
            pty_port: Port of the PTY WebSocket server.
            timeout: Default per-request timeout in seconds.
        """
        from agent_sandbox.api.server_client import ServerClient

        return ServerClient(
            self.network.get_url(port),
            token=token,
            headers=self.network.get_access_headers(),
            pty_url=self.network.get_url(pty_port),
            timeout=timeout,
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
            wait: Wait until healthy.
            timeout: Seconds to wait for health.

        Raises:
            ConnectionError_: The server did not become healthy within *timeout*.
        """
        import asyncio

        from agent_sandbox.models.errors import ConnectionError_

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
        self._server_process = await self.commands.run(
            cmd, background=True, env=server_env or None, timeout=86400
        )
        client = self.server_at(port, token=token)
        if not wait:
            return client
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            if await client.health():
                return client
            if loop.time() >= deadline:
                await client.aclose()
                raise ConnectionError_(
                    f"SandboxServer did not become healthy on port {port} within {timeout:g}s",
                    suggestion="Is agent-sandbox-server installed in the template image?",
                )
            await asyncio.sleep(0.5)

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
        cpu: int | None = None,
        memory: int | None = None,
        disk: int | None = None,
        gpu: str | None = None,
        secure: bool | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
        domain: str | None = None,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        sandbox_api_key: str | None = None,
        sandbox_base_url: str | None = None,
        sandbox_domain: str | None = None,
        region: str | None = None,
        provider: str | Provider | None = None,
        provider_options: dict[str, Any] | None = None,
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
            api_key: API key override.
            api_url: Platform API URL override.
            domain: Platform domain for port URL computation.
            access_key_id: AK/SK access key ID.
            access_key_secret: AK/SK access key secret.
            sandbox_api_key: Canonical name of *api_key* (same value; a different one is an error).
            sandbox_base_url: Canonical name of *api_url*.
            sandbox_domain: Canonical name of *domain*.
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

        prov, _ = _select_provider(provider)
        if prov is not None:
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
                secure=secure,
                domain=_same("sandbox_domain", sandbox_domain, "domain", domain),
                overrides=_endpoint_overrides(
                    api_key=api_key,
                    sandbox_api_key=sandbox_api_key,
                    api_url=api_url,
                    sandbox_base_url=sandbox_base_url,
                    access_key_id=access_key_id,
                    access_key_secret=access_key_secret,
                    region=region,
                ),
                options=provider_options,
            )
        domain = _same("sandbox_domain", sandbox_domain, "domain", domain)

        config, auth, http_client, sandbox_protocol = _build_infra(
            api_key=_same("sandbox_api_key", sandbox_api_key, "api_key", api_key),
            api_url=_same("sandbox_base_url", sandbox_base_url, "api_url", api_url),
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region=region,
            provider_options=provider_options,
        )

        info = None
        try:
            from agent_sandbox.engine.client import Engine

            # The built-in provider's platform HTTP call runs inside the engine.
            info = await Engine().create(
                template,
                timeout=timeout,
                metadata=metadata or {},
                envs=envs or {},
                api_key=config.sandbox_api_key,
                api_url=config.sandbox_base_url,
                access_key_id=config.access_key_id,
                access_key_secret=config.access_key_secret,
                region=config.region or region,
                request_timeout=request_timeout,
                cpu=cpu,
                memory=memory,
                disk=disk,
                gpu=gpu,
            )

            envd_token = EnvdTokenManager(info.envd_access_token, sandbox_id=info.sandbox_id)

            logger.info("Sandbox created: %s", info.sandbox_id)

            # Resolve capabilities for the template
            resolved = await resolve_capabilities(template)

            from agent_sandbox.engine.protocols import (
                EngineFilesystemProtocol,
                EngineProcessProtocol,
            )

            return cls(
                info=info,
                config=config,
                http_client=http_client,
                auth=auth,
                envd_token=envd_token,
                sandbox_protocol=sandbox_protocol,
                process_protocol=EngineProcessProtocol(info.sandbox_id),
                filesystem_protocol=EngineFilesystemProtocol(info.sandbox_id),
                domain=domain or config.sandbox_domain,
                secure=True if secure is None else secure,
                resolved_capabilities=resolved,
                engine_data=True,
            )
        except Exception:
            if info is not None:
                try:
                    await sandbox_protocol.kill(info.sandbox_id)
                except Exception:
                    logger.debug("failed to kill orphaned sandbox %s", info.sandbox_id)
                try:
                    from agent_sandbox.engine.client import Engine

                    await Engine().op("release", sandbox_id=info.sandbox_id)
                except Exception:
                    logger.debug("engine session release failed for %s", info.sandbox_id)
            await http_client.close()
            raise

    @classmethod
    async def connect(
        cls,
        sandbox_id: str,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        domain: str | None = None,
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
            api_key: API key override.
            api_url: Platform API URL override.
            domain: Platform domain for port URL computation.
            access_key_id: AK/SK access key ID.
            access_key_secret: AK/SK access key secret.
            sandbox_api_key: Canonical name of *api_key* (same value; a different one is an error).
            sandbox_base_url: Canonical name of *api_url*.
            sandbox_domain: Canonical name of *domain*.
            region: Built-in provider region (derives the API URL and domain).
            provider: Provider id (or a ``Provider`` object). Default: ``ABX_PROVIDER`` /
                ``[core] provider`` / ``alicloud-express``. A qualified ``provider:id``
                sandbox reference also selects the provider.
            provider_options: Provider-scoped option values (see ``abx provider info``).

        Returns:
            A connected Sandbox instance.
        """
        prov, bare_id = _select_provider(provider, sandbox_id)
        domain = _same("sandbox_domain", sandbox_domain, "domain", domain)
        if prov is not None:
            return await cls._connect_via_provider(
                prov,
                bare_id or sandbox_id,
                domain=domain,
                overrides=_endpoint_overrides(
                    api_key=api_key,
                    sandbox_api_key=sandbox_api_key,
                    api_url=api_url,
                    sandbox_base_url=sandbox_base_url,
                    access_key_id=access_key_id,
                    access_key_secret=access_key_secret,
                    region=region,
                ),
                options=provider_options,
            )
        sandbox_id = bare_id or sandbox_id

        config, auth, http_client, sandbox_protocol = _build_infra(
            api_key=_same("sandbox_api_key", sandbox_api_key, "api_key", api_key),
            api_url=_same("sandbox_base_url", sandbox_base_url, "api_url", api_url),
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region=region,
            provider_options=provider_options,
        )

        try:
            info = await sandbox_protocol.connect(sandbox_id)
            envd_token = EnvdTokenManager(info.envd_access_token, sandbox_id=info.sandbox_id)

            logger.info("Connected to sandbox: %s", sandbox_id)

            # Resolve capabilities for the template
            resolved = await resolve_capabilities(info.template)

            return cls(
                info=info,
                config=config,
                http_client=http_client,
                auth=auth,
                envd_token=envd_token,
                sandbox_protocol=sandbox_protocol,
                domain=domain or config.sandbox_domain,
                resolved_capabilities=resolved,
            )
        except Exception:
            await http_client.close()
            raise

    @classmethod
    async def list(
        cls,
        *,
        status: SandboxStatus | None = None,
        limit: int = 100,
        offset: int = 0,
        api_key: str | None = None,
        api_url: str | None = None,
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
            api_key: API key override.
            api_url: Platform API URL override.
            access_key_id: AK/SK access key ID.
            access_key_secret: AK/SK access key secret.
            sandbox_api_key: Canonical name of *api_key* (same value; a different one is an error).
            sandbox_base_url: Canonical name of *api_url*.
            sandbox_domain: Canonical name of *domain*.
            region: Built-in provider region (derives the API URL and domain).
            provider: Provider id (or a ``Provider`` object). Default: ``ABX_PROVIDER`` /
                ``[core] provider`` / ``alicloud-express``. A qualified ``provider:id``
                sandbox reference also selects the provider.
            provider_options: Provider-scoped option values (see ``abx provider info``).

        Returns:
            List of SandboxInfo objects.
        """
        prov, _ = _select_provider(provider)
        if prov is not None:
            infra = await _provider_infra(
                prov,
                _endpoint_overrides(
                    api_key=api_key,
                    sandbox_api_key=sandbox_api_key,
                    api_url=api_url,
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

        config, auth, http_client, sandbox_protocol = _build_infra(
            api_key=_same("sandbox_api_key", sandbox_api_key, "api_key", api_key),
            api_url=_same("sandbox_base_url", sandbox_base_url, "api_url", api_url),
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region=region,
            provider_options=provider_options,
        )
        try:
            return await sandbox_protocol.list(status=status, limit=limit, offset=offset)
        finally:
            await http_client.close()

    @classmethod
    async def kill_by_id(
        cls,
        sandbox_id: str,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        sandbox_api_key: str | None = None,
        sandbox_base_url: str | None = None,
        sandbox_domain: str | None = None,
        region: str | None = None,
        provider: str | Provider | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> None:
        """Kill a sandbox by ID (class method, no instance required).

        Args:
            sandbox_id: The ID of the sandbox to kill.
            api_key: API key override.
            api_url: Platform API URL override.
            access_key_id: AK/SK access key ID.
            access_key_secret: AK/SK access key secret.
            sandbox_api_key: Canonical name of *api_key* (same value; a different one is an error).
            sandbox_base_url: Canonical name of *api_url*.
            sandbox_domain: Canonical name of *domain*.
            region: Built-in provider region (derives the API URL and domain).
            provider: Provider id (or a ``Provider`` object). Default: ``ABX_PROVIDER`` /
                ``[core] provider`` / ``alicloud-express``. A qualified ``provider:id``
                sandbox reference also selects the provider.
            provider_options: Provider-scoped option values (see ``abx provider info``).
        """
        prov, bare_id = _select_provider(provider, sandbox_id)
        sandbox_id = bare_id or sandbox_id
        if prov is not None:
            infra = await _provider_infra(
                prov,
                _endpoint_overrides(
                    api_key=api_key,
                    sandbox_api_key=sandbox_api_key,
                    api_url=api_url,
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

        config, auth, http_client, sandbox_protocol = _build_infra(
            api_key=_same("sandbox_api_key", sandbox_api_key, "api_key", api_key),
            api_url=_same("sandbox_base_url", sandbox_base_url, "api_url", api_url),
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region=region,
            provider_options=provider_options,
        )
        try:
            await sandbox_protocol.kill(sandbox_id)
            logger.info("Sandbox killed (by ID): %s", sandbox_id)
        finally:
            # Built-in create holds an engine session. Release is a no-op when this
            # id was never registered with the local engine.
            from agent_sandbox.engine.client import Engine

            try:
                await Engine().op("release", sandbox_id=sandbox_id)
            except Exception:
                logger.debug("engine session release failed for %s", sandbox_id)
            await http_client.close()

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
        secure: bool | None,
        domain: str | None,
        overrides: dict[str, Any],
        options: dict[str, Any] | None,
    ) -> Sandbox:
        infra = await _provider_infra(prov, overrides, options)
        closer = _InfraCloser(infra)
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
                secure=secure,
                provider_options=dict(options or {}),
            )
            info = await infra.sandbox_protocol.create(
                sandbox_config, request_timeout=request_timeout
            )
            envd_token = _envd_token(prov, info)
            logger.info("Sandbox created: %s (provider %s)", info.sandbox_id, prov.id)
            resolved = ResolvedCapabilities(
                capabilities=set(DEFAULT_CAPABILITIES) | set(prov.capabilities())
            )
            return cls(
                info=info,
                config=infra.config,
                http_client=closer,  # type: ignore[arg-type]
                auth=infra.auth,
                envd_token=envd_token,
                sandbox_protocol=infra.sandbox_protocol,
                process_protocol=infra.process_protocol,
                filesystem_protocol=infra.filesystem_protocol,
                code_interpreter_protocol=infra.code_interpreter_protocol,
                domain=domain or infra.config.sandbox_domain,
                secure=True if secure is None else secure,
                resolved_capabilities=resolved,
                declared_capabilities=frozenset(prov.capabilities()),
                provider_id=prov.id,
                engine_data=bool(getattr(prov, "uses_engine_data", False)),
            )
        except Exception:
            await closer.close()
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
            envd_token = _envd_token(prov, info)
            logger.info("Connected to sandbox: %s (provider %s)", sandbox_id, prov.id)
            resolved = ResolvedCapabilities(
                capabilities=set(DEFAULT_CAPABILITIES) | set(prov.capabilities())
            )
            return cls(
                info=info,
                config=infra.config,
                http_client=closer,  # type: ignore[arg-type]
                auth=infra.auth,
                envd_token=envd_token,
                sandbox_protocol=infra.sandbox_protocol,
                process_protocol=infra.process_protocol,
                filesystem_protocol=infra.filesystem_protocol,
                code_interpreter_protocol=infra.code_interpreter_protocol,
                domain=domain or infra.config.sandbox_domain,
                resolved_capabilities=resolved,
                declared_capabilities=frozenset(prov.capabilities()),
                provider_id=prov.id,
                engine_data=bool(getattr(prov, "uses_engine_data", False)),
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
            if self._engine_data:
                from agent_sandbox.engine.client import Engine

                try:
                    await Engine().op("release", sandbox_id=self.id)
                except Exception:
                    logger.debug("engine session release failed for %s", self.id)
            await self._http_client.close()

    async def close(self) -> None:
        """Release client-side resources (connections, plugin process); the sandbox stays up."""
        await self._http_client.close()

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
            self._info.envd_url = self._config.build_envd_url(self._info.sandbox_id)
        return self._info

    # ---- Convenience methods ----

    async def run_code(
        self,
        code: str,
        *,
        language: str = "python",
        timeout: int = 30,
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
        opener = getattr(self._process_protocol, "open_terminal", None)
        if opener is not None:
            return await opener(self.id, cols=cols, rows=rows)  # type: ignore[no-any-return]
        if self._engine_data:
            from agent_sandbox.engine.protocols import open_terminal

            return await open_terminal(self.id, cols=cols, rows=rows)  # type: ignore[return-value]
        from agent_sandbox.protocol.terminal import TerminalSession

        return await TerminalSession.create(
            envd_url=self.url,
            envd_token=self._envd_token,
            config=self._config,
            cols=cols,
            rows=rows,
            shell=shell,
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
        self._require_data_plane("named commands")
        if server_port == 9000:
            return await self.server.commands.list()
        async with self.server_at(server_port) as client:
            return await client.commands.list()

    async def run(
        self,
        name: str,
        /,
        *,
        server_port: int = 9000,
        **kwargs: Any,
    ) -> Any:
        """Call a named command registered on the sandbox's SandboxServer.

        ``sandbox.run("name", x=1)`` is ``POST /commands/name`` with *kwargs* as the JSON
        body; it returns the command's result value.  This is the only way to call a named
        command.  For a raw shell command use ``sandbox.commands.run("echo hi")``.

        The server must be running in the sandbox (see :meth:`start_server`).  A server
        protected by its own token needs ``sandbox.server_at(port, token=...).commands.run(...)``.

        Args:
            name: Registered command name.
            server_port: SandboxServer port (default 9000).  Not forwarded to the command.
            **kwargs: Command arguments, sent as the JSON body.

        Returns:
            The command's JSON result value.

        Raises:
            CommandNotFoundError: The server has no command *name*.
            ServerAPIError: Argument validation or execution failed on the server.
            ProviderFeatureNotSupportedError: The provider has no HTTP data plane.
            ConnectionError_: The SandboxServer is not reachable.
        """
        self._require_data_plane("named commands")
        if server_port == 9000:
            return await self.server.commands.run(name, **kwargs)
        async with self.server_at(server_port) as client:
            return await client.commands.run(name, **kwargs)

    def _require_data_plane(self, feature: str) -> None:
        """Named commands need an HTTP envd. Other URL schemes are refused before any I/O."""
        del feature
        url = str(self._info.envd_url or "")
        if url.startswith(("http://", "https://")):
            return
        from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

        raise ProviderFeatureNotSupportedError(self._provider_id, "sessions")

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

    create_sync = staticmethod(make_sync(create.__func__))  # type: ignore[attr-defined]
    connect_sync = staticmethod(make_sync(connect.__func__))  # type: ignore[attr-defined]
    list_sync = staticmethod(make_sync(list.__func__))  # type: ignore[attr-defined]
    kill_by_id_sync = staticmethod(make_sync(kill_by_id.__func__))  # type: ignore[attr-defined]
    kill_sync = make_sync(kill)
    close_sync = make_sync(close)
    run_code_sync = make_sync(run_code)
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
