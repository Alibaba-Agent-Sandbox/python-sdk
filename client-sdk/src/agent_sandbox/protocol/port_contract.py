"""Provider-neutral port addressing and gateway authentication contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, Protocol

from agent_sandbox.models.errors import ProviderFeatureNotSupportedError


@dataclass(frozen=True)
class PortContext:
    sandbox_id: str
    domain: str
    secure: bool
    access_token: str | None


class PortAccess(Protocol):
    def get_host(self, port: int) -> str: ...
    def get_url(self, port: int) -> str: ...
    def get_access_headers(self) -> dict[str, str]: ...
    def get_server_headers(self) -> dict[str, str]: ...


class UnsupportedPortAccess:
    def __init__(self, provider_id: str) -> None:
        self._provider_id = provider_id

    def _fail(self) -> NoReturn:
        raise ProviderFeatureNotSupportedError(
            self._provider_id,
            "ports.url",
            suggestion="Use await sandbox.network.resolve(port) for asynchronous port discovery.",
        )

    def get_host(self, port: int) -> str:
        self._fail()

    def get_url(self, port: int) -> str:
        self._fail()

    def get_access_headers(self) -> dict[str, str]:
        self._fail()

    def get_server_headers(self) -> dict[str, str]:
        self._fail()
