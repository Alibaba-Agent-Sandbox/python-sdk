"""Consume the CLI's shared managed-key operation; cloud credential APIs stay provider-owned."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_sandbox.models.errors import InvalidAPIKeyError, ProviderProtocolError

if TYPE_CHECKING:
    from agent_sandbox.transport.config import TransportConfig


async def resolve_sandbox_api_key(config: TransportConfig) -> str:
    """Reuse an explicit key, or resolve an existing AK/SK-managed key through abx.

    The engine owns the official API mapping, private cache, expiry renewal and
    cross-process lock. Resolution cannot create or renew credentials.
    """
    if config.sandbox_api_key and config.sandbox_api_key.strip():
        return config.sandbox_api_key
    if not (config.access_key_id and config.access_key_secret):
        raise InvalidAPIKeyError(
            "Configure a Sandbox API key or both Alibaba Cloud AccessKey credentials.",
            suggestion=(
                "Set ABX_SANDBOX_API_KEY, or ALICLOUD_ACCESS_KEY_ID and "
                "ALICLOUD_ACCESS_KEY_SECRET. AK/SK preparation needs "
                "sandbox:CreateApiKey, sandbox:DescribeApiKey and sandbox:UpdateApiKey "
                "on the target Team's API keys."
            ),
        )
    from agent_sandbox.providers.commands import run_command
    from agent_sandbox.providers.engine_client import abx_dir

    result = await run_command(
        "alicloud-express",
        "api-key.resolve",
        access_key_id=config.access_key_id,
        access_key_secret=config.access_key_secret,
        region=config.region,
        http_timeout=config.http_timeout,
    )
    if not isinstance(result, dict) or not isinstance(result.get("secret_file"), str):
        raise ProviderProtocolError(
            "API-key preparation returned no private file reference; use a matching abx version."
        )
    filename = Path(result["secret_file"])
    directory = abx_dir() / "credentials" / "alicloud-express"
    if filename.parent != directory or not re.fullmatch(r"[a-f0-9]{64}\.json", filename.name):
        raise ProviderProtocolError("API-key preparation returned an unexpected file location.")
    fd: int | None = None
    try:
        if directory.is_symlink() or directory.parent.is_symlink():
            raise ValueError("Credential directory is a symlink")
        fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or (
            os.name != "nt" and stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise ValueError("Credential file is not private")
        with os.fdopen(fd, encoding="utf-8") as stream:
            fd = None
            record = json.load(stream)
        if (
            not isinstance(record, dict)
            or record.get("state") != "ready"
            or record.get("api_key_id") != result.get("api_key_id")
            or record.get("team_id") != result.get("team_id")
            or not isinstance(record.get("api_key_value"), str)
            or not record["api_key_value"].strip()
        ):
            raise ValueError("Credential preparation is incomplete")
        return str(record["api_key_value"])
    except (OSError, ValueError, TypeError) as error:
        raise ProviderProtocolError(
            "Cannot safely read the prepared API key; inspect local credential storage."
        ) from error
    finally:
        if fd is not None:
            os.close(fd)


async def prepare_api_key(
    *, confirm: bool = False, team_id: str | None = None, **config: Any
) -> dict[str, Any]:
    """Explicitly consent to preparing/renewing one Express-managed API key.

    Args:
        confirm: Must be True to authorize a credential-resource mutation.
        team_id: Target Team; omitted uses the API's default Team.
        **config: Canonical Express settings, including access_key_id,
            access_key_secret and region. Defaults come from project/user config.

    Returns:
        Nonsecret credential metadata and its private local file reference.
        The corresponding abx CLI must be installed; no cloud SDK is duplicated.
    """
    from agent_sandbox.models.errors import ProviderTrustError
    from agent_sandbox.providers.commands import run_command

    if confirm is not True:
        raise ProviderTrustError(
            "API-key preparation requires explicit confirm=True.",
            suggestion=(
                "This creates or renews a 30-day Team-scoped API key and stores it "
                "privately on this machine. Required RAM actions: sandbox:CreateApiKey, "
                "sandbox:DescribeApiKey, sandbox:UpdateApiKey."
            ),
        )
    result = await run_command(
        "alicloud-express",
        "api-key.prepare",
        {"team_id": team_id} if team_id is not None else {},
        confirm=True,
        **config,
    )
    if not isinstance(result, dict):
        raise ProviderProtocolError("API-key preparation returned invalid metadata.")
    return result


def prepare_api_key_sync(
    *, confirm: bool = False, team_id: str | None = None, **config: Any
) -> dict[str, Any]:
    """Synchronous explicit preparation; accepts the same inputs as prepare_api_key."""
    from agent_sandbox.utils.async_bridge import run_sync

    return run_sync(prepare_api_key(confirm=confirm, team_id=team_id, **config))


def standard_api_key() -> str | None:
    """Resolve the standard sync/async client's project-config fallback only when needed."""
    from agent_sandbox.transport.config import load_config
    from agent_sandbox.utils.async_bridge import run_sync

    config = load_config(provider="alicloud-express")
    if config.sandbox_api_key:
        return config.sandbox_api_key
    if config.access_key_id or config.access_key_secret:
        return run_sync(resolve_sandbox_api_key(config))
    return None
