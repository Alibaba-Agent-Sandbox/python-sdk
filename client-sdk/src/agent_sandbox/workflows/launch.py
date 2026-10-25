"""Validate and plan one complete template without selecting a workflow."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

LAUNCH_CONTRACT: dict[str, Any] = json.loads(
    Path(__file__).with_name("launch-v1.json").read_text(encoding="utf-8")
)
_ID = re.compile(r"^[a-z][a-z0-9_-]*$")


def validate_template_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate current launch metadata without inventing application defaults."""
    if not isinstance(manifest, dict):
        raise ValueError("template: expected an object")
    if manifest.get("spec_version") != 5 or type(manifest.get("spec_version")) is not int:
        raise ValueError("template.spec_version: expected 5; migrate retired workflow declarations")
    if any(key in manifest for key in LAUNCH_CONTRACT["retired_keys"]):
        raise ValueError("template: remove retired workflow and capability declarations")
    services = manifest.get("provides")
    if not isinstance(services, dict):
        raise ValueError("template.provides: expected an object")
    for name, service in services.items():
        if not isinstance(name, str) or not _ID.fullmatch(name):
            raise ValueError("provides: invalid service ID")
        if not isinstance(service, dict) or set(service) != set(LAUNCH_CONTRACT["service_keys"]):
            raise ValueError("service: unknown or missing fields")
        if not isinstance(service["protocol"], str) or not service["protocol"]:
            raise ValueError("service.protocol: expected a nonempty string")
        for field, maximum in [("version", LAUNCH_CONTRACT["max_safe_integer"]), ("port", 65535)]:
            value = service[field]
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"service.{field}: expected a bounded integer")
        ops = service["operations"]
        if not isinstance(ops, list) or any(not isinstance(op, str) or not op for op in ops):
            raise ValueError("service.operations: expected nonempty string entries")
        if len(ops) != len(set(ops)):
            raise ValueError("service.operations: duplicate entries")
    for key in ("start_cmd", "ready_cmd", "image", "provider", "template_id"):
        if key in manifest and (not isinstance(manifest[key], str) or not manifest[key].strip()):
            raise ValueError(f"template.{key}: expected a nonempty string")
    if ("provider" in manifest) != ("template_id" in manifest):
        raise ValueError("template: provider and template_id must be declared together")
    if "image" in manifest and "template_id" in manifest:
        raise ValueError("template: image and template_id are mutually exclusive")
    return copy.deepcopy(manifest)


def plan_template_launch(
    manifest: dict[str, Any],
    provider: dict[str, Any],
    consumer: str,
    prepared: bool = False,
) -> dict[str, Any]:
    """Check startup prerequisites; this does not certify runtime readiness.

    ``prepared`` means the caller already has the provider's prepared reference.
    Python does not gain source building through this flag.
    """
    body = validate_template_manifest(manifest)
    entry = LAUNCH_CONTRACT["consumers"].get(consumer)
    if entry is None:
        raise ValueError("consumer: unknown launch entry point")
    if not isinstance(provider.get("id"), str) or not provider["id"]:
        raise ValueError("provider.id: expected a nonempty string")
    if provider.get("operation_contract_version") != 1:
        raise ValueError("provider.operation_contract_version: expected 1")
    operations = provider.get("operations", {}).get(entry)
    if not isinstance(operations, list) or any(not isinstance(op, str) for op in operations):
        raise ValueError("provider.operations: expected consumer operation declarations")
    reason = (
        "provider-mismatch" if body.get("provider") and body["provider"] != provider["id"] else None
    )
    input_kind = "managed" if "template_id" in body else "image" if "image" in body else "source"
    if not (prepared and input_kind == "source") and input_kind not in provider.get(
        "workflow_inputs", []
    ):
        reason = reason or "input-unimplemented"
    startup = (
        "exec" if body.get("start_cmd") else "entrypoint" if input_kind != "managed" else "none"
    )
    if startup not in provider.get("startup_modes", []):
        reason = reason or "startup-unimplemented"
    required = set(LAUNCH_CONTRACT["required_operations"]["create"])
    if input_kind == "source" and not prepared:
        required.update(LAUNCH_CONTRACT["required_operations"]["prepare"])
    if body.get("start_cmd") or body.get("ready_cmd"):
        required.update(LAUNCH_CONTRACT["required_operations"]["start"])
    if body["provides"]:
        required.update(LAUNCH_CONTRACT["required_operations"]["services"])
    missing = required - set(operations)
    return {
        "supported": not missing and reason is None,
        "required_operations": sorted(required),
        "missing_operations": sorted(missing),
        "services": body["provides"],
        **({"reason": reason} if reason else {}),
    }
