"""Explicit configuration and safe public errors for the managed Agents API."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

PROTOCOL = "agent-sandbox-managed-agents/v1"
BRIDGE_PROTOCOL = "agent-sandbox-managed-bridge/v1"
TERMINAL = frozenset({"completed", "failed", "cancelled"})
SUBMISSION_TERMINAL = TERMINAL | {"uncertain"}


def canonical(value: Any) -> str:
    """Return stable, finite JSON suitable for immutable request identities."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value: Any) -> str:
    """Hash a JSON request without exposing it in logs."""
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class ManagedError(Exception):
    """A bounded, explicitly public error, never an arbitrary exception string."""

    def __init__(self, status: int, code: str, message: str, param: str | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.param = status, code, message, param

    def body(self) -> dict[str, Any]:
        """Return the documented error envelope."""
        return {
            "error": {
                "type": "invalid_request_error",
                "code": self.code,
                "message": self.message,
                "param": self.param,
            }
        }


def reject_unknown(body: dict[str, Any], allowed: set[str], param: str = "") -> None:
    """Reject unsupported fields instead of silently accepting an unavailable feature."""
    extra = set(body) - allowed
    if extra:
        key = sorted(extra)[0]
        raise ManagedError(400, "unsupported_field", "This field is not supported", param + key)


def metadata(value: Any) -> dict[str, str]:
    """Validate the bounded metadata map used by configuration resources."""
    if value is None:
        return {}
    if (
        not isinstance(value, dict)
        or len(value) > 32
        or any(
            not isinstance(k, str) or not isinstance(v, str) or len(k) > 64 or len(v) > 1024
            for k, v in value.items()
        )
    ):
        raise ManagedError(400, "invalid_metadata", "Expected a bounded string map", "metadata")
    return dict(value)


def text_input(value: Any) -> str:
    """Extract the supported user/input_text subset without accepting other input kinds."""
    if isinstance(value, str) and value.strip():
        result = value
    elif isinstance(value, list) and value:
        parts: list[str] = []
        for message in value:
            if not isinstance(message, dict):
                raise ManagedError(400, "unsupported_input", "Expected user text", "input")
            reject_unknown(message, {"role", "content"}, "input.")
            if message.get("role") != "user" or not isinstance(message.get("content"), list):
                raise ManagedError(400, "unsupported_input", "Expected user text", "input")
            for part in message["content"]:
                if (
                    not isinstance(part, dict)
                    or set(part) != {"type", "text"}
                    or part["type"] != "input_text"
                    or not isinstance(part["text"], str)
                ):
                    raise ManagedError(
                        400, "unsupported_input", "Only input_text is supported", "input"
                    )
                parts.append(part["text"])
        result = "\n".join(parts)
    else:
        raise ManagedError(400, "invalid_input", "A non-empty text input is required", "input")
    if not result.strip() or len(result.encode()) > 262144:
        raise ManagedError(
            413, "input_too_large", "Input is empty or exceeds its byte budget", "input"
        )
    return result


@dataclass(frozen=True)
class ManagedConfig:
    """One immutable deployed revision; all provider/secret resolution is explicit."""

    revision: str
    template: str
    models: dict[str, str]
    application_id: str = "agents-api"
    provider: str = "alicloud-express"
    workspace: str = "/workspace"
    port: int = 9000
    workers: dict[str, str] = field(default_factory=dict)
    model_env_allowlist: list[str] = field(default_factory=list)
    expected_state_id: str | None = None
    sessions: dict[str, int] = field(
        default_factory=lambda: {
            "idleTimeoutSeconds": 900,
            "maxLifetimeSeconds": 3600,
            "maxLogicalSessionsPerOwner": 100,
            "maxActiveSessions": 20,
            "maxQueuedTurnsPerSession": 8,
            "resultRetentionSeconds": 86400,
            "maxConcurrentTurnsPerSession": 1,
        }
    )
    limits: dict[str, int] = field(
        default_factory=lambda: {
            "maxRunSeconds": 600,
            "maxToolSeconds": 60,
            "maxConcurrentRuns": 10,
            "maxQueuedRuns": 80,
            "maxRunsPerMinute": 60,
            "maxEventsPerRun": 10000,
            "maxOutputBytes": 8388608,
            "maxSubscribersPerSession": 4,
        }
    )
    storage: dict[str, int] = field(
        default_factory=lambda: {
            "maxFileBytes": 10485760,
            "maxArtifactBytes": 10485760,
            "maxTurnArtifactBytes": 10485760,
            "maxRetainedBytesPerOwner": 104857600,
        }
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.revision, str)
            or not self.revision
            or not isinstance(self.template, str)
            or not self.template
            or not isinstance(self.models, dict)
            or not self.models
            or self.provider != "alicloud-express"
        ):
            raise ValueError(
                "A revision, template and explicit supported Express/model "
                "configuration are required"
            )
        if any(
            not isinstance(k, str) or not k or len(k) > 128 or v not in {"codex", "qwen-code"}
            for k, v in self.models.items()
        ):
            raise ValueError("Only tested Codex/Qwen adapters may be configured")
        if (
            not isinstance(self.workspace, str)
            or not self.workspace.startswith("/")
            or ".." in self.workspace.split("/")
            or self.workspace == "/"
            or "\x00" in self.workspace
        ):
            raise ValueError("The workspace must be a fixed absolute container directory")
        for mapping in (self.sessions, self.limits, self.storage):
            if any(
                (not isinstance(v, int) or isinstance(v, bool)) or v < 1 for v in mapping.values()
            ):
                raise ValueError("Managed application budgets must be positive integers")
        if (
            not isinstance(self.port, int) or isinstance(self.port, bool)
        ) or not 1 <= self.port <= 65535:
            raise ValueError("The bridge port must be 1-65535")
        if self.sessions["maxConcurrentTurnsPerSession"] != 1:
            raise ValueError("Managed Sessions execute one turn at a time")
        if (
            not self.limits["maxToolSeconds"]
            <= self.limits["maxRunSeconds"]
            <= self.sessions["maxLifetimeSeconds"]
        ):
            raise ValueError("Tool and run budgets must fit the Session lifetime")
        if not isinstance(self.workers, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) or not k or not v
            for k, v in self.workers.items()
        ):
            raise ValueError("Worker revisions must map to explicit function identities")
        if not isinstance(self.model_env_allowlist, list) or any(
            v not in {"OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"}
            for v in self.model_env_allowlist
        ):
            raise ValueError("Only explicit model environment names may be allowed")
        if self.expected_state_id is not None and (
            not isinstance(self.expected_state_id, str)
            or len(self.expected_state_id) != 32
            or any(c not in "0123456789abcdef" for c in self.expected_state_id)
        ):
            raise ValueError("Expected state identity must be a lowercase 32-character hex ID")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ManagedConfig:
        """Parse compiled, non-secret runtime configuration from the deployer."""
        allowed = {
            "revision",
            "template",
            "models",
            "applicationId",
            "provider",
            "workspace",
            "port",
            "workers",
            "modelEnvAllowlist",
            "expectedStateId",
            "sessions",
            "limits",
            "storage",
        }
        if set(value) - allowed:
            raise ValueError("Unknown compiled managed configuration field")
        kwargs: dict[str, Any] = {
            "revision": value["revision"],
            "template": value["template"],
            "models": value["models"],
        }
        for wire, native in (
            ("applicationId", "application_id"),
            ("provider", "provider"),
            ("workspace", "workspace"),
            ("port", "port"),
            ("workers", "workers"),
            ("modelEnvAllowlist", "model_env_allowlist"),
            ("expectedStateId", "expected_state_id"),
        ):
            if wire in value:
                kwargs[native] = value[wire]
        defaults = cls(**kwargs)
        for key in ("sessions", "limits", "storage"):
            if key in value:
                if not isinstance(value[key], dict):
                    raise ValueError("Managed budgets must be objects")
                permitted = set(getattr(defaults, key))
                policies = (
                    {
                        "closePolicy": "release-compute-retain-results",
                        "deletePolicy": "remove-public-data-retain-private-cleanup",
                        "guestRestartPolicy": "freeze-and-reconcile",
                    }
                    if key == "sessions"
                    else {}
                )
                if set(value[key]) - permitted - set(policies):
                    raise ValueError("Unknown managed budget field")
                if any(k in value[key] and value[key][k] != v for k, v in policies.items()):
                    raise ValueError("Unsupported managed lifecycle policy")
                mapping = {k: v for k, v in value[key].items() if k in permitted}
                kwargs[key] = {**getattr(defaults, key), **mapping}
        return cls(**kwargs)
