"""Sandbox providers (backends): contract, registry, built-in provider and plugin management.

The default provider is ``alicloud-express`` (Alibaba Cloud Express Edition, 阿里云极速版).
Third-party providers are installed from a directory or git URL (``abx provider install`` /
``python -m agent_sandbox.providers install``) and selected with ``Sandbox.create(provider=...)``,
``ABX_PROVIDER`` or ``[core] provider`` in ``~/.abx/config.toml``.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_sandbox.providers import commands as commands
    from agent_sandbox.providers.base import FEATURES as FEATURES
    from agent_sandbox.providers.base import ConfigField as ConfigField
    from agent_sandbox.providers.base import Provider as Provider
    from agent_sandbox.providers.base import ProviderFeature as ProviderFeature
    from agent_sandbox.providers.base import ProviderInfra as ProviderInfra
    from agent_sandbox.providers.manifest import ProviderCommand as ProviderCommand
    from agent_sandbox.providers.registry import ambient_provider_id as ambient_provider_id
    from agent_sandbox.providers.registry import get_provider as get_provider
    from agent_sandbox.providers.registry import list_providers as list_providers
    from agent_sandbox.providers.registry import parse_sandbox_ref as parse_sandbox_ref
    from agent_sandbox.providers.registry import qualify as qualify
    from agent_sandbox.providers.registry import register_provider as register_provider
    from agent_sandbox.providers.registry import resolve_provider_id as resolve_provider_id
    from agent_sandbox.providers.registry import unregister_provider as unregister_provider
    from agent_sandbox.utils.config_keys import BUILTIN_PROVIDER_ID as BUILTIN_PROVIDER_ID

__all__ = [
    "BUILTIN_PROVIDER_ID",
    "FEATURES",
    "ConfigField",
    "Provider",
    "ProviderFeature",
    "ProviderInfra",
    "ProviderCommand",
    "commands",
    "ambient_provider_id",
    "get_provider",
    "list_providers",
    "parse_sandbox_ref",
    "qualify",
    "register_provider",
    "resolve_provider_id",
    "unregister_provider",
]


def __getattr__(name: str) -> Any:
    """Keep public exports lazy so reading bundled metadata does not discover providers."""
    if name == "commands":
        return import_module("agent_sandbox.providers.commands")
    if name == "BUILTIN_PROVIDER_ID":
        return getattr(import_module("agent_sandbox.utils.config_keys"), name)
    if name in {"FEATURES", "ConfigField", "Provider", "ProviderFeature", "ProviderInfra"}:
        module = "base"
    elif name == "ProviderCommand":
        module = "manifest"
    elif name in __all__:
        module = "registry"
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(f"agent_sandbox.providers.{module}"), name)
