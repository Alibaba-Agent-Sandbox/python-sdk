"""Sandbox-related data models.

字段命名与 camelCase alias 已根据真实 API 实测验证。
Volume mount creation hints follow the published API contract; real storage acceptance is separate.
"""

from __future__ import annotations

import enum
from datetime import datetime  # noqa: TCH003  # Pydantic needs at runtime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from agent_sandbox.models.errors import ProviderConfigError


def validate_volume_mounts(value: Any) -> dict[str, str]:
    """Validate mount-path to existing Volume-name hints without coercing values."""
    if value is None:
        return {}
    if type(value) is not dict:  # noqa: E721 - reject custom dictionary subclasses
        raise ProviderConfigError(
            "volume_mounts must be a dictionary of mount paths to Volume names."
        )
    for path, name in value.items():
        if (
            not isinstance(path, str)
            or path in {"__proto__", "prototype", "constructor"}
            or not path.startswith("/")
            or path == "/"
            or path != path.strip()
            or "\x00" in path
            or any(not part or part.startswith(".") for part in path.split("/")[1:])
            or path.split("/")[1] in {"bin", "opt", "var", "dev"}
        ):
            raise ProviderConfigError(
                "volume_mounts paths must be normalized absolute Unix paths outside "
                "/, /bin, /opt, /var and /dev, without hidden path segments."
            )
        if not isinstance(name, str) or not name.strip() or name != name.strip() or "\x00" in name:
            raise ProviderConfigError("volume_mounts requires nonblank, unpadded Volume names.")
    return dict(value)


class SandboxStatus(str, enum.Enum):
    """Sandbox lifecycle status."""

    CREATING = "creating"  # SDK 自定义过渡态
    RUNNING = "running"  # 已实测验证
    PAUSED = "paused"
    PAUSING = "pausing"  # CubeSandbox while a pause is in progress
    STOPPING = "stopping"  # SDK 自定义过渡态
    STOPPED = "stopped"
    ERROR = "error"


class SandboxConfig(BaseModel):
    """Configuration for creating a sandbox.

    请求体字段使用 camelCase（已实测验证）:
    templateID, timeout, autoPause, metadata, envVars
    """

    template: str = Field(default="base", alias="templateID")
    timeout: int = Field(default=300, ge=1, le=86400, description="Sandbox timeout in seconds")
    auto_pause: bool = Field(default=False, alias="autoPause", description="是否自动暂停")
    metadata: dict[str, str] = Field(default_factory=dict)
    env_vars: dict[str, str] = Field(
        default_factory=dict, alias="envVars", description="环境变量键值对（已实测验证）"
    )
    volume_mounts: dict[str, str] = Field(
        default_factory=dict,
        exclude=True,
        description="Absolute sandbox mount paths mapped to existing Volume names",
    )

    @field_validator("volume_mounts", mode="before")
    @classmethod
    def _mounts(cls, value: Any) -> dict[str, str]:
        return validate_volume_mounts(value)

    # Resource configuration (optional — only sent when explicitly set)
    cpu: int | None = Field(default=None, description="CPU 核数")
    memory: int | None = Field(default=None, description="内存大小 (MB)")
    disk: int | None = Field(default=None, description="磁盘大小 (MB)")
    gpu: str | None = Field(default=None, description="GPU 规格，如 'A10'")
    secure: bool | None = Field(
        default=None,
        exclude=True,
        description="User-requested secure mode; None = not specified",
    )
    provider_options: dict[str, Any] = Field(
        default_factory=dict,
        exclude=True,
        description="Per-create provider options forwarded to plugin providers as 'options'",
    )

    model_config = {"populate_by_name": True}

    def to_create_payload(self) -> dict[str, Any]:
        """Build the create payload; mount serialization follows the published API contract."""
        mounts = validate_volume_mounts(self.volume_mounts)
        payload: dict[str, Any] = {
            "templateID": self.template,
            "timeout": self.timeout,
            "autoPause": self.auto_pause,
            "metadata": self.metadata,
            "envVars": self.env_vars,
        }
        if self.cpu is not None:
            payload["cpuCount"] = self.cpu
        if self.memory is not None:
            payload["memoryMB"] = self.memory
        if self.disk is not None:
            payload["diskSizeMB"] = self.disk
        if self.gpu is not None:
            payload["gpu"] = self.gpu
        if mounts:
            payload["volumeMounts"] = [
                {"name": name, "path": path} for path, name in mounts.items()
            ]
        return payload


class SandboxInfo(BaseModel):
    """Information about an existing sandbox.

    响应字段使用 camelCase（已实测验证）:
    sandboxID, templateID, envdAccessToken, envdVersion, clientID, etc.
    """

    sandbox_id: str = Field(alias="sandboxID")
    template: str = Field(default="", alias="templateID")
    alias_name: str | None = Field(default=None, alias="alias")
    status: SandboxStatus = Field(default=SandboxStatus.RUNNING, alias="state")

    # 认证与版本信息（已实测验证）
    envd_access_token: str | None = Field(default=None, alias="envdAccessToken")
    envd_version: str | None = Field(default=None, alias="envdVersion")
    client_id: str | None = Field(default=None, alias="clientID")
    account_id: str | None = Field(default=None, alias="accountID")
    user_id: str | None = Field(default=None, alias="userID")

    # 时间与资源信息（get_info 额外字段，已实测验证）
    started_at: datetime | None = Field(default=None, alias="startedAt")
    end_at: datetime | None = Field(default=None, alias="endAt")
    cpu_count: int | None = Field(default=None, alias="cpuCount")
    memory_mb: int | None = Field(default=None, alias="memoryMB")
    disk_size_mb: int | None = Field(default=None, alias="diskSizeMB")
    lifecycle: dict[str, Any] | str | None = Field(default=None)

    # 通用字段
    metadata: dict[str, str] = Field(default_factory=dict)
    reported_domain: str | None = Field(default=None, alias="domain")
    timeout: int = 300
    region: str = "cn-hangzhou"
    envd_url: str | None = Field(default=None, alias="envdUrl")

    model_config = {"populate_by_name": True}
