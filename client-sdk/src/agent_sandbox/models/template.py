"""Whole-template launch, server policy and source reference models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Standard capability vocabulary
# ---------------------------------------------------------------------------

STANDARD_CAPABILITIES: frozenset[str] = frozenset(
    {
        "shell",
        "files",
        "code",
        "terminal",
        "ports",
    }
)
"""All recognised capability tokens.  Extensible in future phases."""

DEFAULT_CAPABILITIES: frozenset[str] = frozenset()
"""No runtime operation is inferred when no template or provider is known."""


SERVER_POLICY_TOP_KEYS: frozenset[str] = frozenset(
    {"version", "preset", "base_dir", "groups", "defaults", "auth", "endpoints", "description"}
)
SERVER_POLICY_PRESETS: frozenset[str] = frozenset(
    {"default", "transfer-only", "read-only", "hardened", "locked"}
)
SERVER_GROUP_NAMES: frozenset[str] = frozenset(
    {
        "core",
        "commands",
        "file_ops",
        "process",
        "terminal",
        "system",
        "dev_tools",
        "browser",
        "agents",
    }
)
SERVER_RULE_KEYS: frozenset[str] = frozenset(
    {"enabled", "scopes", "paths", "limits", "params", "audit"}
)
SERVER_PATH_KEYS: frozenset[str] = frozenset({"allow", "deny", "read_only", "symlinks"})
"""Structural vocabulary of the ``server:`` block (mirrors ``agent_sandbox.server.policy``;
the server remains the authority and validates values when it loads the compiled policy)."""


def validate_server_block(block: dict[str, Any]) -> dict[str, Any]:
    """Structurally validate a ``server:`` policy block.

    ``groups`` is an alias list (``[file_ops]`` enables those groups) or a map
    (``{process: false}``); both reach the server unchanged.  Checks key names, the preset and
    the shape of rules; semantic validation (endpoint ids,
    limits, scopes) is done by ``agent-sandbox-server check-config`` against the real server.

    Raises:
        ValueError: An unknown key or a malformed section (the message names the path).
    """

    def keys(mapping: Any, allowed: frozenset[str], where: str) -> dict[str, Any]:
        if not isinstance(mapping, dict):
            raise ValueError(f"{where}: expected a mapping")
        for key in mapping:
            if key not in allowed:
                raise ValueError(f"{where}.{key}: unknown key; allowed: {sorted(allowed)}")
        return mapping

    def rule(value: Any, where: str) -> None:
        body = keys(value, SERVER_RULE_KEYS, where)
        if "enabled" in body and not isinstance(body["enabled"], bool):
            raise ValueError(f"{where}.enabled: expected a boolean")
        if "scopes" in body and not (
            isinstance(body["scopes"], list) and all(isinstance(x, str) for x in body["scopes"])
        ):
            raise ValueError(f"{where}.scopes: expected a list of strings")
        if "paths" in body:
            keys(body["paths"], SERVER_PATH_KEYS, f"{where}.paths")
        for section in ("limits", "params"):
            if section in body and not isinstance(body[section], dict):
                raise ValueError(f"{where}.{section}: expected a mapping")

    def groups(value: Any) -> None:
        if isinstance(value, list):
            if not all(isinstance(x, str) for x in value):
                raise ValueError("server.groups: expected a list of group names")
            for name in value:
                if name not in SERVER_GROUP_NAMES:
                    raise ValueError(
                        f"server.groups: unknown group {name!r}; allowed: "
                        f"{sorted(SERVER_GROUP_NAMES)}"
                    )
            return
        body = keys(value, SERVER_GROUP_NAMES, "server.groups")
        for name, enabled in body.items():
            if not isinstance(enabled, bool):
                raise ValueError(f"server.groups.{name}: expected a boolean")
            if name == "core" and not enabled:
                raise ValueError("server.groups.core: the core group cannot be disabled")

    keys(block, SERVER_POLICY_TOP_KEYS, "server")
    preset = block.get("preset")
    if preset is not None and preset not in SERVER_POLICY_PRESETS:
        raise ValueError(
            f"server.preset: unknown {preset!r}; allowed: {sorted(SERVER_POLICY_PRESETS)}"
        )
    endpoints = block.get("endpoints", {})
    if not isinstance(endpoints, dict):
        raise ValueError("server.endpoints: expected a mapping")
    for name, value in endpoints.items():
        rule(value, f"server.endpoints.{name}")
    if "defaults" in block:
        rule(block["defaults"], "server.defaults")
    if "groups" in block:
        groups(block["groups"])
    return block


__all__ = [
    "STANDARD_CAPABILITIES",
    "DEFAULT_CAPABILITIES",
    "SandboxTemplate",
    "TemplateRef",
    "validate_server_block",
]


# ---- Template model (used by utils/registry.py, api/capability.py) ----


class SandboxTemplate(BaseModel):
    """template.yaml 的 Pydantic 模型。

    构建相关字段（system_packages, python_packages, node_packages,
    commands, copy_files）已移除——实际构建流程直接使用 Dockerfile +
    语言原生依赖文件（requirements.txt / package.json）。
    """

    name: str
    version: str = "1.0.0"
    description: str = ""

    # 环境变量
    env: dict[str, str] = Field(default_factory=dict)

    # 资源规格（可选）
    cpu_count: int | None = None
    memory_mb: int | None = None

    # 端口列表
    ports: list[int] = Field(default_factory=list)

    # 元信息
    author: str = ""
    license: str = ""
    tags: list[str] = Field(default_factory=list)

    spec_version: int
    provides: dict[str, Any]
    start_cmd: str | None = None
    ready_cmd: str | None = None

    server: dict[str, Any] | None = None
    """Declarative SandboxServer policy (the ``server:`` block).  ``None`` keeps the server's
    default behaviour.  Compiled to ``server-policy.json`` by the toolchain."""

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def _reject_removed_keys(cls, data: Any) -> Any:
        from agent_sandbox.workflows.launch import validate_template_manifest

        if isinstance(data, dict) and any(
            k in data
            for k in (
                "custom_commands",
                "system_packages",
                "python_packages",
                "node_packages",
                "copy_files",
            )
        ):
            raise ValueError(
                "retired template fields are not accepted; use Dockerfile and template startup"
            )
        validate_template_manifest(data)
        return data

    @field_validator("server")
    @classmethod
    def _validate_server(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if v is None else validate_server_block(v)

    def discovery_capabilities(self) -> set[str]:
        """Describe exposed ports without claiming platform execution capabilities."""
        return {"ports"} if self.provides else set()


class TemplateRef(BaseModel):
    """Explicit source reference coordinates."""

    owner: str | None = None
    repo: str | None = None
    tag: str | None = None
    path: str | None = None  # 仓库内子目录路径
    is_builtin: bool = False
    registry_url: str = "https://github.com"
    registry_type: str = "github"  # "github" | "local"
    local_path: str | None = None  # 本地目录绝对路径
