"""Authentication providers for Platform API and Sandbox envd API.

Sandbox requests use an explicitly configured API key as an Authorization Bearer.
AK/SK is used separately by official control-plane APIs. AkSkAuth remains an
explicit custom-exchange adapter; no default credential-resource creation occurs.

After sandbox creation, envd API uses envdAccessToken from create response,
sent via multiple headers (X-Access-Token, E2b-Sandbox-Id, etc. 已实测验证).
"""

from __future__ import annotations

import time
from typing import Any

from agent_sandbox.models.errors import (
    InvalidAPIKeyError,
    InvalidCredentialsError,
    TokenExchangeError,
    TokenExpiredError,
)
from agent_sandbox.providers.shared.e2b.auth import (
    _ENVD_BASIC_AUTH as _ENVD_BASIC_AUTH,
)
from agent_sandbox.providers.shared.e2b.auth import (
    ENVD_AUTH_HEADER as ENVD_AUTH_HEADER,
)
from agent_sandbox.providers.shared.e2b.auth import (
    ENVD_SANDBOX_ID_HEADER as ENVD_SANDBOX_ID_HEADER,
)
from agent_sandbox.providers.shared.e2b.auth import (
    ENVD_SANDBOX_PORT_HEADER as ENVD_SANDBOX_PORT_HEADER,
)
from agent_sandbox.providers.shared.e2b.auth import (
    EnvdTokenManager as EnvdTokenManager,
)
from agent_sandbox.providers.shared.e2b.auth import (
    build_envd_headers as build_envd_headers,
)
from agent_sandbox.transport.auth_contract import (
    PLATFORM_AUTH_HEADER as PLATFORM_AUTH_HEADER,
)
from agent_sandbox.transport.auth_contract import (
    ApiKeyAuth as ApiKeyAuth,
)
from agent_sandbox.transport.auth_contract import (
    AuthProvider as AuthProvider,
)
from agent_sandbox.utils.logging import get_logger

logger = get_logger("transport.auth")


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

    def authentication_error(self, path: str) -> InvalidCredentialsError:
        """Map rejected custom-exchange credentials without exposing their values."""
        return InvalidCredentialsError(
            f"The Platform API rejected the custom exchanged credential (HTTP 401) for {path}."
        )

    def set_exchange_func(self, func: Any) -> None:
        """Set the token exchange function (called by transport layer)."""
        self._exchange_func = func


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
