"""Distribution composition of pure provider-owned L0 data; no runtime adapters."""

from typing import Any

from agent_sandbox.providers.alicloud_express.config_metadata import (
    DEFAULT_CONFIG as DEFAULT_CONFIG,
)

BUNDLED_CONFIGS: tuple[dict[str, Any], ...] = (DEFAULT_CONFIG,)
BUNDLED_KEYS = tuple(key for entry in BUNDLED_CONFIGS for key in entry["keys"])


def bundled_config(provider_id: str) -> dict[str, Any] | None:
    return next((entry for entry in BUNDLED_CONFIGS if entry["id"] == provider_id), None)
