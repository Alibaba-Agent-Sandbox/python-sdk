"""The built-in provider: Alibaba Cloud Express Edition (``alicloud-express``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_sandbox.providers.base import ConfigField, Provider, ProviderInfra
from agent_sandbox.utils.config_keys import (
    ALICLOUD_EXPRESS_KEYS,
    BUILTIN_PROVIDER_ID,
    BUILTIN_PROVIDER_NAME,
    BUILTIN_PROVIDER_NAME_ZH,
    GENERIC_ENDPOINT_KEYS,
    env_names,
)

if TYPE_CHECKING:
    from agent_sandbox.transport.config import TransportConfig


def _fields() -> tuple[ConfigField, ...]:
    return tuple(
        ConfigField(
            key=k.key,
            type=k.type,
            secret=k.secret,
            credential=k.credential,
            default=k.default,
            description=k.description,
            description_zh=k.description_zh,
            env=tuple(n for n in env_names(k) if n != k.env),
        )
        for k in ALICLOUD_EXPRESS_KEYS
    )


class AlicloudExpressProvider(Provider):
    """Wraps the SDK's existing platform behaviour; it is the default provider."""

    id = BUILTIN_PROVIDER_ID
    display_name = BUILTIN_PROVIDER_NAME
    display_name_zh = BUILTIN_PROVIDER_NAME_ZH
    kind = "builtin"
    # Explicit implementations; new registry features never grant builtin support.
    features = frozenset(
        {
            "sandbox.lifecycle",
            "sandbox.timeout",
            "exec.run",
            "exec.stream",
            "process.manage",
            "pty",
            "files.rw",
            "files.watch",
            "files.transfer",
            "code.interpret",
            "templates.read",
            "templates.build",
            "ports.url",
            "sessions",
        }
    )
    inherit = frozenset(GENERIC_ENDPOINT_KEYS)

    def __init__(self) -> None:
        from agent_sandbox._version import __version__

        self.version = __version__
        self.config_fields = _fields()

    def config_keys(self):  # type: ignore[no-untyped-def]
        return ALICLOUD_EXPRESS_KEYS

    create_options = frozenset({"volume_mounts"})

    def build_legacy_infra(self, **options: Any) -> Any:
        from agent_sandbox.providers.alicloud_express.auth import create_auth_provider
        from agent_sandbox.providers.shared.e2b.sandbox import SandboxProtocol
        from agent_sandbox.transport.config import load_config
        from agent_sandbox.transport.http import HttpClient

        config = load_config(
            provider=self.id,
            **{
                name: value
                for name, value in {
                    "sandbox_api_key": options.get("api_key"),
                    "sandbox_base_url": options.get("api_url"),
                    "access_key_id": options.get("access_key_id"),
                    "access_key_secret": options.get("access_key_secret"),
                    "region": options.get("region"),
                    "provider_options": options.get("provider_options"),
                }.items()
                if value is not None
            },
        )
        auth = create_auth_provider(
            api_key=config.sandbox_api_key,
            access_key_id=config.access_key_id,
            access_key_secret=config.access_key_secret,
        )
        http = HttpClient(config, auth)
        return config, auth, http, SandboxProtocol(http)

    def session_protocols(self, http: Any) -> dict[str, Any]:
        from agent_sandbox.providers.shared.e2b.session import session_protocols

        return session_protocols(http)

    def resolve_session_url(self, info: Any, config: Any) -> str:
        return str(info.envd_url or config.build_envd_url(info.sandbox_id))

    async def prepare_session(
        self, infra: ProviderInfra, info: Any, *, operation: str, template: str
    ) -> dict[str, Any]:
        from agent_sandbox.api.capability import resolve_capabilities_for
        from agent_sandbox.providers.shared.e2b.auth import EnvdTokenManager
        from agent_sandbox.transport.http import stream_envelope_for_envd

        http = infra.http_client
        if http is not None:
            http._stream_envelope = stream_envelope_for_envd(info.envd_version)
        resolved = await resolve_capabilities_for(
            *(
                (template, info.template, info.alias_name)
                if operation == "create"
                else (info.template, info.alias_name)
            )
        )
        binding: dict[str, Any] = {
            "envd_token": EnvdTokenManager(info.envd_access_token, sandbox_id=info.sandbox_id),
            "resolved_capabilities": resolved,
            "declared_capabilities": frozenset(resolved.capabilities),
        }
        if operation == "create":
            if http is None:
                raise RuntimeError("Express session is missing its HTTP client")
            from agent_sandbox.engine.protocols import (
                EngineFilesystemProtocol,
                EngineProcessProtocol,
            )
            from agent_sandbox.providers.shared.e2b.filesystem import FilesystemProtocol

            binding.update(
                process_protocol=EngineProcessProtocol(info.sandbox_id),
                filesystem_protocol=EngineFilesystemProtocol(
                    info.sandbox_id, bounded_reader=FilesystemProtocol(http)
                ),
                engine_data=True,
            )
        return binding

    async def open_terminal(self, sandbox: Any, **options: Any) -> Any:
        if sandbox._engine_data:
            from agent_sandbox.engine.protocols import open_terminal

            return await open_terminal(
                sandbox.id, cols=options.get("cols", 80), rows=options.get("rows", 24)
            )
        from agent_sandbox.providers.shared.e2b.terminal import TerminalSession

        return await TerminalSession.create(
            envd_url=sandbox.url, envd_token=sandbox._envd_token, config=sandbox._config, **options
        )

    async def kill_engine_resource(self, request: Any) -> None:
        from .engine import kill_engine_resource

        await kill_engine_resource(request)

    async def create_engine_session(self, request: Any) -> Any:
        from .engine import create_engine_session

        return await create_engine_session(request)

    async def build_infra(self, config: TransportConfig) -> ProviderInfra:
        from agent_sandbox.providers.alicloud_express.auth import create_auth_provider
        from agent_sandbox.providers.shared.e2b.code_interpreter import CodeInterpreterProtocol
        from agent_sandbox.providers.shared.e2b.filesystem import FilesystemProtocol
        from agent_sandbox.providers.shared.e2b.process import ProcessProtocol
        from agent_sandbox.transport.http import HttpClient

        from .lifecycle import EngineLifecycle

        auth = create_auth_provider(
            api_key=config.sandbox_api_key,
            access_key_id=config.access_key_id,
            access_key_secret=config.access_key_secret,
        )
        http = HttpClient(config, auth)
        return ProviderInfra(
            config=config,
            auth=auth,
            http_client=http,
            sandbox_protocol=EngineLifecycle(http, config),
            process_protocol=ProcessProtocol(http),
            filesystem_protocol=FilesystemProtocol(http),
            code_interpreter_protocol=CodeInterpreterProtocol(http),
        )
