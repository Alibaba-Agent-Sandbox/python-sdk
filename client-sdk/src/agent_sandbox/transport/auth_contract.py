"""Cloud-independent authentication contracts and explicit bearer credentials."""

from __future__ import annotations

from typing import Protocol

from agent_sandbox.models.errors import InvalidAPIKeyError

PLATFORM_AUTH_HEADER = "Authorization"


class AuthProvider(Protocol):
    """Protocol for authentication providers."""

    async def get_headers(self) -> dict[str, str]:
        """Return authentication headers for Platform API requests."""
        ...

    async def refresh(self) -> None:
        """Force refresh credentials if applicable."""
        ...


class ApiKeyAuth:
    """API Key authentication for Platform API.

    Uses ABX_SANDBOX_API_KEY environment variable or explicit api_key parameter.
    Sends an Authorization Bearer header on Platform API requests.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key or not api_key.strip():
            raise InvalidAPIKeyError("API key cannot be empty")
        self._api_key = api_key.strip()

    async def get_headers(self) -> dict[str, str]:
        """Return Authorization: Bearer header (已实测验证)."""
        return {PLATFORM_AUTH_HEADER: f"Bearer {self._api_key}"}

    async def refresh(self) -> None:
        """No-op for API key auth."""
        pass


class SessionAuth:
    """Opaque session credentials. A backend chooses how they become wire headers."""

    def __init__(self, token: str | None, sandbox_id: str | None) -> None:
        self.token, self.sandbox_id = token, sandbox_id

    def get_headers(self) -> dict[str, str]:
        return {}

    def set_token(self, token: str, sandbox_id: str | None = None) -> None:
        self.token = token
        if sandbox_id is not None:
            self.sandbox_id = sandbox_id

    def clear(self) -> None:
        self.token = None
        self.sandbox_id = None


class DataPlaneAuth(Protocol):
    @property
    def token(self) -> str | None: ...
    @property
    def sandbox_id(self) -> str | None: ...
    def get_headers(self) -> dict[str, str]: ...
    def set_token(self, token: str, sandbox_id: str | None = None) -> None: ...
    def clear(self) -> None: ...
