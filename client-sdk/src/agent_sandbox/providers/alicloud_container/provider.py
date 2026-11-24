"""Built-in Python implementation for a configured ACS/ACK sandbox-manager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import SplitResult, urlsplit

from agent_sandbox._version import __version__
from agent_sandbox.models.errors import ProviderConfigError
from agent_sandbox.providers.base import ConfigField, Provider, ProviderInfra
from agent_sandbox.providers.feature_gate import gate_operation_protocols
from agent_sandbox.providers.rest_provider import HeaderKeyAuth
from agent_sandbox.providers.shared.e2b.filesystem import FilesystemProtocol
from agent_sandbox.providers.shared.e2b.process import ProcessProtocol
from agent_sandbox.transport.http import HttpClient

from .interpreter import JupyterProtocol
from .sandbox import PROVIDER_ID, ContainerSandboxProtocol, Gateway

if TYPE_CHECKING:
    from agent_sandbox.protocol.port_contract import PortContext
    from agent_sandbox.transport.config import TransportConfig


def _url(value: str, field: str) -> SplitResult:
    try:
        parts = urlsplit(value)
        if (
            parts.scheme in {"http", "https"}
            and parts.hostname
            and parts.username is None
            and parts.password is None
            and parts.port != 0
            and not parts.query
            and not parts.fragment
            and "\\" not in value
            and not any(c.isspace() for c in value)
        ):
            return parts
    except ValueError:
        pass
    raise ProviderConfigError(f"Provide a valid HTTP(S) Container Edition {field}.")


def _option(config: TransportConfig, name: str) -> str:
    value = config.provider_options.get(name, "")
    if not isinstance(value, str):
        raise ProviderConfigError(f"Container Edition option '{name}' must be a string.")
    return value.strip()


def _gateway(config: TransportConfig) -> Gateway:
    protocol = _option(config, "protocol").lower() or "native"
    if protocol not in {"native", "private"}:
        raise ProviderConfigError("Container Edition protocol must be native or private.")
    domain = _option(config, "domain")
    base = _option(config, "base_url")
    if not domain and not base:
        raise ProviderConfigError("Container Edition needs a domain or a base URL.")
    if domain:
        parts = _url(domain if "://" in domain else f"https://{domain}", "domain")
        if parts.path not in ("", "/"):
            raise ProviderConfigError("Container Edition domain must be a host without a path.")
        domain = parts.netloc
    if not base:
        base = f"https://{domain}/kruise/api" if protocol == "private" else f"https://api.{domain}"
    parts = _url(base, "base URL")
    base = base.rstrip("/")
    if not domain:
        domain = parts.netloc.removeprefix("api.") if protocol == "native" else parts.netloc
    if protocol == "private":
        if not base.endswith("/kruise/api"):
            raise ProviderConfigError("Container Edition private base URL must end in /kruise/api.")
        return Gateway(base, domain, base.removesuffix("/kruise/api"))
    if ":" in (urlsplit(f"https://{domain}").hostname or ""):
        raise ProviderConfigError("Container Edition native routing requires a DNS domain.")
    return Gateway(base, domain)


class AlicloudContainerProvider(Provider):
    """Operate existing SandboxSets through the cluster's E2B-compatible gateway."""

    id = PROVIDER_ID
    display_name = "Alibaba Cloud Agent Sandbox Container Edition"
    display_name_zh = "阿里云 Agent Sandbox 容器版"
    version = __version__
    kind = "builtin"
    config_fields = (
        ConfigField("domain", description="Cluster sandbox-manager gateway domain."),
        ConfigField("base_url", type="url", description="Cluster sandbox-manager management URL."),
        ConfigField(
            "api_key",
            required=True,
            secret=True,
            credential=True,
            description="Cluster sandbox-manager API key.",
        ),
        ConfigField(
            "protocol",
            default="native",
            choices=("native", "private"),
            description="Wildcard-domain or private-prefix gateway routing.",
        ),
    )
    features = frozenset(
        {
            "sandbox.lifecycle",
            "sandbox.timeout",
            "sandbox.pause",
            "exec.run",
            "exec.stream",
            "process.manage",
            "files.rw",
            "ports.url",
        }
    )
    operations = frozenset(
        {
            "sandbox.create",
            "sandbox.get",
            "sandbox.list",
            "sandbox.delete",
            "sandbox.timeout",
            "sandbox.pause",
            "sandbox.resume",
            "exec.run",
            "exec.stream",
            "files.read",
            "files.write",
            "files.list",
            "files.stat",
            "files.remove",
            "files.move",
            "ports.resolve",
            "code.default-context.execute",
        }
    )
    create_options = frozenset({"auto_pause"})
    workflow_inputs = frozenset({"managed"})
    startup_modes = frozenset({"exec", "entrypoint", "none"})

    def validate_config(self, config: TransportConfig) -> None:
        unknown = set(config.provider_options) - {field.key for field in self.config_fields}
        if unknown:
            raise ProviderConfigError(
                "Unknown Container Edition options: " + ", ".join(sorted(unknown))
            )
        _option(config, "api_key")
        super().validate_config(config)
        _gateway(config)

    async def build_infra(self, config: TransportConfig) -> ProviderInfra:
        self.validate_config(config)
        gateway = _gateway(config)
        config = config.model_copy(
            update={
                "sandbox_base_url": gateway.api,
                "sandbox_domain": gateway.domain,
                "sandbox_api_key": None,
                "access_key_id": None,
                "access_key_secret": None,
                "security_token": None,
            }
        )
        auth = HeaderKeyAuth(_option(config, "api_key"), "header")
        http = HttpClient(config, auth)
        return gate_operation_protocols(
            ProviderInfra(
                config=config,
                auth=auth,
                http_client=http,
                sandbox_protocol=ContainerSandboxProtocol(http, gateway),
                process_protocol=ProcessProtocol(http, require_exit=True),
                filesystem_protocol=FilesystemProtocol(http),
                code_interpreter_protocol=JupyterProtocol(http, gateway),
            ),
            self.id,
            self.operations,
        )

    async def application_endpoint(
        self, context: PortContext, port: int, protocol: Any = None
    ) -> dict[str, Any]:
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
