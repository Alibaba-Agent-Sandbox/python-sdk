"""Managed-only instance admission; secret values never enter Session settings."""

from __future__ import annotations

import copy
import re
from typing import Any

from agent_sandbox.models.sandbox import validate_volume_mounts
from agent_sandbox.template_contract import compile_literal_document

_STATE_DIRECTORY = "/home/user/.agent-sandbox"
_RESERVED_METADATA = frozenset({"abx-managed", "abx-session", "abx-revision"})


def validate_env_names(names: Any) -> list[str]:
    """Accept only explicitly declared custom names outside runtime/model controls."""
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise ValueError("Managed instanceEnvNames must be a list of environment names")
    if len(names) != len(set(names)):
        raise ValueError("Managed instanceEnvNames must not contain duplicates")
    for name in names:
        if (
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
            or name
            in {
                "HOME",
                "PATH",
                "SHELL",
                "USER",
                "LOGNAME",
                "ANTHROPIC_API_KEY",
                "DASHSCOPE_API_KEY",
            }
            or name.startswith(("ABX_", "OPENAI_", "QWEN_", "CODEX_", "PYTHON", "LD_"))
        ):
            raise ValueError(
                "Managed custom environment names cannot override runtime/model controls"
            )
    return list(names)


def validate_instance(value: Any, workspace: str, lifetime: int) -> dict[str, Any]:
    """Admit safe Express fields and protect exclusive runtime directories."""
    if not isinstance(value, dict):
        raise ValueError("Managed instance must be an object")
    value = copy.deepcopy(value)
    if "envs" in value:
        raise ValueError(
            "Managed instance environment values belong only in the Worker secret source"
        )
    value.setdefault("timeout", lifetime)
    compiled = compile_literal_document(
        {
            "specVersion": 1,
            "name": "managed",
            "sandbox": {
                "provider": "alicloud-express",
                "template": {"reference": "prepared"},
                "instance": value,
            },
        },
        provider="alicloud-express",
    )
    instance: dict[str, Any] = compiled["sandbox"]["instance"]
    instance.pop("envs")
    lifecycle = instance.get("lifecycle", {})
    if lifecycle.get("onTimeout", "kill") != "kill" or lifecycle.get("autoResume", False):
        raise ValueError("Managed Sessions require kill-on-timeout without automatic resume")
    if _RESERVED_METADATA.intersection(instance["metadata"]):
        raise ValueError("Managed instance metadata cannot override resource ownership")
    mounts = validate_volume_mounts(instance.get("volume_mounts", {}))
    for mount in mounts:
        if any(
            mount == protected
            or mount.startswith(protected + "/")
            or protected.startswith(mount + "/")
            for protected in (workspace.rstrip("/"), _STATE_DIRECTORY)
        ):
            raise ValueError(
                "Managed volume mounts cannot overlap the workspace or private runtime state"
            )
    return instance


def worker_environment(value: Any, names: list[str]) -> dict[str, str]:
    """Resolve only a supplied private map, without process-wide ambient forwarding."""
    names = validate_env_names(names)
    if (
        not isinstance(value, dict)
        or set(value) != set(names)
        or any(not isinstance(item, str) or "\x00" in item for item in value.values())
    ):
        raise ValueError("Worker sandbox environment must exactly match instanceEnvNames")
    return dict(value)
