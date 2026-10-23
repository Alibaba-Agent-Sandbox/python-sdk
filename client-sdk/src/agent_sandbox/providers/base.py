"""Provider contract: identity, feature matrix, config schema, infrastructure factory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, cast

from agent_sandbox.models.errors import (
    InvalidCredentialsError,
    ProviderConfigError,
    ProviderFeatureNotSupportedError,
)
from agent_sandbox.utils.config_keys import (
    GENERIC_ENDPOINT_KEYS,
    ConfigKey,
    provider_env_name,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from agent_sandbox.protocol.contracts import (
        CodeInterpreterProtocol,
        FilesystemProtocol,
        ProcessProtocol,
        SandboxProtocol,
    )
    from agent_sandbox.protocol.port_contract import PortAccess, PortContext
    from agent_sandbox.transport.auth_contract import AuthProvider
    from agent_sandbox.transport.config import TransportConfig
    from agent_sandbox.transport.http import HttpClient

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
    "templates.read",
    "templates.build",
    "templates.deploy",
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
    "templates.read",
    "templates.build",
    "templates.deploy",
    "ports.url",
    "ports.domain",
    "storage.mount",
    "network.vpc",
    "sessions",
]


def ordered_features(features: Iterable[str]) -> list[str]:
    """Feature ids in registry order; ids the host does not know come last, sorted."""
    have = set(features)
    known = [f for f in FEATURES if f in have]
    return known + sorted(have - set(FEATURES))


def compact_features(features: Iterable[str]) -> str:
    """``sandbox.lifecycle, sandbox.pause, pty`` -> ``sandbox(lifecycle,pause) pty``."""
    groups: dict[str, list[str]] = {}
    for feature in ordered_features(features):
        head, dot, tail = feature.partition(".")
        tails = groups.setdefault(head, [])
        if dot:
            tails.append(tail)
    return " ".join(f"{h}({','.join(t)})" if t else h for h, t in groups.items())


def consented_inherit(declared: Iterable[str], receipt: Mapping[str, Any] | None) -> frozenset[str]:
    """Generic endpoint keys a manifest-driven provider may read (declared and consented)."""
    declared = list(declared)
    if receipt is None:
        return frozenset(declared)
    consented = set((receipt.get("consented") or {}).get("inherit") or [])
    return frozenset(k for k in declared if k in consented)


class Extension(NamedTuple):
    """A capability outside the feature registry.

    ``when`` decides whether a live sandbox shows it. The provider catalog
    (``describe``) always lists every extension the provider registered.

    * ``sandbox`` — visible once a sandbox id exists.
    * ``code_interpreter_image`` — visible only when the image name contains ``code-interpreter``.
    * ``egress`` — visible only when this sandbox was created with an egress sidecar.
    * ``command`` — visible only when the caller has an execd command id.
    """

    id: str
    summary: str
    summary_zh: str
    implemented: bool
    when: str


def _image_is_code_interpreter(image: str) -> bool:
    return "code-interpreter" in image


def _extension_visible(ext: Extension, *, image: str, egress: bool, command_id: str) -> bool:
    if ext.when == "sandbox":
        return True
    if ext.when == "code_interpreter_image":
        return _image_is_code_interpreter(image)
    if ext.when == "egress":
        return egress
    if ext.when == "command":
        return bool(command_id)
    return False


ProviderKind = Literal["builtin", "rest", "exec", "node", "python"]


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
        from agent_sandbox.utils.config_keys import Alias, Storage

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
            storage=(
                Storage("env", provider_env_name(provider_id, self.key))
                if self.secret
                else Storage("toml", self.key, f"providers.{provider_id}")
            ),
        )


@dataclass
class ProviderInfra:
    """What :class:`~agent_sandbox.api.sandbox.Sandbox` needs from a provider."""

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
    operation_contract_version: int = 1
    operations: frozenset[str] = frozenset()
    workflow_inputs: frozenset[str] = frozenset()
    startup_modes: frozenset[str] = frozenset()
    extensions: tuple[Extension, ...] = ()
    config_fields: tuple[ConfigField, ...] = ()
    #: Generic keys (``sandbox_api_key``, ``sandbox_base_url``, ``sandbox_domain``) it reads.
    inherit: frozenset[str] = frozenset()
    #: ``[auth] any_of`` groups of config-field keys; empty = no credential check.
    auth_any_of: tuple[tuple[str, ...], ...] = ()
    #: ``[endpoint.derive]`` templates (key -> template with ``{region}``-style fields).
    derive: Mapping[str, str] = MappingProxyType({})
    #: Static endpoint defaults (``sandbox_base_url``/``sandbox_domain``) of declarative providers.
    endpoint_defaults: Mapping[str, str] = MappingProxyType({})

    #: Optional create inputs explicitly implemented by the backend.
    create_options: frozenset[str] = frozenset()

    def session_protocols(self, http: Any) -> dict[str, Any]:
        """Missing protocols fail explicitly rather than acquiring a native transport."""

        class Unsupported:
            prepare_session = None

            def __init__(self, provider: str, feature: str) -> None:
                self.provider, self.feature = provider, feature

            def __getattr__(self, name: str) -> Any:
                async def fail(*args: Any, **kwargs: Any) -> Any:
                    raise ProviderFeatureNotSupportedError(self.provider, self.feature)

                return fail

        return {
            name: Unsupported(self.id, feature)
            for name, feature in (
                ("sandbox_protocol", "sandbox.lifecycle"),
                ("process_protocol", "exec.run"),
                ("filesystem_protocol", "files.rw"),
                ("code_interpreter_protocol", "code.execute"),
            )
        }

    def resolve_session_url(self, info: Any, config: Any) -> str:
        return str(info.envd_url or "")

    def create_port_access(self, context: PortContext, protocol: Any = None) -> PortAccess:
        """Select local port semantics explicitly; absent implementations fail closed."""
        from agent_sandbox.protocol.port_contract import UnsupportedPortAccess

        factory = getattr(protocol, "create_port_access", None)
        if callable(factory):
            return cast("PortAccess", factory(context))
        return UnsupportedPortAccess(self.id)

    async def application_endpoint(
        self, context: PortContext, port: int, protocol: Any = None
    ) -> dict[str, Any]:
        """Return an explicitly implemented application binding, never an envd fallback."""
        raise ProviderFeatureNotSupportedError(self.id, "ports.resolve")

    async def prepare_session(
        self, infra: ProviderInfra, info: Any, *, operation: str, template: str
    ) -> dict[str, Any]:
        """Return only the backend's session binding; core never supplies wire adapters."""
        from agent_sandbox.transport.auth_contract import SessionAuth

        binder = getattr(infra.sandbox_protocol, "prepare_session", None)
        if callable(binder):
            return dict(await binder(info))
        return {"envd_token": SessionAuth(info.envd_access_token, info.sandbox_id)}

    async def open_terminal(self, sandbox: Any, **options: Any) -> Any:
        self.require("pty")
        opener = getattr(sandbox._process_protocol, "open_terminal", None)
        if opener is None:
            raise ProviderFeatureNotSupportedError(self.id, "pty")
        return await opener(sandbox.id, cols=options.get("cols", 80), rows=options.get("rows", 24))

    def require(self, feature: str) -> None:
        """Raise :class:`ProviderFeatureNotSupportedError` unless *feature* is implemented."""
        if feature not in self.features:
            raise ProviderFeatureNotSupportedError(self.id, feature)

    def supports(self, feature: str) -> bool:
        return feature in self.features

    def extensions_for(
        self,
        *,
        image: str = "",
        sandbox_id: str = "",
        egress: bool = False,
        command_id: str = "",
    ) -> tuple[Extension, ...]:
        """Extensions visible on this sandbox. An empty ``sandbox_id`` shows none.

        The catalog (``describe()["extensions"]``) is the full registration and
        does not use this filter.
        """
        if not sandbox_id:
            return ()
        return tuple(
            ext
            for ext in self.extensions
            if _extension_visible(ext, image=image, egress=egress, command_id=command_id)
        )

    def require_extension(self, extension_id: str) -> Extension:
        """Return the extension, or raise ``E8004`` when it is missing or not implemented."""
        found = next((ext for ext in self.extensions if ext.id == extension_id), None)
        if found is None or not found.implemented:
            raise ProviderFeatureNotSupportedError(self.id, extension_id)
        return found

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
                    f"'abx config set providers.{self.id}.{f.key} ...').",
                    suggestion=f"Run 'abx provider info {self.id}' for all options.",
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
                suggestion=f"Run 'abx provider info {self.id}' for details.",
            )

    def config_keys(self) -> tuple[ConfigKey, ...]:
        return tuple(f.to_config_key(self.id) for f in self.config_fields)

    @abstractmethod
    async def build_infra(self, config: TransportConfig) -> ProviderInfra:
        """Build the protocol objects for *config* (already resolved for this provider)."""

    def content_digest(self) -> str:
        """Hash actual provider code and its installed source dependencies.

        Plugin identities include the complete plugin tree. Native identities bind
        shipped package source/config, not the display version or manifest alone.
        Symlinks fail closed and credential/cache/state files are excluded.
        """
        import os
        from pathlib import Path

        from agent_sandbox.workflows.identity import snapshot_digest

        plugin_root = getattr(self, "plugin_root", None)
        if plugin_root is None and not type(self).__module__.startswith("agent_sandbox.providers."):
            raise ProviderConfigError(
                "External native providers must implement their own content_digest"
            )
        root = Path(plugin_root) if plugin_root is not None else Path(__file__).resolve().parents[1]
        excluded = {
            ".git",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            "node_modules",
            ".venv",
            "data",
            ".abx-install.json",
        }
        files: dict[str, bytes] = {}
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in excluded)
            for name in dirs + sorted(names):
                path = Path(directory) / name
                if path.is_symlink():
                    raise ProviderConfigError("Provider content identity refuses symlinked inputs")
            for name in sorted(names):
                if (
                    name in excluded
                    or name == ".env"
                    or name.startswith(".env.")
                    or name.endswith((".pem", ".key", ".pyc"))
                ):
                    continue
                path = Path(directory) / name
                if not path.is_file():
                    raise ProviderConfigError("Provider content identity requires regular files")
                files[path.relative_to(root).as_posix()] = path.read_bytes()
        return snapshot_digest(files)

    def capabilities(self) -> frozenset[str]:
        """Coarse discovery from implemented operations; never grants authorization."""
        tokens = set()
        if "exec.run" in self.operations:
            tokens.add("shell")
        if {"files.read", "files.write"} <= self.operations:
            tokens.add("files")
        if any(op.startswith("code.") for op in self.operations):
            tokens.add("code")
        if "ports.resolve" in self.operations:
            tokens.add("ports")
        if "pty" in self.features:
            tokens.add("terminal")
        return frozenset(tokens)

    def describe(self) -> dict[str, Any]:
        """JSON-friendly summary (``abx provider info``)."""
        manifest = getattr(self, "manifest", None)
        return {
            "id": self.id,
            "name": self.display_name,
            "name_zh": self.display_name_zh,
            "version": self.version,
            "kind": self.kind,
            "features": sorted(self.features),
            "operation_contract_version": self.operation_contract_version,
            "operations": {
                "cli": list(manifest.operations["cli"]) if manifest else [],
                "python": sorted(self.operations),
            },
            "workflow_inputs": sorted(self.workflow_inputs),
            "startup_modes": sorted(self.startup_modes),
            "extensions": [
                {
                    "id": ext.id,
                    "summary": ext.summary,
                    "summary_zh": ext.summary_zh,
                    "implemented": ext.implemented,
                    "when": ext.when,
                }
                for ext in self.extensions
            ],
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
