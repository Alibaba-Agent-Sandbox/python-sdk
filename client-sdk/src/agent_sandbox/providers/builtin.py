"""The built-in provider: Alibaba Cloud Express Edition (``alicloud-express``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_sandbox.providers.base import FEATURES, ConfigField, Provider, ProviderInfra
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
    features = frozenset(FEATURES)
    inherit = frozenset(GENERIC_ENDPOINT_KEYS)

    def __init__(self) -> None:
        from agent_sandbox._version import __version__

        self.version = __version__
        self.config_fields = _fields()

    def config_keys(self):  # type: ignore[no-untyped-def]
        return ALICLOUD_EXPRESS_KEYS

    async def build_infra(self, config: TransportConfig) -> ProviderInfra:
        from agent_sandbox.protocol.code_interpreter import CodeInterpreterProtocol
        from agent_sandbox.protocol.filesystem import FilesystemProtocol
        from agent_sandbox.protocol.process import ProcessProtocol
        from agent_sandbox.protocol.sandbox import SandboxProtocol
        from agent_sandbox.transport.auth import create_auth_provider
        from agent_sandbox.transport.http import HttpClient

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
            sandbox_protocol=SandboxProtocol(http),
            process_protocol=ProcessProtocol(http),
            filesystem_protocol=FilesystemProtocol(http),
            code_interpreter_protocol=CodeInterpreterProtocol(http),
        )
