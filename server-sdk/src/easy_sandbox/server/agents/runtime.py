"""Hosted agent runtime: sessions, turns, process supervision and event log.

Pure stdlib.  The runtime is independent of HTTP; the wire mappers
(:mod:`.wire_responses`, :mod:`.wire_sessions`) and the routes sit on top.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import logging
import os
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any

from .adapters import AdapterRegistry, TurnContext, default_adapters
from .adapters.base import classify_text
from .config import McpServerSpec
from .errors import AgentNotFoundError, AgentRuntimeError, RuntimeFailure
from .procenv import base_child_env, build_child_env, prepare_workspace, write_invocation_file
from .redact import Redactor
from .store import AgentStore

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from .adapters.base import AgentAdapter, EventParser
    from .config import AgentSpec
    from .events import ParsedEvent

__all__ = [
    "AgentRuntime",
    "Item",
    "RuntimeEvent",
    "Session",
    "Turn",
    "TERMINAL_TURN_STATUSES",
]

try:
    import resource
except ImportError:  # pragma: no cover - non-POSIX
    resource = None  # type: ignore[assignment]

_log = logging.getLogger(__name__)

TERMINAL_TURN_STATUSES = frozenset({"completed", "failed", "cancelled"})
_MAX_LINE = 4 * 1024 * 1024
_MAX_TOOL_OUTPUT = 256 * 1024
_STDERR_KEEP = 16 * 1024
_MAX_QUEUED_TURNS = 32
_MAX_SUBSCRIBERS = 32


def _truthy(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


# ---------------------------------------------------------------------- #
# Data model
# ---------------------------------------------------------------------- #


@dataclasses.dataclass
class Item:
    """One saved unit of agent work (message, reasoning, command, tool call)."""

    id: str
    type: str  # message | reasoning | command_execution | mcp_call
    turn_id: str
    status: str = "in_progress"
    output_index: int = 0
    data: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON snapshot (deep-ish copy)."""
        return {
            "id": self.id,
            "type": self.type,
            "turn_id": self.turn_id,
            "status": self.status,
            "output_index": self.output_index,
            "data": json.loads(json.dumps(self.data, default=str)),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Item:
        """Inverse of :meth:`to_dict`."""
        return cls(
            id=d["id"],
            type=d["type"],
            turn_id=d["turn_id"],
            status=d.get("status", "completed"),
            output_index=int(d.get("output_index", 0)),
            data=dict(d.get("data") or {}),
        )


@dataclasses.dataclass
class Turn:
    """One agent invocation inside a session."""

    id: str
    session_id: str
    agent_name: str
    prompt: str
    status: str = "queued"
    created_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    error: dict[str, str] | None = None
    usage: dict[str, Any] | None = None
    items: list[Item] = dataclasses.field(default_factory=list)
    instructions: str | None = None
    mcp_servers: dict[str, McpServerSpec] = dataclasses.field(default_factory=dict)
    first_seq: int = 0
    input_items: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    keep: bool = True
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)
    cancel: threading.Event = dataclasses.field(default_factory=threading.Event, repr=False)
    done: threading.Event = dataclasses.field(default_factory=threading.Event, repr=False)

    def to_dict(self, *, with_items: bool = False) -> dict[str, Any]:
        """JSON snapshot (never contains secrets)."""
        out: dict[str, Any] = {
            "id": self.id,
            "session_id": self.session_id,
            "agent": self.agent_name,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": dict(self.error) if self.error else None,
            "usage": dict(self.usage) if self.usage else None,
            "prompt": self.prompt,
            "input_items": self.input_items,
            "extra": dict(self.extra),
        }
        if with_items:
            out["items"] = [i.to_dict() for i in self.items]
        return out

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Turn:
        """Inverse of ``to_dict(with_items=True)``."""
        turn = cls(
            id=d["id"],
            session_id=d["session_id"],
            agent_name=d.get("agent", ""),
            prompt=d.get("prompt", ""),
            status=d.get("status", "failed"),
            created_at=float(d.get("created_at") or 0),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            error=d.get("error"),
            usage=d.get("usage"),
            input_items=list(d.get("input_items") or []),
            extra=dict(d.get("extra") or {}),
        )
        turn.items = [Item.from_dict(i) for i in d.get("items") or []]
        if turn.status in TERMINAL_TURN_STATUSES:
            turn.done.set()
        return turn


@dataclasses.dataclass
class RuntimeEvent:
    """One entry of a session's ordered event log."""

    seq: int
    type: str
    session_id: str
    turn_id: str | None
    data: dict[str, Any]
    ts: float


class Session:
    """A conversation with one agent definition; owns an ordered event log."""

    def __init__(
        self,
        session_id: str,
        agent_name: str,
        created_at: float,
        metadata: dict[str, str] | None = None,
        *,
        event_buffer: int = 20000,
    ) -> None:
        self.id = session_id
        self.agent_name = agent_name
        self.created_at = created_at
        self.last_active_at = created_at
        self.metadata: dict[str, str] = dict(metadata or {})
        self.native_session_id: str | None = None
        self.turns: list[Turn] = []
        self.queue: collections.deque[Turn] = collections.deque()
        self.active: Turn | None = None
        self.worker_running = False
        self.closed = False
        self.subscribers = 0
        self.idempotency: collections.OrderedDict[str, str] = collections.OrderedDict()
        self.subagents: dict[str, dict[str, Any]] = {}
        self.cond = threading.Condition(threading.RLock())
        self._events: list[RuntimeEvent] = []
        self._base = 1
        self._next_seq = 1
        self._cap = event_buffer

    @property
    def status(self) -> str:
        """``in_progress`` while a turn is running or queued, else ``idle``."""
        with self.cond:
            return "in_progress" if (self.active is not None or self.queue) else "idle"

    @property
    def last_seq(self) -> int:
        """Sequence number of the newest event (0 when empty)."""
        with self.cond:
            return self._next_seq - 1

    def emit(self, type_: str, turn_id: str | None = None, **data: Any) -> RuntimeEvent:
        """Append an event and wake subscribers."""
        with self.cond:
            event = RuntimeEvent(self._next_seq, type_, self.id, turn_id, data, time.time())
            self._next_seq += 1
            self._events.append(event)
            overflow = len(self._events) - self._cap
            if overflow > 0:
                drop = max(overflow, self._cap // 10)
                del self._events[:drop]
                self._base += drop
            self.last_active_at = event.ts
            self.cond.notify_all()
            return event

    def events_after(self, after: int) -> list[RuntimeEvent]:
        """Events with ``seq > after`` still in the buffer."""
        with self.cond:
            idx = max(0, after + 1 - self._base)
            return list(self._events[idx:])

    def subscribe(
        self, after: int | None = None, *, ping_s: float = 15.0
    ) -> Iterator[RuntimeEvent | None]:
        """Iterate events after *after* (``None`` → only new events).

        Yields ``None`` after *ping_s* seconds without events (keep-alive tick).
        The iterator ends when the session is closed/deleted.
        """
        with self.cond:
            if self.subscribers >= _MAX_SUBSCRIBERS:
                raise AgentRuntimeError("too many concurrent subscribers for this session")
            self.subscribers += 1
            cursor = (self._next_seq - 1) if after is None else after
        try:
            while True:
                batch: list[RuntimeEvent] | None
                with self.cond:
                    while True:
                        idx = max(0, cursor + 1 - self._base)
                        if idx < len(self._events):
                            batch = self._events[idx : idx + 256]
                            break
                        if self.closed:
                            return
                        if not self.cond.wait(timeout=ping_s):
                            batch = None
                            break
                if batch is None:
                    yield None
                    continue
                for event in batch:
                    cursor = event.seq
                    yield event
        finally:
            with self.cond:
                self.subscribers -= 1

    def to_dict(self, *, with_turns: bool = False) -> dict[str, Any]:
        """JSON snapshot (persisted form when ``with_turns``)."""
        with self.cond:
            out: dict[str, Any] = {
                "id": self.id,
                "agent": self.agent_name,
                "created_at": self.created_at,
                "last_active_at": self.last_active_at,
                "metadata": dict(self.metadata),
                "native_session_id": self.native_session_id,
                "status": self.status,
            }
            if with_turns:
                out["turns"] = [t.to_dict(with_items=True) for t in self.turns if t.keep]
            return out


# ---------------------------------------------------------------------- #
# Turn building (ParsedEvent -> items + runtime events)
# ---------------------------------------------------------------------- #


class _TextStream:
    """Accumulates streamed text; releases it only when it cannot contain a split secret."""

    def __init__(self, redactor: Redactor) -> None:
        self._redactor = redactor
        self.raw = ""
        self._cut = 0

    def push(self, text: str) -> tuple[str, str]:
        """Add *text*; returns ``(redacted_delta, redacted_safe_total)``."""
        self.raw += text
        cut = self._redactor.safe_cut(self.raw)
        delta = self._redactor.redact(self.raw[self._cut : cut]) if cut > self._cut else ""
        self._cut = max(self._cut, cut)
        return delta, self._redactor.redact(self.raw[: self._cut])

    def flush(self) -> tuple[str, str]:
        """Release everything; returns ``(redacted_rest, redacted_total)``."""
        rest = self._redactor.redact(self.raw[self._cut :])
        self._cut = len(self.raw)
        return rest, self._redactor.redact(self.raw)


class _TurnBuilder:
    """Turns :class:`ParsedEvent` streams into items and session events."""

    def __init__(self, session: Session, turn: Turn, redactor: Redactor, runtime_name: str) -> None:
        self.session = session
        self.turn = turn
        self.redactor = redactor
        self.runtime_name = runtime_name
        self.turn_cwd: str | None = None
        self._native: dict[str, Item] = {}
        self._streams: dict[str, _TextStream] = {}
        self._pending_message: Item | None = None
        self.fatal: tuple[str, str] | None = None
        self.result_ok: bool | None = None
        self.result_text: str | None = None
        self.result_stop: str | None = None
        self._usage: dict[str, Any] = {}
        self.saw_message = False
        self._started_at: dict[str, float] = {}
        self.reported_paths: list[tuple[str, str]] = []
        self._file_items: dict[str, list[tuple[str, str]]] = {}

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _field(item: Item) -> tuple[str, str]:
        """``(data field, delta kind)`` for the streamed text of *item*."""
        if item.type == "message":
            return "text", "text"
        if item.type == "reasoning":
            return "text", "reasoning"
        return "output", "output"

    def _new_item(self, type_: str, native_id: str | None, **data: Any) -> Item:
        self._flush_pending_message("commentary")
        item = Item(
            id="item_" + uuid.uuid4().hex[:24],
            type=type_,
            turn_id=self.turn.id,
            output_index=len(self.turn.items),
            data=data,
        )
        self.turn.items.append(item)
        if native_id is not None:
            self._native[native_id] = item
        self.session.emit("item.added", self.turn.id, item=item.to_dict())
        return item

    def _flush_pending_message(self, phase: str) -> None:
        item = self._pending_message
        if item is None:
            return
        self._pending_message = None
        item.status = "completed"
        item.data["phase"] = phase
        self.session.emit("item.done", self.turn.id, item=item.to_dict())

    def _push(self, item: Item, text: str) -> None:
        field, kind = self._field(item)
        stream = self._streams.setdefault(item.id, _TextStream(self.redactor))
        delta, safe_total = stream.push(text)
        item.data[field] = safe_total
        if delta:
            self.session.emit(
                "item.delta",
                self.turn.id,
                item_id=item.id,
                kind=kind,
                delta=delta,
                output_index=item.output_index,
            )

    def _close_text(self, item: Item, final: str | None) -> None:
        """Release held-back text and store the authoritative, redacted final text."""
        field, kind = self._field(item)
        stream = self._streams.pop(item.id, None)
        if stream is None:
            if final is not None:
                item.data[field] = self.redactor.redact(final)[:_MAX_TOOL_OUTPUT]
            return
        if final is not None and final != stream.raw and final.startswith(stream.raw):
            stream.push(final[len(stream.raw) :])
        rest, total = stream.flush()
        if rest:
            self.session.emit(
                "item.delta",
                self.turn.id,
                item_id=item.id,
                kind=kind,
                delta=rest,
                output_index=item.output_index,
            )
        item.data[field] = (self.redactor.redact(final) if final is not None else total)[
            :_MAX_TOOL_OUTPUT
        ]

    def _text_item(self, native_id: str | None, type_: str) -> Item:
        item = self._native.get(native_id) if native_id is not None else None
        if item is None:
            item = self._new_item(type_, native_id, text="")
            if type_ == "message":
                item.data["phase"] = None
        return item

    # -- event handling ------------------------------------------------ #

    def handle(self, pe: ParsedEvent) -> None:
        """Apply one parsed event."""
        kind = pe.kind
        if kind == "session":
            if pe.text:
                self.session.native_session_id = pe.text
        elif kind in ("text_delta", "reasoning_delta"):
            item = self._text_item(pe.item_id, "message" if kind == "text_delta" else "reasoning")
            if item.status == "in_progress" and pe.text:
                self._push(item, pe.text)
        elif kind in ("message", "reasoning"):
            existing = self._native.get(pe.item_id) if pe.item_id is not None else None
            item = existing or self._text_item(pe.item_id, kind)
            text = pe.text or ""
            if existing is None and text:
                self._push(item, text)
            self._close_text(item, text if (existing is not None or text) else None)
            if kind == "message":
                self.saw_message = True
                self._pending_message = item
            else:
                item.status = "completed"
                self.session.emit("item.done", self.turn.id, item=item.to_dict())
        elif kind == "tool_start":
            self._tool_start(pe)
        elif kind == "tool_output":
            item = self._native.get(pe.item_id or "")
            if item is not None and pe.text:
                self._push(item, pe.text)
        elif kind == "tool_end":
            self._tool_end(pe)
        elif kind == "subagent":
            self._subagent(pe)
        elif kind == "usage":
            for key in ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens"):
                self._usage[key] = int(self._usage.get(key, 0)) + int(pe.data.get(key) or 0)
            if pe.data.get("cost_usd") is not None:
                self._usage["cost_usd"] = float(self._usage.get("cost_usd", 0.0)) + float(
                    pe.data["cost_usd"]
                )
        elif kind == "error":
            if pe.data.get("fatal"):
                code = str(pe.data.get("code") or "internal_error")
                text = pe.text or "agent error"
                if code == "internal_error":
                    code = classify_text(text)
                self.fatal = (code, self.redactor.redact(text)[:2000])
        elif kind == "result":
            self.result_ok = bool(pe.data.get("ok"))
            self.result_text = pe.text
            self.result_stop = pe.data.get("stop_reason")

    def _tool_start(self, pe: ParsedEvent) -> None:
        data = pe.data
        kind = str(data.get("kind") or "other")
        arguments = self.redactor.redact_obj(data.get("arguments"))
        if kind == "command":
            item = self._new_item(
                "command_execution",
                pe.item_id,
                command=self.redactor.redact(str(data.get("command") or "")),
                cwd=self.turn_cwd,
                output="",
                exit_code=None,
                kind="command",
                arguments=arguments,
            )
        else:
            item = self._new_item(
                "mcp_call",
                pe.item_id,
                kind=kind,
                server_label=str(data.get("server") or self.runtime_name),
                name=str(data.get("name") or "tool"),
                arguments=arguments,
                output=None,
                error=None,
            )
        self._started_at[item.id] = time.monotonic()
        paths = _reported_paths(kind, str(data.get("name") or ""), data.get("arguments"))
        if paths:
            self._file_items[item.id] = paths

    def _subagent(self, pe: ParsedEvent) -> None:
        """Record a subagent id (and its own stream entries) the CLI emitted."""
        op = pe.data.get("op")
        now = time.time()
        redact = self.redactor.redact
        with self.session.cond:
            for raw_id in pe.data.get("ids") or []:
                sid = str(raw_id)
                if not sid:
                    continue
                record = self.session.subagents.get(sid)
                if record is None:
                    record = {
                        "id": sid,
                        "name": None,
                        "instructions": None,
                        "opened_at": now,
                        "closed_at": None,
                        "source": self.runtime_name,
                        "turn_id": self.turn.id,
                        "entries": [],
                    }
                    self.session.subagents[sid] = record
                name = pe.data.get("name")
                if name and not record["name"]:
                    record["name"] = redact(str(name))[:256]
                prompt = pe.data.get("prompt")
                if prompt and not record["instructions"]:
                    record["instructions"] = redact(str(prompt))[:8192]
                if op == "close" and record["closed_at"] is None:
                    record["closed_at"] = now
                entry = pe.data.get("entry")
                if op == "event" and isinstance(entry, dict) and len(record["entries"]) < 2000:
                    clean = self.redactor.redact_obj(entry)
                    if isinstance(clean, dict):
                        _merge_subagent_entry(record["entries"], clean)

    def _tool_end(self, pe: ParsedEvent) -> None:
        item = self._native.get(pe.item_id or "")
        if item is None:
            return
        self._close_text(item, pe.text)
        started = self._started_at.pop(item.id, None)
        ok = bool(pe.data.get("ok", True))
        if item.type == "command_execution":
            item.data["exit_code"] = pe.data.get("exit_code")
            if started is not None:
                item.data["duration_ms"] = int((time.monotonic() - started) * 1000)
        elif pe.data.get("error"):
            item.data["error"] = self.redactor.redact(str(pe.data["error"]))[:4000]
        elif not ok:
            item.data["error"] = item.data.get("output") or "tool call failed"
        item.status = "completed" if ok else "failed"
        if ok and item.id in self._file_items:
            self.reported_paths.extend(self._file_items[item.id])
        self.session.emit("item.done", self.turn.id, item=item.to_dict())

    # -- completion ---------------------------------------------------- #

    def finalize(self, *, aborted: bool) -> None:
        """Close open items; synthesise a message from the CLI result when needed."""
        if not self.saw_message and self.result_text and not aborted:
            self.handle(_msg_event(self.result_text))
        self._flush_pending_message("final_answer")
        for item in self.turn.items:
            if item.status == "in_progress":
                self._close_text(item, None)
                if item.type in ("message", "reasoning"):
                    item.status = "incomplete"
                    if item.type == "message" and item.data.get("phase") is None:
                        item.data["phase"] = "final_answer"
                else:
                    item.status = "failed"
                self.session.emit("item.done", self.turn.id, item=item.to_dict())
        if self._usage:
            total = int(self._usage.get("input_tokens", 0)) + int(
                self._usage.get("output_tokens", 0)
            )
            self.turn.usage = {**self._usage, "total_tokens": total}


_WRITE_TOOLS = frozenset({"write_file", "replace", "edit", "write", "multiedit", "edit_file"})
_PATH_KEYS = ("file_path", "path", "absolute_path")


def _reported_paths(kind: str, name: str, arguments: Any) -> list[tuple[str, str]]:
    """Paths a tool call reports as written: ``(path, add|update|delete)``."""
    out: list[tuple[str, str]] = []
    if kind == "file_change" and isinstance(arguments, dict):
        for change in arguments.get("changes") or []:
            if isinstance(change, dict) and isinstance(change.get("path"), str):
                action = str(change.get("kind") or "update")
                out.append((change["path"], "delete" if action == "delete" else action))
    elif kind == "other" and name.lower() in _WRITE_TOOLS and isinstance(arguments, dict):
        for key in _PATH_KEYS:
            if isinstance(arguments.get(key), str) and arguments[key]:
                out.append((arguments[key], "update"))
                break
    return out


def _merge_subagent_entry(entries: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    """Append *entry*; a tool result is folded into its tool call."""
    if entry.get("kind") == "tool_result":
        for existing in reversed(entries):
            if existing.get("kind") == "tool_call" and existing.get("call_id") == entry.get(
                "call_id"
            ):
                existing["output"] = entry.get("output")
                existing["ok"] = entry.get("ok", True)
                return
        return
    entries.append(entry)


def _msg_event(text: str) -> ParsedEvent:
    from .events import message

    return message("result-text", text)


# ---------------------------------------------------------------------- #
# Runtime
# ---------------------------------------------------------------------- #


class AgentRuntime:
    """Owns sessions, runs turns as supervised subprocesses, persists state."""

    def __init__(
        self,
        store: AgentStore | None = None,
        adapters: AdapterRegistry | None = None,
        *,
        state_dir: str | None = None,
        persist: bool | None = None,
        max_concurrent_turns: int | None = None,
        max_sessions: int = 200,
        session_ttl_s: float = 24 * 3600.0,
        event_buffer: int = 20000,
        kill_grace_s: float = 5.0,
        term_grace_s: float = 3.0,
        poll_interval_s: float = 0.05,
        environ: Mapping[str, str] | None = None,
        id_factory: Callable[[str], str] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._environ: Mapping[str, str] = os.environ if environ is None else environ
        env = self._environ
        self.adapters = adapters if adapters is not None else default_adapters()
        self.store = (
            store
            if store is not None
            else AgentStore(
                self.adapters, allow_command=_truthy(env.get("EBX_AGENTS_ALLOW_COMMAND"), True)
            )
        )
        self.allow_install = _truthy(env.get("EBX_AGENTS_ALLOW_INSTALL"), False)
        self.lock_definitions = _truthy(env.get("EBX_AGENTS_LOCK_DEFINITIONS"), False)
        self.max_sessions = max_sessions
        self.session_ttl_s = session_ttl_s
        self.event_buffer = event_buffer
        self.kill_grace_s = kill_grace_s
        self.term_grace_s = term_grace_s
        self.poll_interval_s = poll_interval_s
        self._clock = clock
        self._id_factory = id_factory or (lambda prefix: f"{prefix}_{uuid.uuid4().hex[:24]}")
        slots = max_concurrent_turns
        if slots is None:
            try:
                slots = int(env.get("EBX_AGENTS_MAX_CONCURRENT_TURNS", "4"))
            except ValueError:
                slots = 4
        self._slots = threading.BoundedSemaphore(max(1, slots))
        self._sessions: dict[str, Session] = {}
        self._turn_index: dict[str, str] = {}
        self._lock = threading.RLock()
        self._health_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self.turn_hooks: list[Callable[[Session, Turn, str, list[tuple[str, str]]], None]] = []
        if persist is None:
            persist = _truthy(env.get("EBX_AGENTS_PERSIST"), True)
        self._state_path: str | None = None
        if persist:
            base = (
                state_dir
                or env.get("EBX_AGENTS_STATE_DIR")
                or os.path.join(os.path.expanduser("~"), ".easy-sandbox", "agents")
            )
            self._state_path = os.path.join(base, "sessions.json")
            self._load_state()

    # ------------------------------------------------------------------ #
    # Sessions
    # ------------------------------------------------------------------ #

    def create_session(self, agent_name: str, metadata: dict[str, str] | None = None) -> Session:
        """Create an idle session bound to the definition *agent_name*."""
        self.store.require(agent_name)
        self._evict()
        session = Session(
            self._id_factory("agsess"),
            agent_name,
            self._clock(),
            metadata,
            event_buffer=self.event_buffer,
        )
        with self._lock:
            self._sessions[session.id] = session
        self._save_state()
        return session

    def get_session(self, session_id: str) -> Session:
        """Look up a session (raises :class:`AgentNotFoundError`)."""
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise AgentNotFoundError(f"session {session_id!r} not found", param="session_id")
        return session

    def list_sessions(self) -> list[Session]:
        """All sessions, oldest first."""
        with self._lock:
            return sorted(self._sessions.values(), key=lambda s: (s.created_at, s.id))

    def delete_session(self, session_id: str) -> None:
        """Cancel active work and forget the session."""
        session = self.get_session(session_id)
        with session.cond:
            session.closed = True
            pending = list(session.queue)
            session.queue.clear()
            active = session.active
            session.cond.notify_all()
        for turn in pending:
            self._finish_unrun(session, turn, "cancelled")
        if active is not None:
            active.cancel.set()
            active.done.wait(timeout=self.kill_grace_s + self.term_grace_s + 5)
        with self._lock:
            self._sessions.pop(session_id, None)
            for turn in session.turns:
                self._turn_index.pop(turn.id, None)
        self._save_state()

    def find_turn(self, turn_id: str) -> tuple[Session, Turn]:
        """Resolve a turn id across sessions."""
        with self._lock:
            session_id = self._turn_index.get(turn_id)
            session = self._sessions.get(session_id) if session_id else None
        if session is not None:
            for turn in session.turns:
                if turn.id == turn_id:
                    return session, turn
        raise AgentNotFoundError(f"turn {turn_id!r} not found", param="turn_id")

    def _evict(self) -> None:
        now = self._clock()
        with self._lock:
            idle = [s for s in self._sessions.values() if s.status == "idle" and not s.subscribers]
            expired = [s for s in idle if now - s.last_active_at > self.session_ttl_s]
            overflow = len(self._sessions) - len(expired) - self.max_sessions + 1
            victims = list(expired)
            if overflow > 0:
                rest = sorted((s for s in idle if s not in expired), key=lambda s: s.last_active_at)
                victims += rest[:overflow]
            for session in victims:
                session.closed = True
                with session.cond:
                    session.cond.notify_all()
                self._sessions.pop(session.id, None)
                for turn in session.turns:
                    self._turn_index.pop(turn.id, None)

    # ------------------------------------------------------------------ #
    # Turns
    # ------------------------------------------------------------------ #

    def submit(
        self,
        session: Session,
        prompt: str,
        *,
        instructions: str | None = None,
        mcp_servers: Mapping[str, McpServerSpec] | None = None,
        keep: bool = True,
        input_items: list[dict[str, Any]] | None = None,
        idempotency_key: str | None = None,
        turn_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Turn:
        """Queue a turn; execution starts immediately when the session is idle."""
        self.store.require(session.agent_name)
        with session.cond:
            if session.closed:
                raise AgentNotFoundError(f"session {session.id!r} was deleted", param="session_id")
            if idempotency_key and idempotency_key in session.idempotency:
                existing = session.idempotency[idempotency_key]
                for turn in session.turns:
                    if turn.id == existing:
                        return turn
            if len(session.queue) >= _MAX_QUEUED_TURNS:
                raise AgentRuntimeError("too many queued turns for this session")
            turn = Turn(
                id=turn_id or self._id_factory("turn"),
                session_id=session.id,
                agent_name=session.agent_name,
                prompt=prompt,
                created_at=self._clock(),
                instructions=instructions,
                mcp_servers=dict(mcp_servers or {}),
                keep=keep,
                input_items=list(input_items or []),
                extra=dict(extra or {}),
            )
            session.turns.append(turn)
            if idempotency_key:
                session.idempotency[idempotency_key] = turn.id
                while len(session.idempotency) > 256:
                    session.idempotency.popitem(last=False)
            with self._lock:
                self._turn_index[turn.id] = session.id
            session.queue.append(turn)
            turn.first_seq = session.last_seq + 1
            start_worker = not session.worker_running
            if start_worker:
                session.worker_running = True
                session.emit("session.in_progress", None, status="in_progress")
            session.emit("turn.queued", turn.id, turn=turn.to_dict())
        if start_worker:
            threading.Thread(
                target=self._drain, args=(session,), name=f"agent-{session.id}", daemon=True
            ).start()
        return turn

    def cancel_turn(self, turn: Turn) -> None:
        """Cancel a queued or running turn (idempotent)."""
        session = self.get_session(turn.session_id)
        with session.cond:
            if turn in session.queue:
                session.queue.remove(turn)
                queued = True
            else:
                queued = False
        if queued:
            self._finish_unrun(session, turn, "cancelled")
        else:
            turn.cancel.set()

    def cancel_active(self, session: Session) -> Turn | None:
        """Cancel the session's active turn; returns it (``None`` when idle)."""
        with session.cond:
            active = session.active
        if active is not None:
            active.cancel.set()
        return active

    def wait(self, turn: Turn, timeout: float | None = None) -> bool:
        """Block until *turn* is terminal."""
        return turn.done.wait(timeout)

    def _finish_unrun(self, session: Session, turn: Turn, status: str) -> None:
        turn.status = status
        turn.completed_at = self._clock()
        session.emit(f"turn.{status}", turn.id, turn=turn.to_dict())
        turn.done.set()
        with session.cond:
            idle = session.active is None and not session.queue
        if idle:
            session.emit("session.idle", None, status="idle")
        self._save_state()

    def _drain(self, session: Session) -> None:
        try:
            while True:
                with session.cond:
                    if not session.queue:
                        session.worker_running = False
                        session.active = None
                        break
                    turn = session.queue.popleft()
                    session.active = turn
                try:
                    self._execute(session, turn)
                except Exception:
                    _log.exception("unexpected error while executing turn %s", turn.id)
                    if not turn.done.is_set():
                        turn.status = "failed"
                        turn.error = {"code": "internal_error", "message": "internal runtime error"}
                        turn.completed_at = self._clock()
                        session.emit("turn.failed", turn.id, turn=turn.to_dict())
                        turn.done.set()
                finally:
                    with session.cond:
                        session.active = None
            session.emit("session.idle", None, status="idle")
        finally:
            with session.cond:
                session.worker_running = False
            self._save_state()

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #

    def _execute(self, session: Session, turn: Turn) -> None:
        while not self._slots.acquire(timeout=self.poll_interval_s):
            if turn.cancel.is_set():
                self._finish_unrun(session, turn, "cancelled")
                return
        try:
            if turn.cancel.is_set():
                self._finish_unrun(session, turn, "cancelled")
                return
            self._run_turn(session, turn)
        finally:
            self._slots.release()

    def _fail(
        self, session: Session, turn: Turn, code: str, message: str, redactor: Redactor
    ) -> None:
        turn.status = "failed"
        turn.error = {"code": code, "message": redactor.redact(message)[:2000]}
        turn.completed_at = self._clock()
        session.emit("turn.failed", turn.id, turn=turn.to_dict())
        turn.done.set()

    def _run_turn(self, session: Session, turn: Turn) -> None:
        spec = self.store.get(session.agent_name)
        redactor = Redactor(spec.secret_values() if spec else [])
        if spec is None:
            self._fail(
                session,
                turn,
                "resource_not_found",
                f"agent {session.agent_name!r} is no longer registered; define it again",
                redactor,
            )
            return
        extra_mcp = turn.mcp_servers
        if extra_mcp:
            spec = dataclasses.replace(spec, mcp_servers={**spec.mcp_servers, **extra_mcp})
            redactor.add(spec.secret_values())
        adapter = self.adapters.get(spec.runtime)
        if adapter is None:
            self._fail(
                session, turn, "invalid_request", f"unknown runtime {spec.runtime!r}", redactor
            )
            return

        turn.status = "in_progress"
        turn.started_at = self._clock()
        session.emit("turn.started", turn.id, turn=turn.to_dict())

        builder = _TurnBuilder(session, turn, redactor, adapter.name)
        turn_dir = tempfile.mkdtemp(prefix="ebx-agent-turn-")
        os.chmod(turn_dir, 0o700)
        outcome: tuple[str, str, str] = ("failed", "internal_error", "turn did not run")
        try:
            workdir = prepare_workspace(spec, redactor)
            builder.turn_cwd = workdir
            prompt = turn.prompt
            if turn.instructions:
                prompt = f"{turn.instructions.strip()}\n\n---\n\n{prompt}"
            ctx = TurnContext(
                spec=spec,
                prompt=prompt,
                workdir=workdir,
                turn_dir=turn_dir,
                native_session_id=session.native_session_id,
                first_turn=session.native_session_id is None,
            )
            invocation = adapter.build_invocation(ctx)
            for file in invocation.files:
                write_invocation_file(file, workdir)
            env = build_child_env(spec, adapter, invocation.env, self._environ)
            outcome = self._supervise(
                session,
                turn,
                spec,
                adapter,
                invocation.argv,
                env,
                invocation.stdin,
                workdir,
                builder,
                redactor,
                adapter.new_parser(ctx),
            )
        except RuntimeFailure as failure:
            outcome = ("failed", failure.code, failure.message)
        except Exception as exc:
            _log.exception("turn %s crashed", turn.id)
            outcome = ("failed", "internal_error", f"{type(exc).__name__}: {exc}")
        finally:
            shutil.rmtree(turn_dir, ignore_errors=True)

        status, code, message = outcome
        builder.finalize(aborted=status != "completed")
        turn.status = status
        if status == "completed" and builder.turn_cwd:
            for hook in list(self.turn_hooks):
                try:
                    hook(session, turn, builder.turn_cwd, list(builder.reported_paths))
                except Exception:
                    _log.exception("turn hook failed for %s", turn.id)
        turn.completed_at = self._clock()
        if status == "failed":
            turn.error = {"code": code, "message": redactor.redact(message)[:2000]}
        session.emit(f"turn.{status}", turn.id, turn=turn.to_dict(with_items=False))
        turn.done.set()
        self._save_state()

    def _supervise(
        self,
        session: Session,
        turn: Turn,
        spec: AgentSpec,
        adapter: AgentAdapter,
        argv: list[str],
        env: dict[str, str],
        stdin: bytes | None,
        workdir: str,
        builder: _TurnBuilder,
        redactor: Redactor,
        parser: EventParser,
    ) -> tuple[str, str, str]:
        limits = spec.limits
        try:
            proc = subprocess.Popen(  # noqa: S603
                argv,
                cwd=workdir,
                env=env,
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError:
            binary = argv[0]
            hint = (
                f"{binary!r} was not found on PATH; install it with "
                f"`python -m easy_sandbox.server.agents install {adapter.name}`"
            )
            raise RuntimeFailure("runtime_not_installed", hint) from None
        except OSError as exc:
            raise RuntimeFailure("sandbox_error", f"cannot start {argv[0]!r}: {exc}") from exc

        prlimit = getattr(resource, "prlimit", None) if resource is not None else None
        if limits.cpu_seconds and prlimit is not None and resource is not None:
            try:
                prlimit(proc.pid, resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds + 5))
            except (OSError, ValueError):
                pass

        q: queue.Queue[tuple[str, bytes | None]] = queue.Queue()
        stderr_tail = bytearray()
        stderr_lock = threading.Lock()

        def _write_stdin() -> None:
            assert proc.stdin is not None and stdin is not None
            try:
                proc.stdin.write(stdin)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        def _read_stdout() -> None:
            assert proc.stdout is not None
            try:
                for raw in iter(lambda: proc.stdout.readline(_MAX_LINE), b""):  # type: ignore[union-attr]
                    q.put(("out", raw))
            except (ValueError, OSError):
                pass
            q.put(("eof", None))

        def _read_stderr() -> None:
            assert proc.stderr is not None
            try:
                for raw in iter(lambda: proc.stderr.read1(4096), b""):  # type: ignore[union-attr]
                    with stderr_lock:
                        stderr_tail.extend(raw)
                        if len(stderr_tail) > _STDERR_KEEP:
                            del stderr_tail[: len(stderr_tail) - _STDERR_KEEP]
                    q.put(("err", None))
            except (ValueError, OSError):
                pass

        threads = [
            threading.Thread(target=_read_stdout, daemon=True),
            threading.Thread(target=_read_stderr, daemon=True),
        ]
        if stdin is not None:
            threads.append(threading.Thread(target=_write_stdin, daemon=True))
        for t in threads:
            t.start()

        started = time.monotonic()
        last_activity = started
        total_bytes = 0
        eof = False
        failure: tuple[str, str] | None = None
        cancelled = False
        partial = b""

        def _feed(line_bytes: bytes) -> None:
            text = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
            try:
                for pe in parser.feed(text):
                    builder.handle(pe)
            except Exception as exc:
                raise RuntimeFailure(
                    "internal_error", f"cannot parse agent output: {type(exc).__name__}"
                ) from exc

        try:
            while True:
                try:
                    kind, data = q.get(timeout=self.poll_interval_s)
                except queue.Empty:
                    kind, data = "", None
                now = time.monotonic()
                if kind == "out" and data is not None:
                    last_activity = now
                    total_bytes += len(data)
                    if total_bytes > limits.max_output_bytes:
                        failure = (
                            "output_limit_exceeded",
                            f"agent output exceeded {limits.max_output_bytes} bytes",
                        )
                    else:
                        if data.endswith(b"\n"):
                            _feed(partial + data)
                            partial = b""
                        else:
                            partial += data
                            if len(partial) >= _MAX_LINE:
                                _feed(partial)
                                partial = b""
                elif kind == "err":
                    last_activity = now
                elif kind == "eof":
                    eof = True
                if failure is None:
                    if turn.cancel.is_set():
                        cancelled = True
                    elif now - started > limits.turn_timeout_s:
                        failure = ("request_timeout", f"turn exceeded {limits.turn_timeout_s:g}s")
                    elif now - last_activity > limits.idle_timeout_s:
                        failure = ("request_timeout", f"no output for {limits.idle_timeout_s:g}s")
                if cancelled or failure is not None:
                    self._terminate(proc)
                    break
                if eof and proc.poll() is not None:
                    break
                if eof and q.empty():
                    time.sleep(self.poll_interval_s)
        except RuntimeFailure as exc:
            self._terminate(proc)
            failure = (exc.code, exc.message)
        finally:
            for t in threads:
                t.join(timeout=2)
            try:
                rc = proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._terminate(proc)
                rc = proc.poll()
            for stream in (proc.stdout, proc.stderr):
                try:
                    if stream:
                        stream.close()
                except OSError:
                    pass

        if partial and failure is None and not cancelled:
            try:
                _feed(partial)
            except RuntimeFailure as exc:
                failure = (exc.code, exc.message)
        try:
            while True:
                kind, data = q.get_nowait()
                if kind == "out" and data and failure is None and not cancelled:
                    _feed(data)
        except queue.Empty:
            pass
        except RuntimeFailure as exc:
            failure = failure or (exc.code, exc.message)
        try:
            for pe in parser.finish(rc):
                builder.handle(pe)
        except Exception:
            _log.debug("parser.finish failed", exc_info=True)

        with stderr_lock:
            stderr_text = redactor.redact(stderr_tail.decode("utf-8", errors="replace"))
        if cancelled:
            return ("cancelled", "cancelled", "turn cancelled")
        if failure is not None:
            return ("failed", failure[0], failure[1])
        if builder.fatal is not None:
            return ("failed", builder.fatal[0], builder.fatal[1])
        if rc != 0:
            code, message = adapter.classify_failure(rc, stderr_text)
            return ("failed", code, message)
        if builder.result_ok is False:
            return ("failed", "internal_error", builder.result_text or "agent reported an error")
        return ("completed", "", "")

    def _terminate(self, proc: subprocess.Popen[bytes]) -> None:
        def _sig(sig: int) -> None:
            try:
                os.killpg(proc.pid, sig)
            except (ProcessLookupError, PermissionError):
                pass
            except OSError:
                try:
                    proc.send_signal(sig)
                except OSError:
                    pass

        def _wait(seconds: float) -> bool:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    return True
                time.sleep(0.01)
            return proc.poll() is not None

        if proc.poll() is not None:
            return
        _sig(signal.SIGINT)
        if _wait(self.kill_grace_s):
            return
        _sig(signal.SIGTERM)
        if _wait(self.term_grace_s):
            return
        _sig(signal.SIGKILL)
        _wait(2.0)

    # ------------------------------------------------------------------ #
    # Health / install
    # ------------------------------------------------------------------ #

    def runtime_info(self, name: str, *, refresh: bool = False) -> dict[str, Any]:
        """Installation/health summary of one adapter (cached for 30 s)."""
        adapter = self.adapters.get(name)
        if adapter is None:
            raise AgentNotFoundError(f"unknown runtime {name!r}", param="runtime")
        now = time.monotonic()
        cached = self._health_cache.get(adapter.name)
        if cached and not refresh and now - cached[0] < 30:
            return cached[1]
        path = (
            shutil.which(adapter.binary, path=base_child_env(self._environ).get("PATH"))
            if adapter.binary
            else None
        )
        version: str | None = None
        installed = bool(path) or not adapter.binary
        if path:
            try:
                proc = subprocess.run(  # noqa: S603
                    adapter.health_argv(),
                    env=base_child_env(self._environ),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                version = (
                    (proc.stdout or proc.stderr).strip().splitlines()[0][:200]
                    if (proc.stdout or proc.stderr).strip()
                    else None
                )
            except (OSError, subprocess.TimeoutExpired):
                version = None
        info = {
            "name": adapter.name,
            "aliases": list(adapter.aliases),
            "binary": adapter.binary or None,
            "installed": installed,
            "path": path,
            "version": version,
            "experimental": adapter.capabilities.experimental,
            "capabilities": dataclasses.asdict(adapter.capabilities),
            "auth_env_present": any(
                n in self._environ
                for n in (*adapter.credential_env_names, *adapter.passthrough_env)
            ),
            "install_steps": [list(s) for s in adapter.install_steps],
        }
        self._health_cache[adapter.name] = (now, info)
        return info

    def list_runtimes(self) -> list[dict[str, Any]]:
        """Info for every registered adapter."""
        return [self.runtime_info(n) for n in self.adapters.names()]

    def install(self, name: str, *, timeout: float = 600.0) -> dict[str, Any]:
        """Run the adapter's install steps (requires ``EBX_AGENTS_ALLOW_INSTALL=1``)."""
        if not self.allow_install:
            raise AgentRuntimeError(
                "runtime installation is disabled (set EBX_AGENTS_ALLOW_INSTALL=1)"
            )
        adapter = self.adapters.get(name)
        if adapter is None:
            raise AgentNotFoundError(f"unknown runtime {name!r}", param="runtime")
        if not adapter.install_steps:
            return {"name": adapter.name, "ok": True, "log": "nothing to install"}
        log: list[str] = []
        ok = True
        env = base_child_env(self._environ)
        for step in adapter.install_steps:
            try:
                proc = subprocess.run(  # noqa: S603
                    list(step),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                log.append(
                    f"$ {' '.join(step)}\n{(proc.stdout or '')[-2000:]}{(proc.stderr or '')[-2000:]}"
                )
                if proc.returncode != 0:
                    ok = False
                    break
            except (OSError, subprocess.TimeoutExpired) as exc:
                log.append(f"$ {' '.join(step)}\n{exc}")
                ok = False
                break
        self._health_cache.pop(adapter.name, None)
        return {"name": adapter.name, "ok": ok, "log": Redactor().redact("\n".join(log))[-6000:]}

    def doctor(self, name: str) -> dict[str, Any]:
        """Check an agent definition (or bare runtime name) without calling the model."""
        checks: list[dict[str, Any]] = []
        spec = self.store.get(name)
        runtime = spec.runtime if spec else name
        adapter = self.adapters.get(runtime)
        if adapter is None:
            return {
                "name": name,
                "ok": False,
                "checks": [
                    {"name": "runtime", "ok": False, "detail": f"unknown runtime {runtime!r}"}
                ],
            }
        info = self.runtime_info(adapter.name, refresh=True)
        checks.append(
            {
                "name": "installed",
                "ok": bool(info["installed"]),
                "detail": info["path"] or "not found on PATH",
            }
        )
        if info["version"]:
            checks.append({"name": "version", "ok": True, "detail": info["version"]})
        if spec is not None:
            problems = adapter.validate(spec)
            checks.append(
                {"name": "config", "ok": not problems, "detail": "; ".join(problems) or "valid"}
            )
            has_cred = (
                bool(spec.provider.api_key) or info["auth_env_present"] or adapter.name == "command"
            )
            checks.append(
                {
                    "name": "credentials",
                    "ok": has_cred,
                    "detail": "configured"
                    if has_cred
                    else f"set provider.api_key or one of {', '.join(adapter.credential_env_names)}",
                }
            )
            wd = spec.workspace.path
            checks.append(
                {
                    "name": "workspace",
                    "ok": os.path.isdir(wd)
                    or bool(spec.workspace.git)
                    or os.access(os.path.dirname(wd) or "/", os.W_OK),
                    "detail": wd,
                }
            )
        return {"name": name, "ok": all(c["ok"] for c in checks), "checks": checks}

    def health(self) -> dict[str, Any]:
        """Server-level summary without secrets."""
        with self._lock:
            sessions = list(self._sessions.values())
        return {
            "status": "ok",
            "agents": [s.name for s in self.store.list()],
            "sessions": len(sessions),
            "active_turns": sum(1 for s in sessions if s.active is not None),
            "persistent": self._state_path is not None,
            "locked_definitions": self.lock_definitions,
            "install_allowed": self.allow_install,
            "full_access_agents": [
                s.name for s in self.store.list() if s.permissions == "full_access"
            ],
        }

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _save_state(self) -> None:
        if not self._state_path:
            return
        with self._lock:
            payload = {
                "version": 1,
                "sessions": [s.to_dict(with_turns=True) for s in self._sessions.values()],
            }
        try:
            os.makedirs(os.path.dirname(self._state_path), mode=0o700, exist_ok=True)
            tmp = f"{self._state_path}.{os.getpid()}.tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, self._state_path)
        except OSError:
            _log.debug("could not persist agent state", exc_info=True)

    def _load_state(self) -> None:
        assert self._state_path is not None
        try:
            with open(self._state_path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            return
        for raw in payload.get("sessions", []):
            try:
                session = Session(
                    raw["id"],
                    raw["agent"],
                    float(raw["created_at"]),
                    raw.get("metadata"),
                    event_buffer=self.event_buffer,
                )
                session.last_active_at = float(raw.get("last_active_at") or session.created_at)
                session.native_session_id = raw.get("native_session_id")
                for traw in raw.get("turns", []):
                    turn = Turn.from_dict(traw)
                    if turn.status not in TERMINAL_TURN_STATUSES:
                        turn.status = "failed"
                        turn.error = {
                            "code": "internal_error",
                            "message": "server restarted while the turn was running",
                        }
                        turn.done.set()
                    session.turns.append(turn)
                    self._turn_index[turn.id] = session.id
                self._sessions[session.id] = session
            except (KeyError, ValueError, TypeError):
                continue
