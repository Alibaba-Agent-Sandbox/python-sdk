"""Template-related data models.

模板管理 API 响应字段使用 camelCase（已实测验证 POST /templates 返回 templateID, buildID）。
"""

from __future__ import annotations

import enum
from datetime import datetime  # noqa: TC003  # Pydantic needs at runtime
from typing import Any

from pydantic import BaseModel, Field, field_validator

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

DEFAULT_CAPABILITIES: frozenset[str] = frozenset({"shell", "files", "code"})
"""System default baseline — applied when a template declares no capabilities.

``terminal`` and ``ports`` must be declared explicitly by the template.
"""


SERVER_POLICY_TOP_KEYS: frozenset[str] = frozenset(
    {"version", "preset", "base_dir", "groups", "defaults", "auth", "endpoints", "description"}
)
SERVER_POLICY_PRESETS: frozenset[str] = frozenset(
    {"default", "transfer-only", "read-only", "hardened", "locked"}
)
SERVER_RULE_KEYS: frozenset[str] = frozenset(
    {"enabled", "scopes", "paths", "limits", "params", "audit"}
)
SERVER_PATH_KEYS: frozenset[str] = frozenset({"allow", "deny", "read_only", "symlinks"})
"""Structural vocabulary of the ``server:`` block (mirrors ``easy_sandbox.server.policy``;
the server remains the authority and validates values when it loads the compiled policy)."""


def validate_server_block(block: dict[str, Any]) -> dict[str, Any]:
    """Structurally validate a ``server:`` policy block.

    Checks key names, the preset and the shape of rules; semantic validation (endpoint ids,
    limits, scopes) is done by ``easy-sandbox-server check-config`` against the real server.

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
    if "groups" in block and not isinstance(block["groups"], dict):
        raise ValueError("server.groups: expected a mapping")
    return block


class BuildStatus(str, enum.Enum):
    """Template build lifecycle status."""

    BUILDING = "building"
    READY = "ready"
    ERROR = "error"


class TemplateInfo(BaseModel):
    """Information about a template.

    API 响应字段使用 camelCase:
    templateID, buildID, aliases, public, cpuCount, memoryMB, etc.
    """

    template_id: str = Field(alias="templateID")
    build_id: str | None = Field(default=None, alias="buildID")
    aliases: list[str] = Field(default_factory=list, alias="aliases")
    public: bool = Field(default=False)

    @field_validator("aliases", mode="before")
    @classmethod
    def _coerce_aliases(cls, v: Any) -> list[str]:
        """API may return aliases as a string, list, or None."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, (list, tuple)):
            return [str(item) for item in v]
        return [str(v)]

    cpu_count: int | None = Field(default=None, alias="cpuCount")
    memory_mb: int | None = Field(default=None, alias="memoryMB")
    disk_size_mb: int | None = Field(default=None, alias="diskSizeMB")
    start_cmd: str | None = Field(default=None, alias="startCmd")
    build_status: BuildStatus = Field(default=BuildStatus.BUILDING)
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class BuildInfo(BaseModel):
    """Information about a template build.

    GET /templates/{id}/builds/{buildId}/status 响应体。
    """

    build_id: str = Field(alias="buildID")
    template_id: str = Field(default="", alias="templateID")
    status: BuildStatus = Field(default=BuildStatus.BUILDING)
    logs: list[str] = Field(default_factory=list)
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    error: str | None = Field(default=None)

    model_config = {"populate_by_name": True}


__all__ = [
    "STANDARD_CAPABILITIES",
    "DEFAULT_CAPABILITIES",
    "BuildStatus",
    "TemplateInfo",
    "BuildInfo",
    "SandboxTemplate",
    "TemplateRef",
    "CustomCommandArg",
    "CustomCommand",
    "_VALID_ARG_TYPES",
    "validate_server_block",
]


# ---- Custom command models ----


_VALID_ARG_TYPES: frozenset[str] = frozenset({"string", "integer", "float", "boolean"})
"""Allowed values for :attr:`CustomCommandArg.type`."""


class CustomCommandArg(BaseModel):
    """A single argument for a custom command."""

    name: str
    default: str | None = None
    required: bool = False
    description: str = ""
    type: str = "string"
    """Scalar type hint: ``string`` | ``integer`` | ``float`` | ``boolean``."""

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in _VALID_ARG_TYPES:
            raise ValueError(f"Invalid arg type {v!r}; allowed: {sorted(_VALID_ARG_TYPES)}")
        return v


class CustomCommand(BaseModel):
    """A named command exposed by a template.

    ``cmd`` supports ``{placeholder}`` tokens that are filled at runtime
    from the matching :class:`CustomCommandArg` entries.
    """

    cmd: str
    description: str = ""
    cwd: str = "/app"
    env: dict[str, str] = Field(default_factory=dict)
    timeout: int = 60
    args: list[CustomCommandArg] = Field(default_factory=list)


# ---- Template model (used by utils/registry.py, api/capability.py) ----


class SandboxTemplate(BaseModel):
    """template.yaml 的 Pydantic 模型。

    构建相关字段（base, system_packages, python_packages, node_packages,
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

    # ---- Capability model (Phase 1) ----
    capabilities: list[str] | None = None
    """Runtime capabilities.  ``None`` → inherit :data:`DEFAULT_CAPABILITIES`;
    an explicit list overrides the default (may be a subset or include
    ``terminal`` / ``ports``)."""

    custom_commands: dict[str, CustomCommand] = Field(default_factory=dict)
    """Named commands exposed by this template."""

    server: dict[str, Any] | None = None
    """Declarative SandboxServer policy (the ``server:`` block).  ``None`` keeps the server's
    default behaviour.  Compiled to ``server-policy.json`` by the toolchain."""

    model_config = {"extra": "ignore"}

    @field_validator("server")
    @classmethod
    def _validate_server(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if v is None else validate_server_block(v)

    @field_validator("capabilities")
    @classmethod
    def _validate_capabilities(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for cap in v:
                if cap not in STANDARD_CAPABILITIES:
                    raise ValueError(
                        f"Unknown capability {cap!r}; allowed: {sorted(STANDARD_CAPABILITIES)}"
                    )
        return v


class TemplateRef(BaseModel):
    """模板引用解析结果（向后兼容）。"""

    owner: str | None = None
    repo: str | None = None
    tag: str | None = None
    path: str | None = None  # 仓库内子目录路径
    is_builtin: bool = False
    registry_url: str = "https://github.com"
    registry_type: str = "github"  # "github" | "local"
    local_path: str | None = None  # 本地目录绝对路径
