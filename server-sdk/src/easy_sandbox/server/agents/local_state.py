"""In-memory records behind the local Agents API (definitions, environments, vaults, ...).

Everything here is memory-only: nothing is written to disk and a restart loses it. Records
are owned by a principal; a foreign id and an unknown id are indistinguishable.
"""

from __future__ import annotations

import dataclasses
import threading
import time
import uuid
from typing import Any

from .artifacts import ArtifactStore

__all__ = [
    "LocalState",
    "Record",
    "Registry",
    "SessionMeta",
    "get_state",
    "reset_state",
]


@dataclasses.dataclass
class Record:
    """One owned object: ``data`` is the public view, ``private`` never leaves the process."""

    id: str
    owner: str
    created_at: int
    updated_at: int
    data: dict[str, Any]
    private: dict[str, Any] = dataclasses.field(default_factory=dict)


class Registry:
    """Thread-safe, owner-filtered store of :class:`Record` objects."""

    def __init__(self, prefix: str, *, sep: str = "_", limit: int | None = None) -> None:
        self._prefix = prefix + sep
        self._limit = limit
        self._lock = threading.RLock()
        self._rows: dict[str, Record] = {}

    def full(self, owner: str) -> bool:
        """Whether *owner* reached the configured object limit."""
        if self._limit is None:
            return False
        with self._lock:
            return sum(1 for r in self._rows.values() if r.owner == owner) >= self._limit

    def create(
        self,
        owner: str,
        data: dict[str, Any],
        private: dict[str, Any] | None = None,
        *,
        rid: str | None = None,
    ) -> Record:
        """Store a new record and return it."""
        now = int(time.time())
        record = Record(
            id=rid or self._prefix + uuid.uuid4().hex[:24],
            owner=owner,
            created_at=now,
            updated_at=now,
            data=data,
            private=private or {},
        )
        with self._lock:
            self._rows[record.id] = record
        return record

    def get(self, owner: str, rid: str) -> Record | None:
        """The record when it exists and belongs to *owner*."""
        with self._lock:
            record = self._rows.get(rid)
        return record if record is not None and record.owner == owner else None

    def list(self, owner: str) -> list[Record]:
        """Records of *owner*, oldest first."""
        with self._lock:
            rows = [r for r in self._rows.values() if r.owner == owner]
        rows.sort(key=lambda r: (r.created_at, r.id))
        return rows

    def delete(self, owner: str, rid: str) -> Record | None:
        """Remove and return the record (``None`` when absent or foreign)."""
        with self._lock:
            record = self._rows.get(rid)
            if record is None or record.owner != owner:
                return None
            del self._rows[rid]
        return record

    def touch(self, record: Record) -> None:
        """Advance ``updated_at``."""
        record.updated_at = max(int(time.time()), record.updated_at)


@dataclasses.dataclass
class SessionMeta:
    """What the local API knows about a runtime session beyond the runtime's own state."""

    owner: str
    kind: str = "session"  # session | response
    adapter: str = ""
    spec_name: str = ""
    display_id: str = ""
    display_name: str | None = ""
    display_model: str = ""
    tools_wire: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    definition_id: str | None = None
    environment_id: str | None = None
    vault_ids: list[str] = dataclasses.field(default_factory=list)
    bindings: list[dict[str, str]] = dataclasses.field(default_factory=list)


class LocalState:
    """Every local registry of one server process."""

    def __init__(self) -> None:
        self.definitions = Registry("agent")
        self.environments = Registry("env")
        self.templates = Registry("envtmpl")
        self.vaults = Registry("vlt", limit=_max_vaults())
        self.credentials = Registry("cred")
        self.blobs = Registry("file", sep="-")
        self.responses = Registry("resp")
        self.webhooks = Registry("we")
        self.artifacts = ArtifactStore()
        self.session_meta: dict[str, SessionMeta] = {}
        self.response_latest: dict[str, str] = {}
        self.idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}
        self.lock = threading.RLock()

    def close(self) -> None:
        """Release snapshot storage."""
        self.artifacts.close()


def _max_vaults() -> int:
    import os

    try:
        return max(1, int(os.environ.get("EBX_AGENTS_MAX_VAULTS", "100")))
    except ValueError:
        return 100


_state_lock = threading.Lock()
_state: LocalState | None = None


def get_state() -> LocalState:
    """Process-wide local state."""
    global _state
    with _state_lock:
        if _state is None:
            _state = LocalState()
        return _state


def reset_state() -> None:
    """Drop every local record (tests)."""
    global _state
    with _state_lock:
        old, _state = _state, None
    if old is not None:
        old.close()
