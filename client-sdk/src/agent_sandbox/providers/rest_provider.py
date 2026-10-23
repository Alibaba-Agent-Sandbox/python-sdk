"""``rest`` providers: a declarative endpoint preset for any E2B-protocol backend (no code)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_sandbox.models.errors import InvalidAPIKeyError
from agent_sandbox.providers.base import Provider, ProviderInfra, consented_inherit
from agent_sandbox.providers.feature_gate import (
    FILESYSTEM_RULES,
    PROCESS_RULES,
    SANDBOX_RULES,
    gate_protocol,
)

if TYPE_CHECKING:
    from agent_sandbox.protocol.port_contract import PortAccess, PortContext
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
        self.operations = frozenset(manifest.operations["python"])
        self.workflow_inputs = frozenset(manifest.workflow_inputs)
        self.startup_modes = frozenset(manifest.startup_modes)
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

    def content_digest(self) -> str:
        from agent_sandbox.workflows.identity import snapshot_digest

        return snapshot_digest(
            {
                "native-package": super().content_digest().encode(),
                "manifest": self.manifest.sha256.encode(),
            }
        )

    async def application_endpoint(
        self, context: PortContext, port: int, protocol: Any = None
    ) -> dict[str, Any]:
        from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

        if "ports.resolve" not in self.operations:
            raise ProviderFeatureNotSupportedError(self.id, "ports.resolve")
        access = self.create_port_access(context, protocol)
        return {
            "provider_id": self.id,
            "sandbox_id": context.sandbox_id,
            "port": port,
            "url": access.get_url(port),
            "headers": access.get_server_headers(),
            "authentication_audience": "gateway",
            "path_mode": "prefix",
        }

    async def prepare_session(
        self, infra: ProviderInfra, info: Any, *, operation: str, template: str
    ) -> dict[str, Any]:
        from agent_sandbox.providers.shared.e2b.session import prepare_session

        return await prepare_session(self, info)

    def session_protocols(self, http: Any) -> dict[str, Any]:
        from agent_sandbox.providers.shared.e2b.session import session_protocols

        return session_protocols(http, operations=self.operations, provider_id=self.id)

    def create_port_access(self, context: PortContext, protocol: Any = None) -> PortAccess:
        from agent_sandbox.providers.shared.e2b.ports import WirePortAccess

        return WirePortAccess(context, server_auth=True)

    def resolve_session_url(self, info: Any, config: Any) -> str:
        from agent_sandbox.providers.shared.e2b.url import envd_url

        return str(info.envd_url or envd_url(info.sandbox_id, config.sandbox_domain))

    async def open_terminal(self, sandbox: Any, **options: Any) -> Any:
        self.require("pty")
        from agent_sandbox.providers.shared.e2b.terminal import TerminalSession

        return await TerminalSession.create(
            envd_url=sandbox.url, envd_token=sandbox._envd_token, config=sandbox._config, **options
        )

    async def build_infra(self, config: TransportConfig) -> ProviderInfra:
        from agent_sandbox.providers.shared.e2b.code_interpreter import CodeInterpreterProtocol
        from agent_sandbox.providers.shared.e2b.filesystem import FilesystemProtocol
        from agent_sandbox.providers.shared.e2b.process import ProcessProtocol
        from agent_sandbox.providers.shared.e2b.sandbox import SandboxProtocol
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

        from agent_sandbox.providers.feature_gate import gate_operation_protocols

        return gate_operation_protocols(
            ProviderInfra(
                config=config,
                auth=auth,
                http_client=http,
                sandbox_protocol=gate(SandboxProtocol(http, unknown_if_absent=True), SANDBOX_RULES),
                process_protocol=gate(ProcessProtocol(http), PROCESS_RULES),
                filesystem_protocol=gate(FilesystemProtocol(http), FILESYSTEM_RULES),
                code_interpreter_protocol=CodeInterpreterProtocol(
                    http, operations=self.operations, provider_id=self.id
                ),
            ),
            self.id,
            self.operations,
        )
