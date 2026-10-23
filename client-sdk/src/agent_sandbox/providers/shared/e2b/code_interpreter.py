"""Explicitly unavailable interpreter for adapters without a verified wire mapping.

The removed Connect RPC guesses were never a supported interpreter implementation.
The maintained standard SDK is separate; a future provider must implement its own
verified adapter before declaring exact interpreter operations.
"""

from __future__ import annotations

from typing import Any

from agent_sandbox.models.errors import ProviderFeatureNotSupportedError


class UnsupportedCodeProtocol:
    """Fail before transport I/O and never substitute shell execution."""

    def __init__(self, provider_id: str) -> None:
        self._provider_id = provider_id

    async def run_code(
        self, *args: Any, context_id: str | None = None, mode: str = "stateless", **kwargs: Any
    ) -> dict[str, Any]:
        operation = (
            "code.context.execute"
            if context_id is not None
            else "code.default-context.execute"
            if mode == "default-context"
            else "code.execute"
        )
        raise ProviderFeatureNotSupportedError(self._provider_id, operation)

    async def create_context(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ProviderFeatureNotSupportedError(self._provider_id, "code.context.create")

    async def list_contexts(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise ProviderFeatureNotSupportedError(self._provider_id, "code.context.list")

    async def restart_context(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ProviderFeatureNotSupportedError(self._provider_id, "code.context.restart")

    async def remove_context(self, *args: Any, **kwargs: Any) -> None:
        raise ProviderFeatureNotSupportedError(self._provider_id, "code.context.delete")
