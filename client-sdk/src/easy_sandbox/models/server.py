"""Typed models for the in-sandbox SandboxServer HTTP API (``easy_sandbox.server``).

Every response model tolerates unknown fields (``extra="allow"``) so a newer server can add
fields without breaking an older client.
"""

from __future__ import annotations

import base64
import enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from easy_sandbox.models.filesystem import WatchEvent


class _ServerModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #


class ServerFileEntry(_ServerModel):
    """One entry of ``files.list``."""

    name: str
    type: str = "file"
    size: int = 0
    modified: str = ""

    @property
    def is_dir(self) -> bool:
        return self.type == "directory"


class ServerFileInfo(_ServerModel):
    """Result of ``files.stat``; ``exists`` is ``False`` for missing paths."""

    name: str = ""
    path: str = ""
    type: str = "unknown"
    size: int = 0
    permissions: str = ""
    modified: str = ""
    accessed: str = ""
    created: str = ""
    exists: bool = True


class SearchHit(_ServerModel):
    """One match of ``files.search``."""

    name: str
    path: str


class SearchResult(_ServerModel):
    """Result of ``files.search``."""

    results: list[SearchHit] = Field(default_factory=list)
    timed_out: bool = False


class TransferResult(_ServerModel):
    """Result of an upload."""

    path: str
    size: int = Field(default=0, alias="bytes")


class MkdirResult(_ServerModel):
    path: str
    created: bool = True


class MoveResult(_ServerModel):
    source: str
    destination: str


class DeleteResult(_ServerModel):
    path: str = ""
    deleted: bool = True


class ArchiveResult(_ServerModel):
    """Result of ``files.archive``; :attr:`data` is the decoded archive."""

    content_base64: str
    format: str = "tar.gz"
    size: int = Field(default=0, alias="bytes")

    @property
    def data(self) -> bytes:
        return base64.b64decode(self.content_base64)


class ServerWatchEvent(WatchEvent):
    """A change event of ``files.watch`` (``type`` is created / modified / deleted)."""

    is_dir: bool = False


# --------------------------------------------------------------------------- #
# Processes
# --------------------------------------------------------------------------- #


class ShellResult(_ServerModel):
    """Result of ``process.shell``."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    truncated: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class ShellEventType(str, enum.Enum):
    STDOUT = "stdout"
    STDERR = "stderr"
    EXIT = "exit"
    ERROR = "error"


class ShellEvent(_ServerModel):
    """One SSE event of ``process.shell_stream``."""

    event: ShellEventType
    data: str = ""
    exit_code: int | None = None
    error: str = ""


class ServerProcess(_ServerModel):
    """A background process managed by the server."""

    pid: int
    command: str = ""
    state: str = "running"
    started_at: float | None = None
    exit_code: int | None = None

    @property
    def running(self) -> bool:
        return self.state == "running"


class ProcessOutputEvent(_ServerModel):
    seq: int
    stream: str
    data: str = ""


class ProcessOutput(_ServerModel):
    """Captured output of a process started with ``capture_output=True``.

    Pass :attr:`next` as ``since`` on the following call to receive only new events.
    """

    pid: int
    events: list[ProcessOutputEvent] = Field(default_factory=list)
    next: int = 0
    state: str = "running"
    exit_code: int | None = None
    dropped: bool = False

    @property
    def stdout(self) -> str:
        return "".join(e.data for e in self.events if e.stream == "stdout")

    @property
    def stderr(self) -> str:
        return "".join(e.data for e in self.events if e.stream == "stderr")


class StdinResult(_ServerModel):
    pid: int
    written: int = 0
    closed: bool = False


class SignalResult(_ServerModel):
    pid: int
    signal: int = 0


# --------------------------------------------------------------------------- #
# Terminal
# --------------------------------------------------------------------------- #


class PtyCreated(_ServerModel):
    """Result of ``pty.create``."""

    session_id: str
    ws_url: str = ""
    pid: int | None = None


class PtyMessage(_ServerModel):
    """A message received on the PTY WebSocket.

    ``type`` is ``"output"`` (``data`` holds terminal text) or ``"event"`` (``event`` is
    ``started`` / ``exited``).
    """

    type: str
    data: str = ""
    event: str = ""
    session_id: str = ""
    pid: int | None = None


class PtySessionInfo(_ServerModel):
    id: str
    pid: int | None = None
    created_at: float | None = None
    cols: int = 80
    rows: int = 24
    alive: bool = True


# --------------------------------------------------------------------------- #
# System, dev tools, browser
# --------------------------------------------------------------------------- #


class SystemInfo(_ServerModel):
    os: str = ""
    arch: str = ""
    cpu_count: int = 0
    memory_total_mb: int = 0
    memory_available_mb: int = 0
    disk_total_gb: float = 0.0
    disk_free_gb: float = 0.0
    python_version: str = ""
    hostname: str = ""


class SystemMetrics(_ServerModel):
    cpu_load_1m: float = 0.0
    cpu_load_5m: float = 0.0
    cpu_load_15m: float = 0.0
    memory_used_mb: int = 0
    memory_total_mb: int = 0
    memory_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    disk_percent: float = 0.0
    uptime_seconds: float = 0.0


class ListeningPort(_ServerModel):
    port: int
    protocol: str = "tcp"
    address: str = ""
    pid: int | None = None


class PackageInfo(_ServerModel):
    name: str
    version: str = ""


class PackageList(_ServerModel):
    manager: str = "pip"
    packages: list[PackageInfo] = Field(default_factory=list)


class CodeRunResult(_ServerModel):
    """Result of the server's stateless ``code/run``."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    language: str = ""
    execution_time_ms: float = 0.0
    truncated: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class GitFileStatus(_ServerModel):
    path: str
    status: str = ""


class GitStatus(_ServerModel):
    branch: str = ""
    clean: bool = True
    files: list[GitFileStatus] = Field(default_factory=list)


class GitDiff(_ServerModel):
    diff: str = ""
    stats: dict[str, Any] = Field(default_factory=dict)


class BrowserPage(_ServerModel):
    """Result of ``browser.navigate``."""

    url: str = ""
    title: str = ""
    status: int = 0


class BrowserContent(_ServerModel):
    content: str = ""
    url: str = ""
    title: str = ""


class ConsoleLog(_ServerModel):
    logs: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


class ServerCommandArg(_ServerModel):
    name: str
    type: str = "string"
    required: bool = True
    default: Any = None
    description: str = ""


class ServerCommand(_ServerModel):
    """A command registered on the server (``GET /commands``)."""

    name: str
    description: str = ""
    args: list[ServerCommandArg] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


class EndpointPaths(_ServerModel):
    """Path scoping of an endpoint as disclosed to the current identity."""

    allow: list[str] = Field(default_factory=list)
    read_only: bool = False
    deny_count: int = 0
    symlinks: str = "within"


class EndpointInfo(_ServerModel):
    """One endpoint of the ``GET /capabilities`` document (API version 2)."""

    name: str = ""
    method: str = ""
    path: str = ""
    group: str = ""
    streaming: bool = False
    enabled: bool = True
    allowed: bool = True
    reason: str | None = None
    scopes: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    paths: EndpointPaths | None = None


class PathDecision(_ServerModel):
    """Server-authoritative answer of ``POST /capabilities/check``."""

    endpoint: str = ""
    allowed: bool = False
    code: str | None = None
    reason: str | None = None


__all__ = [
    "ArchiveResult",
    "BrowserContent",
    "BrowserPage",
    "CodeRunResult",
    "ConsoleLog",
    "DeleteResult",
    "EndpointInfo",
    "EndpointPaths",
    "GitDiff",
    "GitFileStatus",
    "GitStatus",
    "ListeningPort",
    "MkdirResult",
    "MoveResult",
    "PackageInfo",
    "PackageList",
    "PathDecision",
    "ProcessOutput",
    "ProcessOutputEvent",
    "PtyCreated",
    "PtyMessage",
    "PtySessionInfo",
    "SearchHit",
    "SearchResult",
    "ServerCommand",
    "ServerCommandArg",
    "ServerFileEntry",
    "ServerFileInfo",
    "ServerProcess",
    "ServerWatchEvent",
    "ShellEvent",
    "ShellEventType",
    "ShellResult",
    "SignalResult",
    "StdinResult",
    "SystemInfo",
    "SystemMetrics",
    "TransferResult",
]
