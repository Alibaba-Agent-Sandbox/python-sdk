"""Verify explicit MCP resource requests against independent platform metadata."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any

import httpx

from agent_sandbox.models.errors import ProviderResourceNotFoundError, SandboxNotFoundError
from agent_sandbox.transport.config import TransportConfig

if TYPE_CHECKING:
    from agent_sandbox.agent.mcp import SandboxManager


async def verify_created_resources(
    manager: SandboxManager,
    sandbox: Any,
    requested: dict[str, int],
) -> dict[str, Any] | None:
    """Reject unverified overrides and reconcile deletion of only this new resource."""
    if not requested:
        return None
    sandbox_id = manager._sandbox_key(sandbox)
    config = getattr(sandbox, "_config", None)
    frozen_config = config.model_copy(deep=True) if isinstance(config, TransportConfig) else None
    observed: dict[str, int | None] = {"cpu": None, "memory": None}
    try:
        info = await sandbox.refresh_info()
        for field, attribute in (("cpu", "cpu_count"), ("memory", "memory_mb")):
            value = getattr(info, attribute, None)
            if type(value) is int and value > 0:
                observed[field] = value
        if all(observed[field] == value for field, value in requested.items()):
            return None
    except Exception:
        # Provider exceptions can contain URLs, credentials, or private metadata.
        pass

    # Metadata awaits can overlap session shutdown. Never resolve this rollback
    # again by ID: cache removal could fall back to another endpoint, and a
    # replacement handle could belong to different work.
    # Keep ownership until deletion is acknowledged or independent absence is
    # confirmed. A failed rollback must remain available to session cleanup.
    cleanup_acknowledged = False
    with suppress(Exception):
        await sandbox.kill()
        cleanup_acknowledged = True
    cleanup_verified = False
    with suppress(Exception):
        cleanup_verified = await _read_created_metadata(sandbox, frozen_config)
    if cleanup_acknowledged or cleanup_verified:
        async with manager._state_lock:
            manager._forget_sandbox(sandbox_id, sandbox)
    unknown = any(observed[field] is None for field in requested)
    result: dict[str, Any] = {
        "error": (
            "The created sandbox's requested resources could not be verified."
            if unknown
            else "The provider did not apply the requested sandbox resources."
        ),
        "category": "resource_configuration",
        "verified": False,
        "requested_resources": requested,
        "observed_resources": observed,
        "sandbox_id": sandbox_id,
        "cleanup_verified": cleanup_verified,
        "suggestion": (
            "Select or build a template with the required resources, then verify its sandbox "
            "metadata. Retry cleanup of this sandbox ID if cleanup_verified is false."
        ),
    }
    if not cleanup_verified:
        result["recovery_sandbox_id"] = sandbox_id
    return result


async def _read_created_metadata(sandbox: Any, config: TransportConfig | None) -> bool:
    """Use a fresh control plane with the exact created instance's resolved config."""
    from agent_sandbox.api.sandbox import _InfraCloser
    from agent_sandbox.providers.registry import get_provider

    if config is None:
        raise RuntimeError("Created sandbox control-plane configuration is unavailable")
    infra = await get_provider(sandbox.provider).build_infra(config)
    absent = False
    try:
        try:
            await infra.sandbox_protocol.get_info(sandbox.id)
        except (SandboxNotFoundError, ProviderResourceNotFoundError):
            absent = True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            absent = True
    finally:
        await _InfraCloser(infra).close()
    return absent
