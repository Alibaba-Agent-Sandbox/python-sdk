"""Authentication providers for Platform API and Sandbox envd API.

Sandbox requests use an explicitly configured API key as an Authorization Bearer.
AK/SK is used separately by official control-plane APIs.

After sandbox creation, envd API uses envdAccessToken from create response,
sent via multiple headers (X-Access-Token, E2b-Sandbox-Id, etc. 已实测验证).
"""

from __future__ import annotations

from agent_sandbox.models.errors import (
    InvalidAPIKeyError,
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


def create_auth_provider(
    api_key: str | None = None,
) -> AuthProvider:
    """Create API-key authentication for sandbox data-plane requests.

    Explicit api_key takes precedence over ABX_SANDBOX_API_KEY. Control-plane
    operations use their own AK/SK clients.
    """
    if api_key:
        logger.debug("Using API Key authentication")
        return ApiKeyAuth(api_key)

    import os

    sandbox_key = os.environ.get("ABX_SANDBOX_API_KEY")
    if sandbox_key:
        logger.debug("Using API Key authentication (via ABX_SANDBOX_API_KEY)")
        return ApiKeyAuth(sandbox_key)

    raise InvalidAPIKeyError(
        "No authentication credentials provided",
        suggestion=("Configure ABX_SANDBOX_API_KEY or pass api_key explicitly."),
    )
