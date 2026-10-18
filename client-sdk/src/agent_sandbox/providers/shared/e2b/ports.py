"""Local gateway addressing selected explicitly by E2B/envd adapters."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

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


def legacy_pty_url(base_url: str, server_port: int, pty_port: int) -> str:
    """Preserve the historical standalone ServerClient gateway convention."""
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    gateway = re.match(rf"^{server_port}-(.+)$", host)
    if gateway:
        netloc = f"{pty_port}-{gateway.group(1)}"
        if parts.port:
            netloc += f":{parts.port}"
    else:
        netloc = f"{host}:{pty_port}"
    return urlunsplit((parts.scheme, netloc, "", "", ""))
