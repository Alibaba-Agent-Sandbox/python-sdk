"""Validate and plan one complete template without selecting a workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_sandbox.template_contract import normalize_document

LAUNCH_CONTRACT: dict[str, Any] = json.loads(
    Path(__file__).with_name("launch-v1.json").read_text(encoding="utf-8")
)


def validate_template_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate canonical public v1 intent with owner-defined defaults."""
    return normalize_document(manifest)


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
        "provider-mismatch"
        if body.get("sandbox", {}).get("provider") and body["sandbox"]["provider"] != provider["id"]
        else None
    )
    sandbox = body.get("sandbox", {})
    template = sandbox.get("template", {})
    input_kind = (
        "managed" if "reference" in template else "image" if "image" in template else "source"
    )
    if not (prepared and input_kind == "source") and input_kind not in provider.get(
        "workflow_inputs", []
    ):
        reason = reason or "input-unimplemented"
    startup = (
        "exec" if sandbox.get("start") else "entrypoint" if input_kind != "managed" else "none"
    )
    if startup not in provider.get("startup_modes", []):
        reason = reason or "startup-unimplemented"
    required = set(LAUNCH_CONTRACT["required_operations"]["create"])
    if input_kind == "source" and not prepared:
        required.update(LAUNCH_CONTRACT["required_operations"]["prepare"])
    if sandbox.get("start") or sandbox.get("ready"):
        required.update(LAUNCH_CONTRACT["required_operations"]["start"])
    if sandbox.get("services", {}) or sandbox.get("ports", []):
        required.update(LAUNCH_CONTRACT["required_operations"]["services"])
    missing = required - set(operations)
    return {
        "supported": not missing and reason is None,
        "required_operations": sorted(required),
        "missing_operations": sorted(missing),
        "services": sandbox.get("services", {}),
        **({"reason": reason} if reason else {}),
    }
