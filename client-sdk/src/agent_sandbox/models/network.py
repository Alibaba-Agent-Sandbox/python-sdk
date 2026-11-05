"""Validation and wire conversion for explicit sandbox network creation settings."""

from __future__ import annotations

import copy
import json
import re
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


def network_secret_values(network: dict[str, Any] | None) -> set[str]:
    """Find credential-bearing header values without logging or rewriting rules."""
    secrets: set[str] = set()

    def add(value: object) -> None:
        if isinstance(value, str) and value:
            secrets.add(value)
            bearer = re.match(r"^Bearer\s+(.+)$", value, re.IGNORECASE)
            if bearer:
                secrets.add(bearer[1])

    rules = network.get("rules", {}) if isinstance(network, dict) else {}
    if not isinstance(rules, dict):
        return secrets
    for entries in rules.values():
        if not isinstance(entries, list):
            continue
        for rule in entries:
            transform = rule.get("transform") if isinstance(rule, dict) else None
            headers = transform.get("headers") if isinstance(transform, dict) else None
            if not isinstance(headers, dict):
                continue
            for name, value in headers.items():
                add(value)
                if str(name).lower() == "fc.sandbox.network.header-value-replacements":
                    try:
                        replacements = json.loads(value)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(replacements, list):
                        for item in replacements:
                            if isinstance(item, dict):
                                add(item.get("value"))
    # Cloud errors may reflect a JSON-escaped value rather than the literal value.
    return secrets | {json.dumps(value, ensure_ascii=True)[1:-1] for value in secrets}
