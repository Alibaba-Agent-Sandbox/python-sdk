"""Sandbox providers (backends): contract, registry, built-in provider and plugin management.

The default provider is ``alicloud-express`` (Alibaba Cloud Express Edition, 阿里云极速版).
Third-party providers are installed from a directory or git URL (``ebx provider install`` /
``python -m easy_sandbox.providers install``) and selected with ``Sandbox.create(provider=...)``,
``EBX_PROVIDER`` or ``[core] provider`` in ``~/.ebx/config.toml``.
"""

from easy_sandbox.providers.base import (
    FEATURES,
    ConfigField,
    Provider,
    ProviderFeature,
    ProviderInfra,
)
from easy_sandbox.providers.registry import (
    ambient_provider_id,
    get_provider,
    list_providers,
    parse_sandbox_ref,
    qualify,
    register_provider,
    resolve_provider_id,
    unregister_provider,
)
from easy_sandbox.utils.config_keys import BUILTIN_PROVIDER_ID

__all__ = [
    "BUILTIN_PROVIDER_ID",
    "FEATURES",
    "ConfigField",
    "Provider",
    "ProviderFeature",
    "ProviderInfra",
    "ambient_provider_id",
    "get_provider",
    "list_providers",
    "parse_sandbox_ref",
    "qualify",
    "register_provider",
    "resolve_provider_id",
    "unregister_provider",
]
