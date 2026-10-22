"""Provider-owned port addressing and access headers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from agent_sandbox.protocol.port_contract import PortAccess

from agent_sandbox.models.template import DEFAULT_CAPABILITIES
from agent_sandbox.utils.logging import get_logger

logger = get_logger("api.network")


class NetworkModule:
    """Port access through the selected adapter; async discovery uses resolve()."""

    def __init__(
        self,
        sandbox_id: str,
        domain: str,
        secure: bool = True,
        access_token: str | None = None,
        capabilities: set[str] | None = None,
        port_resolver: Callable[[int], Awaitable[tuple[str, dict[str, str]]]] | None = None,
        port_access: PortAccess | None = None,
    ) -> None:
        self._port_resolver = port_resolver
        if port_access is None:
            raise ValueError("NetworkModule requires the selected provider's port_access.")
        self._port_access = port_access
        self._sandbox_id = sandbox_id
        self._domain = domain
        self._secure = secure
        self._access_token = access_token
        self._capabilities = capabilities if capabilities is not None else set(DEFAULT_CAPABILITIES)

    def get_host(self, port: int) -> str:
        """Return the host supplied by the synchronous adapter hook."""
        return self._port_access.get_host(port)

    def get_url(self, port: int) -> str:
        """Return the URL supplied by the synchronous adapter hook."""
        return self._port_access.get_url(port)

    def get_access_headers(self) -> dict[str, str]:
        """Return access headers supplied by the selected adapter."""
        return self._port_access.get_access_headers()

    def get_server_headers(self) -> dict[str, str]:
        """Gateway headers for the project server, owned by the selected adapter."""
        return self._port_access.get_server_headers()

    async def resolve(self, port: int) -> tuple[str, dict[str, str]]:
        """Return ``(url, headers)`` for *port*, asking the provider when it can answer.

        Providers that declare ``ports.url`` are asked for the authoritative URL and access
        headers; everything else falls back to :meth:`get_url` / :meth:`get_access_headers`.
        """
        if self._port_resolver is not None:
            return await self._port_resolver(port)
        return self.get_url(port), self.get_access_headers()

    async def resolve_url(self, port: int) -> str:
        """Like :meth:`get_url`, but routed through the provider's ``ports.url`` when declared."""
        return (await self.resolve(port))[0]
