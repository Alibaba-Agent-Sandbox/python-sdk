"""Distribution composition for bundled provider metadata; no cloud implementation import."""

from typing import Any

from agent_sandbox.providers.alicloud_express.metadata import CONFIG_METADATA

BUNDLED_CONFIGS: tuple[dict[str, Any], ...] = (CONFIG_METADATA,)
DEFAULT_CONFIG: dict[str, Any] = CONFIG_METADATA
BUNDLED_KEYS = tuple(key for metadata in BUNDLED_CONFIGS for key in metadata["keys"])


def bundled_config(provider_id: str) -> dict[str, Any] | None:
    return next((metadata for metadata in BUNDLED_CONFIGS if metadata["id"] == provider_id), None)
