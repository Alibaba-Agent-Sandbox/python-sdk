"""Validation and wire conversion for explicit sandbox network creation settings."""

from __future__ import annotations

import copy
from typing import Any

from agent_sandbox.models.errors import ProviderConfigError


def network_create_payload(network: dict[str, Any]) -> dict[str, Any]:
    """Convert supported snake-case network settings without rewriting rule data."""
    names = {
        "allow_out": "allowOut",
        "deny_out": "denyOut",
        "allow_public_traffic": "allowPublicTraffic",
        "mask_request_host": "maskRequestHost",
        "rules": "rules",
    }
    if not isinstance(network, dict) or set(network) - names.keys():
        raise ProviderConfigError(
            "network supports allow_out, deny_out, allow_public_traffic, "
            "mask_request_host and rules."
        )
    for key, value in network.items():
        if key in {"allow_out", "deny_out"} and (
            not isinstance(value, list)
            or any(not isinstance(target, str) or not target.strip() for target in value)
        ):
            raise ProviderConfigError("Network allow_out and deny_out must be lists of targets.")
        if key == "allow_public_traffic" and type(value) is not bool:
            raise ProviderConfigError("Network allow_public_traffic must be a boolean.")
        if key == "mask_request_host" and not isinstance(value, str):
            raise ProviderConfigError("Network mask_request_host must be a string.")
        if key == "rules" and not isinstance(value, dict):
            raise ProviderConfigError("Network rules must be an object.")
    return {names[key]: copy.deepcopy(value) for key, value in network.items()}


def network_has_header_values(network: dict[str, Any] | None) -> bool:
    """Identify credential-bearing rules without copying their secret values."""
    rules = network.get("rules", {}) if isinstance(network, dict) else {}
    if not isinstance(rules, dict):
        return False
    for entries in rules.values():
        if not isinstance(entries, list):
            continue
        for rule in entries:
            transform = rule.get("transform") if isinstance(rule, dict) else None
            headers = transform.get("headers") if isinstance(transform, dict) else None
            if not isinstance(headers, dict):
                continue
            if any(isinstance(value, str) and value for value in headers.values()):
                return True
    return False
