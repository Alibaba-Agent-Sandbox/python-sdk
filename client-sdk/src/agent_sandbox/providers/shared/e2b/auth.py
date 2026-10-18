"""Authentication for providers explicitly selecting the E2B/envd wire adapter."""

from __future__ import annotations

import base64

from agent_sandbox.models.errors import TokenExpiredError
from agent_sandbox.utils.logging import get_logger

logger = get_logger("providers.shared.e2b.auth")
ENVD_AUTH_HEADER = "X-Access-Token"
ENVD_SANDBOX_ID_HEADER = "E2b-Sandbox-Id"
ENVD_SANDBOX_PORT_HEADER = "E2b-Sandbox-Port"
_ENVD_BASIC_AUTH = base64.b64encode(b"user:").decode("ascii")


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
