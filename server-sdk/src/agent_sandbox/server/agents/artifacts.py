"""Immutable snapshot copies of the files a CLI reported as written during a turn.

Only paths the adapter reported are copied (Codex ``file_change`` items, Qwen
``write_file`` / ``replace`` tool inputs). The workdir is never scanned. Each copy is
taken with ``O_NOFOLLOW``, must be a regular file, and lands in a 0700 directory.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import shutil
import stat
import tempfile
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .runtime import Session, Turn

__all__ = ["ArtifactStore"]

_MAX_PER_TURN = 100
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024
_SKIP_TOP = {".git"}


def _max_bytes() -> int:
    raw = os.environ.get("ABX_AGENTS_MAX_ARTIFACT_BYTES", "")
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_BYTES
    return value if value > 0 else _DEFAULT_MAX_BYTES


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


class ArtifactStore:
    """Snapshots and their metadata; bytes live under a private directory."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._meta: dict[str, dict[str, Any]] = {}
        self._dir: str | None = None

    def _base(self) -> str:
        with self._lock:
            if self._dir is None:
                configured = os.environ.get("ABX_AGENTS_STATE_DIR", "").strip()
                if configured:
                    self._dir = os.path.join(configured, "artifacts")
                    os.makedirs(self._dir, mode=0o700, exist_ok=True)
                else:
                    self._dir = tempfile.mkdtemp(prefix="abx-agent-artifacts-")
                    atexit.register(self.close)
                os.chmod(self._dir, 0o700)
            return self._dir

    def close(self) -> None:
        """Delete every snapshot held by this store."""
        with self._lock:
            base = self._dir
            self._meta.clear()
            self._dir = None
        if base:
            shutil.rmtree(base, ignore_errors=True)

    # ------------------------------------------------------------------ #
    # Snapshotting (runtime turn hook)
    # ------------------------------------------------------------------ #

    def on_turn_done(
        self, session: Session, turn: Turn, workdir: str, paths: list[tuple[str, str]]
    ) -> None:
        """Copy the reported, still-present regular files of a completed turn."""
        if not paths or turn.status != "completed" or not turn.keep:
            return
        latest: dict[str, str] = {}
        for raw, kind in paths:
            if kind == "delete":
                latest.pop(raw, None)
            else:
                latest[raw] = kind
        root = os.path.realpath(workdir)
        limit = _max_bytes()
        taken = 0
        seen: set[str] = set()
        for raw in latest:
            if taken >= _MAX_PER_TURN:
                break
            copied = self._copy_one(root, raw, limit)
            if copied is None:
                continue
            rel, data = copied
            if rel in seen:
                continue
            seen.add(rel)
            self._store(session.id, turn.id, rel, data)
            taken += 1

    @staticmethod
    def _copy_one(root: str, raw: str, limit: int) -> tuple[str, bytes] | None:
        if not isinstance(raw, str) or not raw or "\x00" in raw:
            return None
        candidate = raw if os.path.isabs(raw) else os.path.join(root, raw)
        candidate = os.path.normpath(candidate)
        parent = os.path.realpath(os.path.dirname(candidate))
        if not _within(parent, root):
            return None
        final = os.path.join(parent, os.path.basename(candidate))
        rel = os.path.relpath(final, root)
        if rel.startswith("..") or rel.split(os.sep)[0] in _SKIP_TOP:
            return None
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(final, flags | getattr(os, "O_NONBLOCK", 0))
        except OSError:
            return None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                return None
            with os.fdopen(fd, "rb", closefd=False) as fh:
                data = fh.read(limit + 1)
        finally:
            os.close(fd)
        if len(data) > limit:
            return None
        return rel.replace(os.sep, "/"), data

    def _store(self, session_id: str, turn_id: str, rel: str, data: bytes) -> None:
        base = self._base()
        artifact_id = "artifact_" + uuid.uuid4().hex[:24]
        directory = os.path.join(base, session_id)
        os.makedirs(directory, mode=0o700, exist_ok=True)
        target = os.path.join(directory, artifact_id)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        record = {
            "id": artifact_id,
            "session_id": session_id,
            "turn_id": turn_id,
            "rel": rel,
            "size_bytes": len(data),
            "created_at": int(time.time()),
            "file": target,
        }
        with self._lock:
            self._meta[artifact_id] = record

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #

    def list(self, session_id: str) -> list[dict[str, Any]]:
        """Snapshots of a session, oldest first."""
        with self._lock:
            rows = [dict(r) for r in self._meta.values() if r["session_id"] == session_id]
        rows.sort(key=lambda r: (r["created_at"], r["id"]))
        return rows

    def get(self, session_id: str, artifact_id: str) -> dict[str, Any] | None:
        """One snapshot record, or ``None``."""
        with self._lock:
            record = self._meta.get(artifact_id)
            if record is None or record["session_id"] != session_id:
                return None
            return dict(record)

    def read(self, record: dict[str, Any]) -> bytes | None:
        """Bytes of a snapshot (``None`` when it vanished)."""
        try:
            with open(record["file"], "rb") as fh:
                return fh.read()
        except OSError:
            return None

    def delete(self, session_id: str, artifact_id: str) -> bool:
        """Remove one snapshot; the file in the workspace is untouched."""
        with self._lock:
            record = self._meta.get(artifact_id)
            if record is None or record["session_id"] != session_id:
                return False
            del self._meta[artifact_id]
        with contextlib.suppress(OSError):
            os.unlink(record["file"])
        return True

    def drop_session(self, session_id: str) -> None:
        """Remove every snapshot of a session."""
        for record in self.list(session_id):
            self.delete(session_id, record["id"])
        if self._dir:
            shutil.rmtree(os.path.join(self._dir, session_id), ignore_errors=True)
