"""Provider contract: identity, feature matrix, config schema, infrastructure factory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from easy_sandbox.models.errors import (
    InvalidCredentialsError,
    ProviderConfigError,
    ProviderFeatureNotSupportedError,
)
from easy_sandbox.utils.config_keys import (
    GENERIC_ENDPOINT_KEYS,
    ConfigKey,
    provider_env_name,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from easy_sandbox.protocol.code_interpreter import CodeInterpreterProtocol
    from easy_sandbox.protocol.filesystem import FilesystemProtocol
    from easy_sandbox.protocol.process import ProcessProtocol
    from easy_sandbox.protocol.sandbox import SandboxProtocol
    from easy_sandbox.transport.auth import AuthProvider
    from easy_sandbox.transport.config import TransportConfig
    from easy_sandbox.transport.http import HttpClient

#: Feature registry (design §7.2). Values are the stable wire/manifest ids.
FEATURES: tuple[str, ...] = (
    "sandbox.lifecycle",
    "sandbox.timeout",
    "sandbox.pause",
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
    "ports.domain",
    "storage.mount",
    "network.vpc",
    "sessions",
)

ProviderFeature = Literal[
    "sandbox.lifecycle",
    "sandbox.timeout",
    "sandbox.pause",
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
    "ports.domain",
    "storage.mount",
    "network.vpc",
    "sessions",
]

#: Template capability token implied by a provider feature (design §7.2).
FEATURE_TO_CAPABILITY: dict[str, str] = {
    "exec.run": "shell",
    "files.rw": "files",
    "code.interpret": "code",
    "pty": "terminal",
    "ports.url": "ports",
}

ProviderKind = Literal["builtin", "rest", "exec", "python"]


@dataclass(frozen=True)
class ConfigField:
    """One provider-scoped configuration field (``[config.fields.<key>]``)."""

    key: str
    type: str = "str"
    required: bool = False
    secret: bool = False
    credential: bool = False
    default: Any = None
    description: str = ""
    description_zh: str = ""
    env: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()

    def to_config_key(self, provider_id: str) -> ConfigKey:
        """The registry record used by the resolver for this field."""
        from easy_sandbox.utils.config_keys import Alias, Storage

        return ConfigKey(
            self.key,
            scope=provider_id,
            type=self.type
            if self.type in ("str", "url", "int", "float", "bool", "enum", "path", "csv")
            else "str",
            secret=self.secret,
            credential=self.credential,
            required=self.required,
            default=self.default,
            description=self.description,
            description_zh=self.description_zh,
            choices=self.choices,
            aliases=tuple(Alias(n, "native", "env") for n in self.env),
            storage_phase1=(
                Storage("env", provider_env_name(provider_id, self.key))
                if self.secret
                else Storage("toml", self.key, f"providers.{provider_id}")
            ),
            storage_phase2=(
                Storage("env", provider_env_name(provider_id, self.key))
                if self.secret
                else Storage("toml", self.key, f"providers.{provider_id}")
            ),
        )


@dataclass
class ProviderInfra:
    """What :class:`~easy_sandbox.api.sandbox.Sandbox` needs from a provider."""

    config: TransportConfig
    auth: AuthProvider | None
    http_client: HttpClient | None
    sandbox_protocol: SandboxProtocol | Any
    process_protocol: ProcessProtocol | Any | None = None
    filesystem_protocol: FilesystemProtocol | Any | None = None
    code_interpreter_protocol: CodeInterpreterProtocol | Any | None = None
    close: Any = None  # optional ``async def close()`` for non-HTTP providers


class Provider(ABC):
    """A sandbox backend.

    Subclass for SDK-only (``kind = "python"``) providers; the built-in provider and the
    manifest-driven ``rest``/``exec`` providers are implemented by this package.
    """

    id: str
    display_name: str = ""
    display_name_zh: str = ""
    version: str = "0.0.0"
    kind: ProviderKind = "python"
    features: frozenset[str] = frozenset()
    config_fields: tuple[ConfigField, ...] = ()
    #: Generic keys (``sandbox_api_key``, ``sandbox_base_url``, ``sandbox_domain``) it reads.
    inherit: frozenset[str] = frozenset()
    #: ``[auth] any_of`` groups of config-field keys; empty = no credential check.
    auth_any_of: tuple[tuple[str, ...], ...] = ()
    #: ``[endpoint.derive]`` templates (key -> template with ``{region}``-style fields).
    derive: Mapping[str, str] = MappingProxyType({})
    #: Static endpoint defaults (``sandbox_base_url``/``sandbox_domain``) of declarative providers.
    endpoint_defaults: Mapping[str, str] = MappingProxyType({})

    def require(self, feature: str) -> None:
        """Raise :class:`ProviderFeatureNotSupportedError` unless *feature* is implemented."""
        if feature not in self.features:
            raise ProviderFeatureNotSupportedError(self.id, feature)

    def supports(self, feature: str) -> bool:
        return feature in self.features

    def validate_config(self, config: TransportConfig) -> None:
        """Raise when required fields or every credential group in ``auth_any_of`` are missing."""
        opts = config.provider_options

        def have(name: str) -> bool:
            if name in GENERIC_ENDPOINT_KEYS:
                return bool(getattr(config, name, None)) and name in self.inherit
            return opts.get(name) not in (None, "")

        for f in self.config_fields:
            if f.required and not have(f.key):
                names = ", ".join((provider_env_name(self.id, f.key), *f.env))
                exc_type = InvalidCredentialsError if f.credential else ProviderConfigError
                raise exc_type(
                    f"Provider '{self.id}' needs '{f.key}' (set {names} or "
                    f"'ebx config set providers.{self.id}.{f.key} ...').",
                    suggestion=f"Run 'ebx provider info {self.id}' for all options.",
                )
        if self.auth_any_of and not any(all(have(n) for n in grp) for grp in self.auth_any_of):
            wanted = " or ".join(
                " + ".join(
                    provider_env_name(self.id, n) if n not in GENERIC_ENDPOINT_KEYS else n
                    for n in grp
                )
                for grp in self.auth_any_of
            )
            raise InvalidCredentialsError(
                f"Provider '{self.id}' is missing credentials (set {wanted}).",
                suggestion=f"Run 'ebx provider info {self.id}' for details.",
            )

    def config_keys(self) -> tuple[ConfigKey, ...]:
        return tuple(f.to_config_key(self.id) for f in self.config_fields)

    @abstractmethod
    async def build_infra(self, config: TransportConfig) -> ProviderInfra:
        """Build the protocol objects for *config* (already resolved for this provider)."""

    def capabilities(self) -> frozenset[str]:
        """Template capability tokens implied by this provider's features."""
        return frozenset(c for f, c in FEATURE_TO_CAPABILITY.items() if f in self.features)

    def describe(self) -> dict[str, Any]:
        """JSON-friendly summary (``ebx provider info``)."""
        return {
            "id": self.id,
            "name": self.display_name,
            "name_zh": self.display_name_zh,
            "version": self.version,
            "kind": self.kind,
            "features": sorted(self.features),
            "config_fields": [
                {
                    "key": f.key,
                    "type": f.type,
                    "secret": f.secret,
                    "credential": f.credential,
                    "required": f.required,
                    "default": f.default,
                    "env": provider_env_name(self.id, f.key),
                    "aliases": list(f.env),
                    "description": f.description,
                    "description_zh": f.description_zh,
                }
                for f in self.config_fields
            ],
            "inherit": sorted(self.inherit),
        }
