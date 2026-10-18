"""Agent Sandbox Client SDK — Create, manage, and interact with cloud sandboxes."""

from __future__ import annotations

from pkgutil import extend_path
from typing import Any

from agent_sandbox._version import __version__

# ``agent_sandbox`` is a shared namespace: ``agent_sandbox.server`` ships in the
# separate ``agent-sandbox-server`` distribution, possibly installed in another
# directory (editable installs, vendored layouts).
__path__ = extend_path(__path__, __name__)

__all__ = [
    "__version__",
    "Sandbox",
    "SandboxError",
    "AuthenticationError",
    "SandboxCreationError",
    "ExecutionError",
    "FileOperationError",
    "NetworkError",
    "sandbox",
]


def __getattr__(name: str) -> Any:
    if name == "Sandbox":
        from agent_sandbox.api.sandbox import Sandbox

        return Sandbox
    if name in (
        "SandboxError",
        "AuthenticationError",
        "SandboxCreationError",
        "ExecutionError",
        "FileOperationError",
        "NetworkError",
    ):
        from agent_sandbox.models import errors

        return getattr(errors, name)
    if name == "sandbox":
        from agent_sandbox.declarative.decorator import sandbox as _sandbox

        return _sandbox
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _resolve_provider_schema(provider_id: str) -> Any:
    """Composition adapter; discovery stays lazy and outside transport."""
    from agent_sandbox._provider_schema import ProviderSchema
    from agent_sandbox.providers.bundled_config import bundled_config

    metadata = bundled_config(provider_id)
    if metadata is not None:
        return ProviderSchema(
            metadata["id"],
            metadata["keys"],
            metadata["inherit"],
            dict(metadata["derive"]),
            dict(metadata["endpoint_defaults"]),
            legacy_fields=metadata["legacy_fields"],
            omit_default_options=metadata["omit_default_options"],
            legacy_url_builder=metadata["legacy_url_builder"],
        )
    from agent_sandbox.providers.registry import get_provider

    provider = get_provider(provider_id)
    return ProviderSchema(
        provider.id,
        provider.config_keys(),
        frozenset(provider.inherit),
        dict(provider.derive),
        dict(getattr(provider, "endpoint_defaults", {}) or {}),
        legacy_fields=frozenset(getattr(provider, "legacy_fields", ())),
        omit_default_options=bool(getattr(provider, "omit_default_options", False)),
        legacy_url_builder=getattr(provider, "legacy_session_url", None),
    )


from agent_sandbox._provider_schema import _set_resolver  # noqa: E402

_set_resolver(_resolve_provider_schema)
del _set_resolver
