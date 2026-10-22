"""Local gateway addressing selected explicitly by E2B/envd adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_sandbox.protocol.port_contract import PortContext


class PortClient:
    @staticmethod
    def get_host(sandbox_id: str, port: int, domain: str) -> str:
        return f"{port}-{sandbox_id}.{domain}"

    @staticmethod
    def get_port_url(sandbox_id: str, port: int, domain: str, secure: bool = True) -> str:
        return f"{'https' if secure else 'http'}://{PortClient.get_host(sandbox_id, port, domain)}"


class WirePortAccess:
    def __init__(self, context: PortContext, *, server_auth: bool = True) -> None:
        self._context = context
        self._server_auth = server_auth

    def get_host(self, port: int) -> str:
        return PortClient.get_host(self._context.sandbox_id, port, self._context.domain)

    def get_url(self, port: int) -> str:
        return PortClient.get_port_url(
            self._context.sandbox_id, port, self._context.domain, self._context.secure
        )

    def get_access_headers(self) -> dict[str, str]:
        if self._context.secure and self._context.access_token:
            return {"X-Access-Token": self._context.access_token}
        return {}

    def get_server_headers(self) -> dict[str, str]:
        return self.get_access_headers() if self._server_auth else {}
