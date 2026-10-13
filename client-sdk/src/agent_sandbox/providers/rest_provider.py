"""``rest`` providers: a declarative endpoint preset for any E2B-protocol backend (no code)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_sandbox.models.errors import InvalidAPIKeyError
from agent_sandbox.providers.base import Provider, ProviderInfra, consented_inherit
from agent_sandbox.providers.feature_gate import (
    CODE_RULES,
    FILESYSTEM_RULES,
    PROCESS_RULES,
    SANDBOX_RULES,
    gate_protocol,
)

if TYPE_CHECKING:
    from agent_sandbox.providers.manifest import Manifest
    from agent_sandbox.transport.config import TransportConfig


class HeaderKeyAuth:
    """Platform authentication with a bearer token or a custom API-key header."""

    def __init__(self, key: str, scheme: str = "bearer", header: str = "X-API-Key") -> None:
        if not key or not key.strip():
            raise InvalidAPIKeyError("API key cannot be empty")
        self._key = key.strip()
        self._scheme = scheme
        self._header = header

    async def get_headers(self) -> dict[str, str]:
        if self._scheme == "header":
            return {self._header: self._key}
        return {"Authorization": f"Bearer {self._key}"}

    async def refresh(self) -> None:
        return None


class RestProvider(Provider):
    """E2B-protocol backend described entirely by its manifest."""

    kind = "rest"

    def __init__(self, manifest: Manifest, receipt: dict[str, Any] | None = None) -> None:
        self.manifest = manifest
        self.receipt = receipt
        self.id = manifest.id
        self.display_name = manifest.name
        self.display_name_zh = manifest.name_zh
        self.version = manifest.version
        self.features = frozenset(manifest.features)
        self.config_fields = manifest.fields
        self.auth_any_of = manifest.auth_any_of
        self.inherit = consented_inherit(manifest.inherit, receipt)
        ep = manifest.endpoint
        defaults: dict[str, str] = {}
        if ep.get("base_url"):
            defaults["sandbox_base_url"] = str(ep["base_url"])
        if ep.get("domain"):
            defaults["sandbox_domain"] = str(ep["domain"])
        self.endpoint_defaults = defaults
        self.derive = dict(ep.get("derive", {}))
        self._auth_cfg = dict(ep.get("auth", {"scheme": "bearer"}))

    async def build_infra(self, config: TransportConfig) -> ProviderInfra:
        from agent_sandbox.protocol.code_interpreter import CodeInterpreterProtocol
        from agent_sandbox.protocol.filesystem import FilesystemProtocol
        from agent_sandbox.protocol.process import ProcessProtocol
        from agent_sandbox.protocol.sandbox import SandboxProtocol
        from agent_sandbox.transport.http import HttpClient

        self.validate_config(config)
        key = config.provider_options.get("api_key") or (
            config.sandbox_api_key if "sandbox_api_key" in self.inherit else None
        )
        if not key:
            raise InvalidAPIKeyError(
                f"Provider '{self.id}' has no API key.",
                suggestion=f"Set ABX_{self.id.upper().replace('-', '_')}_API_KEY.",
            )
        scheme = str(self._auth_cfg.get("scheme", "bearer"))
        auth = HeaderKeyAuth(str(key), scheme, str(self._auth_cfg.get("header", "X-API-Key")))
        http = HttpClient(config, auth)

        def gate(protocol: Any, rules: dict[str, tuple[str, ...]]) -> Any:
            return gate_protocol(protocol, self.id, rules, self.features)

        return ProviderInfra(
            config=config,
            auth=auth,
            http_client=http,
            sandbox_protocol=gate(SandboxProtocol(http, unknown_if_absent=True), SANDBOX_RULES),
            process_protocol=gate(ProcessProtocol(http), PROCESS_RULES),
            filesystem_protocol=gate(FilesystemProtocol(http), FILESYSTEM_RULES),
            code_interpreter_protocol=gate(CodeInterpreterProtocol(http), CODE_RULES),
        )
