"""Evaluate the shared declarative workflow contract without loading providers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CONTRACT: dict[str, Any] = json.loads(
    Path(__file__).with_name("workflow-v1.json").read_text(encoding="utf-8")
)
_ID = re.compile(r"^[a-z][a-z0-9_-]*$")


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ValueError(f"{where}: expected an object")
    return value


def _keys(value: Any, allowed: list[str], required: list[str], where: str) -> dict[str, Any]:
    body = _mapping(value, where)
    if set(body) - set(allowed) or set(required) - set(body):
        raise ValueError(f"{where}: unknown or missing fields")
    return body


def _strings(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
        raise ValueError(f"{where}: expected nonempty string entries")
    if len(value) != len(set(value)):
        raise ValueError(f"{where}: duplicate entries")
    return value


def _integer(value: Any, low: int, high: int, where: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{where}: expected a bounded safe integer")


def validate_workflow_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate the new workflow portion; retired inputs are always rejected.

    Application topology and unrelated template metadata are validated by the
    template owner. Missing required workflow values never receive old defaults.
    """
    body = _mapping(manifest, "template")
    if any(k in body for k in CONTRACT["retired_keys"]):
        raise ValueError("template: retired capability or coverage fields are not accepted")
    if type(body.get("spec_version")) is not int or body["spec_version"] != 4:
        raise ValueError("template.spec_version: expected 4")
    if (
        type(body.get("workflow_contract_version")) is not int
        or body["workflow_contract_version"] != 1
    ):
        raise ValueError("template.workflow_contract_version: expected 1")
    services = _mapping(body.get("provides"), "provides")
    for key, raw in services.items():
        if not _ID.fullmatch(key):
            raise ValueError("provides: invalid service ID")
        service = _keys(raw, CONTRACT["service_keys"], CONTRACT["service_keys"], "service")
        if not isinstance(service["protocol"], str) or not service["protocol"]:
            raise ValueError("service.protocol: invalid protocol")
        _integer(service["version"], 1, CONTRACT["max_safe_integer"], "service.version")
        _integer(service["port"], 1, 65535, "service.port")
        _strings(service["operations"], "service.operations")
    workflows = _mapping(body.get("workflows"), "workflows")
    default = body.get("default_workflow")
    if not isinstance(default, str) or default not in workflows:
        raise ValueError("default_workflow: must select an existing workflow")
    for key, raw in workflows.items():
        if not _ID.fullmatch(key):
            raise ValueError("workflows: invalid workflow ID")
        flow = _keys(raw, CONTRACT["workflow_keys"], CONTRACT["workflow_required"], "workflow")
        for field, vocabulary in [("kind", "kinds"), ("input", "inputs"), ("startup", "startups")]:
            if flow[field] not in CONTRACT[vocabulary]:
                raise ValueError(f"workflow.{field}: invalid value")
        binding = _keys(
            flow["binding"], CONTRACT["binding_keys"], CONTRACT["binding_keys"], "binding"
        )
        for field, values in CONTRACT["binding_values"].items():
            if binding[field] not in values:
                raise ValueError(f"binding.{field}: invalid value")
        if "required_checks" in flow:
            _strings(flow["required_checks"], "workflow.required_checks")
        operation = flow["operation"]
        if not isinstance(operation, str) or not operation:
            raise ValueError("workflow.operation: expected a nonempty operation")
        extra = _strings(flow["required_operations"], "workflow.required_operations")
        if any(op not in CONTRACT["operations"] for op in extra):
            raise ValueError("workflow.required_operations: unknown operation")
        if flow["kind"] == "application":
            if not isinstance(flow.get("service"), str) or flow["service"] not in services:
                raise ValueError("workflow.service: missing service")
            if operation not in services[flow["service"]]["operations"]:
                raise ValueError("workflow.operation: not provided by service")
        elif "service" in flow:
            raise ValueError("workflow.service: only applications bind services")
        elif operation not in CONTRACT["operations"]:
            raise ValueError("workflow.operation: unknown operation")
        if flow["kind"] == "exec" and operation not in ["exec.run", "exec.stream"]:
            raise ValueError("workflow.operation: exec workflow requires exec operation")
        if flow["kind"] == "interpreter" and not operation.startswith("code."):
            raise ValueError("workflow.operation: interpreter requires code operation")
        if flow["input"] == "service" and flow["startup"] != "none":
            raise ValueError("workflow.startup: external service cannot start a sandbox")
        if flow["startup"] == "exec" and (
            not isinstance(body.get("start_cmd"), str) or not body["start_cmd"].strip()
        ):
            raise ValueError("workflow.startup: exec requires start_cmd")
        if "ready_cmd" in body and (
            not isinstance(body["ready_cmd"], str) or not body["ready_cmd"].strip()
        ):
            raise ValueError("template.ready_cmd: expected a nonempty string")
    return {k: body[k] for k in CONTRACT["template_keys"]}


def plan_workflow(
    manifest: dict[str, Any], provider: dict[str, Any], workflow_id: str, consumer: str
) -> dict[str, Any]:
    """Return the normalized static plan; no environment success is inferred."""
    data = validate_workflow_manifest(manifest)
    if consumer not in CONTRACT["consumers"]:
        raise ValueError("consumer: unknown entry point")
    if not isinstance(workflow_id, str) or workflow_id not in data["workflows"]:
        raise ValueError("workflow_id: unknown workflow")
    if not isinstance(provider.get("id"), str) or not provider["id"]:
        raise ValueError("provider.id: expected a nonempty string")
    if (
        type(provider.get("operation_contract_version")) is not int
        or provider["operation_contract_version"] != 1
    ):
        raise ValueError("provider.operation_contract_version: expected 1")
    declared = _keys(provider.get("operations"), ["cli", "python"], ["cli", "python"], "operations")
    for entry, operations in declared.items():
        if any(op not in CONTRACT["operations"] for op in _strings(operations, entry)):
            raise ValueError("provider.operations: unknown operation")
    for field, allowed in CONTRACT["provider_fields"].items():
        values = _strings(provider.get(field), f"provider.{field}")
        if any(value not in allowed for value in values):
            raise ValueError(f"provider.{field}: unknown value")
    flow = data["workflows"][workflow_id]
    service = data["provides"].get(flow.get("service"))
    requirements: dict[tuple[str, str, str], dict[str, str]] = {}

    def require(operation: str, phase: str, owner: str) -> None:
        if consumer == "native-sdk":
            state, reason = "U", "consumer-unverified"
        elif owner == "consumer":
            support = CONTRACT["clients"].get(consumer, {}).get(service["protocol"], {})
            ok = service["version"] in support.get("versions", []) and operation in support.get(
                "operations", []
            )
            ok = ok and flow["binding"]["transport"] == "http"
            ok = ok and flow["binding"]["caller"] == "host"
            ok = ok and flow["binding"]["endpoint"] in ["provider-port", "explicit-url"]
            state, reason = ("T", "implemented") if ok else ("F", "client-unimplemented")
        elif consumer == "server-client":
            state, reason = "F", "client-unimplemented"
        else:
            entry = "python" if consumer == "python-provider" else "cli"
            ok = operation in declared[entry]
            state, reason = ("T", "implemented") if ok else ("F", "adapter-unimplemented")
        requirements[(operation, phase, owner)] = {
            "operation": operation,
            "phase": phase,
            "owner": owner,
            "state": state,
            "reason": reason,
        }

    roots = {"workflow": flow, "provider": provider, "manifest": manifest}

    def resolve(path: str) -> Any:
        value: Any = roots
        for part in path.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        return value

    for rule in CONTRACT["rules"]:
        match = True
        for key, values in rule["when"].items():
            value: Any = flow
            for part in key.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            match = match and value in values
        match = match and all(resolve(path) is not None for path in rule.get("when_present", []))
        if match:
            for operation in rule["operations"]:
                require(operation, rule["phase"], rule["owner"])
    require(flow["operation"], "before-invoke", "consumer" if service else "provider")
    for operation in flow["required_operations"]:
        require(operation, "before-invoke", "provider")
    for constraint in CONTRACT["constraints"]:
        if not all(flow.get(k) in v for k, v in constraint["when"].items()):
            continue
        left, right = resolve(constraint["left"]), resolve(constraint["right"])
        if left is None or right is None:
            state, reason = "U", "configuration-missing"
        else:
            ok = left in right if constraint["test"] == "member" else left == right
            state, reason = ("T", "implemented") if ok else ("F", constraint["reason"])
        key = (constraint["operation"], constraint["phase"], constraint["owner"])
        requirements[key] = dict(
            zip(
                ["operation", "phase", "owner", "state", "reason"],
                [*key, state, reason],
                strict=True,
            )
        )
    rows = sorted(
        requirements.values(),
        key=lambda r: (CONTRACT["phases"].index(r["phase"]), r["owner"], r["operation"]),
    )
    states = [r["state"] for r in rows]
    state = "F" if "F" in states else "U" if "U" in states else "T"
    return {
        "contract_version": 1,
        "workflow_id": workflow_id,
        "consumer": consumer,
        "state": state,
        "requirements": rows,
        "binding": flow["binding"],
        "kind": flow["kind"],
        "input": flow["input"],
        "service": service,
    }
