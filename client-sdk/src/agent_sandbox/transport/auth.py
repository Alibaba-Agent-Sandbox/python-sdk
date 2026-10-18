"""Authentication providers for Platform API and Sandbox envd API.

Sandbox requests use an explicitly configured API key as an Authorization Bearer.
AK/SK is used separately by official control-plane APIs. AkSkAuth remains an
explicit custom-exchange adapter; no default credential-resource creation occurs.

After sandbox creation, envd API uses envdAccessToken from create response,
sent via multiple headers (X-Access-Token, E2b-Sandbox-Id, etc. 已实测验证).
"""

from __future__ import annotations

import base64
import time
from typing import Any, Protocol

from agent_sandbox.models.errors import (
    InvalidAPIKeyError,
    InvalidCredentialsError,
    TokenExchangeError,
    TokenExpiredError,
)
from agent_sandbox.utils.logging import get_logger

logger = get_logger("transport.auth")

# Header names（已实测验证）
PLATFORM_AUTH_HEADER = "Authorization"  # 已实测验证：Bearer token 认证
ENVD_AUTH_HEADER = "X-Access-Token"
ENVD_SANDBOX_ID_HEADER = "E2b-Sandbox-Id"
ENVD_SANDBOX_PORT_HEADER = "E2b-Sandbox-Port"
_ENVD_BASIC_AUTH = base64.b64encode(b"user:").decode("ascii")  # 已实测验证


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


class AkSkAuth:
    """Legacy adapter for an explicitly configured custom token exchange.

    No Alibaba STS/API-key creation endpoint is selected automatically. Callers
    must supply their own exchange and set the cache lifetime to that service's
    documented token validity. Cached credentials are never persisted.
    """

    TOKEN_TTL = 3600  # Legacy custom-exchange cache policy, not a platform TTL.
    REFRESH_BEFORE_EXPIRY = 300

    def __init__(self, access_key_id: str, access_key_secret: str) -> None:
        if not access_key_id or not access_key_secret:
            raise InvalidCredentialsError(
                "AccessKey ID and Secret cannot be empty",
                suggestion=(
                    "Set ALICLOUD_ACCESS_KEY_ID and ALICLOUD_ACCESS_KEY_SECRET"
                    " environment variables."
                ),
            )
        self._ak = access_key_id.strip()
        self._sk = access_key_secret.strip()
        self._cached_token: str | None = None
        self._token_expires_at: float = 0.0
        self._exchange_func: Any = None  # Set by transport layer

    def _is_token_valid(self) -> bool:
        """Check if cached token is still valid (with refresh buffer)."""
        if self._cached_token is None:
            return False
        return time.time() < (self._token_expires_at - self.REFRESH_BEFORE_EXPIRY)

    async def _exchange_token(self) -> str:
        """Exchange AK/SK for a temporary API key.

        The caller supplies the exchange implementation and owns its lifecycle.
        There is no default network exchange.
        """
        if self._exchange_func is None:
            raise InvalidCredentialsError(
                "Token exchange function not configured. "
                "Set an explicit custom callback with set_exchange_func(), "
                "or use ApiKeyAuth for sandbox requests.",
            )
        token = await self._exchange_func(self._ak, self._sk)
        if not isinstance(token, str) or not token.strip():
            raise TokenExchangeError(
                "Custom token exchange must return a non-empty token string.",
                suggestion="Check the custom exchange contract and token lifetime.",
            )
        self._cached_token = token.strip()
        self._token_expires_at = time.time() + self.TOKEN_TTL
        logger.debug("AK/SK token exchanged, expires at %.0f", self._token_expires_at)
        return self._cached_token

    async def get_headers(self) -> dict[str, str]:
        """Return Authorization: Bearer header with exchanged token."""
        if not self._is_token_valid():
            await self._exchange_token()
        if self._cached_token is None:
            raise TokenExpiredError("Failed to obtain API token via AK/SK exchange")
        return {PLATFORM_AUTH_HEADER: f"Bearer {self._cached_token}"}

    async def refresh(self) -> None:
        """Force refresh the exchanged token."""
        if self._exchange_func is None:
            raise InvalidCredentialsError(
                "AK/SK token exchange function not configured.",
                suggestion=(
                    "Set an explicit custom callback with set_exchange_func(), "
                    "or configure ABX_SANDBOX_API_KEY for sandbox requests."
                ),
            )
        self._cached_token = None
        self._token_expires_at = 0.0
        await self._exchange_token()

    def set_exchange_func(self, func: Any) -> None:
        """Set the token exchange function (called by transport layer)."""
        self._exchange_func = func


class EnvdTokenManager:
    """Manages envdAccessToken for sandbox envd API requests.

    Each sandbox has its own envdAccessToken returned during creation.
    envd 认证需要四个 header（已实测验证）：
    - X-Access-Token: {envd_access_token}
    - E2b-Sandbox-Id: {sandbox_id}
    - E2b-Sandbox-Port: 49983
    - Authorization: Basic {base64("user:")}
    """

    def __init__(
        self,
        token: str | None = None,
        sandbox_id: str | None = None,
        *,
        allow_missing: bool = False,
        basic_user: str = "user",
    ) -> None:
        self._token = token
        self._sandbox_id = sandbox_id
        self._allow_missing = allow_missing
        self._basic_user = basic_user or "user"

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def sandbox_id(self) -> str | None:
        return self._sandbox_id

    def set_token(self, token: str, sandbox_id: str | None = None) -> None:
        """Set the envd access token (from sandbox create response)."""
        self._token = token
        if sandbox_id is not None:
            self._sandbox_id = sandbox_id
        logger.debug("envdAccessToken set for sandbox %s", self._sandbox_id)

    def get_headers(self) -> dict[str, str]:
        """Return all envd auth headers (已实测验证).

        Returns dict with X-Access-Token, E2b-Sandbox-Id, E2b-Sandbox-Port,
        and Authorization (Basic) headers.
        """
        basic = base64.b64encode(f"{self._basic_user}:".encode()).decode("ascii")
        headers = {"Authorization": f"Basic {basic}"}
        if self._token:
            headers[ENVD_AUTH_HEADER] = self._token
        elif not self._allow_missing:
            raise TokenExpiredError(
                "envdAccessToken not available. Sandbox may not be created or connected.",
                suggestion="Create or connect to a sandbox first.",
            )
        if self._sandbox_id is not None:
            headers[ENVD_SANDBOX_ID_HEADER] = self._sandbox_id
        headers[ENVD_SANDBOX_PORT_HEADER] = "49983"
        return headers

    def clear(self) -> None:
        """Clear the cached token."""
        self._token = None
        self._sandbox_id = None


def build_envd_headers(sandbox_id: str, envd_access_token: str) -> dict[str, str]:
    """Build envd authentication headers from sandbox_id and envd_access_token (已实测验证).

    Args:
        sandbox_id: Sandbox ID (e.g., "sbx-xxxx").
        envd_access_token: The envdAccessToken from sandbox create response.

    Returns:
        Dict with all required envd auth headers.
    """
    return {
        ENVD_AUTH_HEADER: envd_access_token,
        ENVD_SANDBOX_ID_HEADER: sandbox_id,
        ENVD_SANDBOX_PORT_HEADER: "49983",
        "Authorization": f"Basic {_ENVD_BASIC_AUTH}",
    }


def create_auth_provider(
    api_key: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
    *,
    region: str = "cn-hangzhou",
) -> AuthProvider:
    """Create API-key authentication for sandbox data-plane requests.

    Explicit api_key takes precedence over ABX_SANDBOX_API_KEY. The AK/SK and
    region arguments remain accepted for signature compatibility, but cannot
    select an automatic key-creation/exchange route. Official template and image
    control-plane operations use their own AK/SK clients.
    """
    if api_key:
        logger.debug("Using API Key authentication")
        return ApiKeyAuth(api_key)

    import os

    sandbox_key = os.environ.get("ABX_SANDBOX_API_KEY")
    if sandbox_key:
        logger.debug("Using API Key authentication (via ABX_SANDBOX_API_KEY)")
        return ApiKeyAuth(sandbox_key)

    if access_key_id and access_key_secret:
        raise InvalidAPIKeyError(
            "A sandbox API Key is required; AK/SK credentials are for control-plane operations.",
            suggestion="Configure ABX_SANDBOX_API_KEY or pass api_key explicitly.",
        )

    raise InvalidAPIKeyError(
        "No authentication credentials provided",
        suggestion=("Configure ABX_SANDBOX_API_KEY or pass api_key explicitly."),
    )
