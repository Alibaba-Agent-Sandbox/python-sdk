"""Application control contracts, separate from the sandbox-local Agents API."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Placement = Literal["external", "in-sandbox"]
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "timed_out"})


def canonical(value: Any) -> str:
    """Serialize immutable execution inputs without NaN or non-JSON values."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False
    )


def digest(value: Any) -> str:
    """Return a canonical JSON SHA256 digest."""
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def timestamp(epoch: float) -> str:
    """Format an epoch as an RFC3339 timestamp."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class ApplicationError(Exception):
    """A safe public error; implementation exceptions must never be exposed."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Principal:
    """Authenticated owner and explicitly granted application revisions/scopes."""

    owner: str
    revisions: frozenset[str]
    scopes: frozenset[str] = frozenset({"runs:read", "runs:write"})

    def require(self, scope: str) -> None:
        """Fail closed when the caller lacks an operation scope."""
        if scope not in self.scopes:
            raise ApplicationError(403, "forbidden", "Operation is not authorized")


@dataclass(frozen=True)
class Application:
    """Trusted deployed revision; snapshots contain references, never credentials.

    A revision is immutable. Changing its snapshot requires a new revision ID.
    The application registry is deployment configuration, not user request input.
    """

    revision: str
    placement: Placement
    snapshot: dict[str, Any]
    max_run_seconds: int = 900
    max_tool_seconds: int = 60
    max_concurrent_runs: int = 10
    max_queued_runs: int = 100
    max_runs_per_minute: int = 60
    max_output_bytes: int = 65536
    max_events: int = 10000
    max_artifact_bytes: int = 10485760

    def __post_init__(self) -> None:
        if not self.revision or self.placement not in {"external", "in-sandbox"}:
            raise ValueError("A valid application revision and placement are required")
        for name in (
            "max_run_seconds",
            "max_tool_seconds",
            "max_concurrent_runs",
            "max_queued_runs",
            "max_runs_per_minute",
            "max_output_bytes",
            "max_events",
            "max_artifact_bytes",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if self.max_events < 5:
            raise ValueError("At least five events are required for lifecycle transitions")
        canonical(self.snapshot)

    def execution_snapshot(self) -> dict[str, Any]:
        """Capture deployed inputs and limits so workers cannot silently change them."""
        return {
            "revision": self.revision,
            "placement": self.placement,
            "configuration": json.loads(canonical(self.snapshot)),
            "limits": {
                "runSeconds": self.max_run_seconds,
                "toolSeconds": self.max_tool_seconds,
                "concurrentRuns": self.max_concurrent_runs,
                "queuedRuns": self.max_queued_runs,
                "runsPerMinute": self.max_runs_per_minute,
                "outputBytes": self.max_output_bytes,
                "events": self.max_events,
                "artifactBytes": self.max_artifact_bytes,
            },
        }


@dataclass(frozen=True)
class Artifact:
    """Bounded artifact content copied into durable storage before sandbox cleanup."""

    name: str
    content: bytes
    media_type: str = "application/octet-stream"


@dataclass(frozen=True)
class ExecutionResult:
    """Executor output persisted atomically with terminal state."""

    text: str
    artifacts: tuple[Artifact, ...] = field(default_factory=tuple)


def public_run(row: dict[str, Any]) -> dict[str, Any]:
    """Project internal state without owner, input, credentials or lease data."""
    run_id = row["id"]
    result: dict[str, Any] = {
        "id": run_id,
        "applicationRevision": row["revision"],
        "executionSnapshotDigest": row["snapshot_digest"],
        "placement": row["placement"],
        "status": row["status"],
        "eventIntegrity": row["integrity"],
        "createdAt": timestamp(row["created"]),
        "attemptId": row["attempt"],
        "links": {
            "self": f"/v1/agent-runs/{run_id}",
            "events": f"/v1/agent-runs/{run_id}/events",
        },
    }
    if row["failure"]:
        result["failure"] = {"code": row["failure"], "message": "Run did not complete successfully"}
    return result
