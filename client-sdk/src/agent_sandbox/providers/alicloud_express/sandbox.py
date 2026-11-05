"""Express-only lifecycle behavior over the documented E2B-compatible API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_sandbox.models.errors import ProviderProtocolError, SandboxCreationError
from agent_sandbox.models.network import network_secret_values
from agent_sandbox.models.sandbox import SandboxStatus
from agent_sandbox.providers.shared.e2b.sandbox import SandboxProtocol as E2bSandboxProtocol

if TYPE_CHECKING:
    from agent_sandbox.models.sandbox import SandboxConfig, SandboxInfo


class SandboxProtocol(E2bSandboxProtocol):
    """Retain read-only attach while using connect explicitly for resume."""

    async def create(
        self, config: SandboxConfig, *, request_timeout: float | None = None
    ) -> SandboxInfo:
        """Keep reflected network credentials out of public errors and chains."""
        secrets = network_secret_values(config.network)
        try:
            return await super().create(config, request_timeout=request_timeout)
        except SandboxCreationError as error:
            if not secrets:
                raise

            def redact(value: str) -> str:
                for secret in sorted(secrets, key=len, reverse=True):
                    value = value.replace(secret, "[redacted]")
                return value

            safe = type(error)(
                redact(error.message),
                code=error.code,
                suggestion=redact(error.suggestion),
                docs_url=redact(error.docs_url),
            )
            response = getattr(error.__cause__, "response", None)
            status = getattr(error, "status_code", getattr(response, "status_code", None))
            if isinstance(status, int):
                safe.status_code = status  # type: ignore[attr-defined]
        # Raise after leaving the handler: even a suppressed __context__ would
        # retain the raw HTTP exception, whose request carries the rule secrets.
        raise safe

    async def pause(self, sandbox_id: str) -> None:
        """Pause with memory retained; service admission remains account-specific."""
        await self._sandbox_request("POST", sandbox_id, "/pause", json={"memory": True})

    async def resume(self, sandbox_id: str) -> SandboxInfo:
        """Resume explicitly and return the new session credentials for rebinding."""
        response = await self._sandbox_request(
            "POST", sandbox_id, "/connect", json={"timeout": 300}
        )
        info = self._info(response.json())
        if info.sandbox_id != sandbox_id:
            raise ProviderProtocolError("Resume returned a different sandbox identity.")
        if "status" not in info.model_fields_set:
            info.status = SandboxStatus.RUNNING
        info.timeout = 300
        if info.envd_version:
            from agent_sandbox.transport.http import stream_envelope_for_envd

            self._http._stream_envelope = stream_envelope_for_envd(info.envd_version)
        return info
