"""Low-level configuration schema values and a composition-injected resolver.

No provider discovery/import is performed by this module. The package root
registers a lazy adapter; transport depends only on these values and callback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from agent_sandbox.utils.config_keys import ConfigKey


class ProviderSchema:
    """What the resolver needs to know about the selected provider."""

    def __init__(
        self,
        provider_id: str,
        keys: tuple[ConfigKey, ...],
        inherit: frozenset[str],
        derive: dict[str, str] | None = None,
        endpoint_defaults: dict[str, str] | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.keys = keys
        self.inherit = inherit
        self.derive = derive or {}
        self.endpoint_defaults = endpoint_defaults or {}

    @property
    def builtin(self) -> bool:
        from agent_sandbox.utils.config_keys import BUILTIN_PROVIDER_ID

        return self.provider_id == BUILTIN_PROVIDER_ID


_resolver: Callable[[str], ProviderSchema] | None = None


def _set_resolver(resolver: Callable[[str], ProviderSchema]) -> None:
    global _resolver
    _resolver = resolver


def resolve_provider_schema(provider_id: str) -> ProviderSchema:
    if _resolver is None:
        raise RuntimeError("The provider configuration resolver is not initialized.")
    return _resolver(provider_id)
