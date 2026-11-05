"""Private, restart-aware bridge for one Gateway-owned Sandbox Session.

This listener is separate from the public local Agents API. It reuses the real
CLI runtime, but never exposes arbitrary shell/files/provider administration.
The journal handles cooperative runtime failures, not hostile same-UID code.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import hmac
import json
import math
import os
import secrets
import shutil
import sqlite3
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .agents.config import AgentSpec, LimitsSpec, ProviderSpec, WorkspaceSpec
from .agents.runtime import AgentRuntime
from .agents.wire_sessions import SessionsEventMapper, item_object, turn_object
from .managed_process import ProcessDomain

PROTOCOL = "agent-sandbox-managed-bridge/v1"
_TERMINAL = frozenset({"completed", "failed", "cancelled", "uncertain"})


class BridgeError(Exception):
    """A private protocol error with no arbitrary exception disclosure."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status, self.code = status, code


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ManagedBridge:
    """Own one local Agent Session and durable accepted-submission identities."""

    def __init__(
        self,
        state_dir: str,
        workspace: str,
        *,
        runtime: AgentRuntime | None = None,
        max_file_bytes: int = 10485760,
        max_output_bytes: int = 8388608,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.workspace = os.path.abspath(workspace)
        os.makedirs(self.workspace, exist_ok=True)
        self.max_file_bytes, self.max_output_bytes = max_file_bytes, max_output_bytes
        self.epoch = secrets.token_hex(16)
        self.lock = threading.RLock()
        self.domains: dict[str, ProcessDomain] = {}
        self.runtime = runtime or AgentRuntime(
            persist=False, max_sessions=1, max_concurrent_turns=1, event_buffer=20000
        )
        self.path = self.state_dir / "receipts.sqlite3"
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,body TEXT NOT NULL)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY,body TEXT NOT NULL)"
            )
            for rid, raw in db.execute("SELECT id,body FROM receipts").fetchall():
                row = json.loads(raw)
                if row["status"] not in _TERMINAL:
                    row.update(status="uncertain", error={"code": "runtime_restarted"})
                    db.execute("UPDATE receipts SET body=? WHERE id=?", (_json(row), rid))
        os.chmod(self.path, 0o600)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA synchronous=FULL")
        return db

    def _session_record(self) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT body FROM meta WHERE key='session'").fetchone()
            return json.loads(row[0]) if row else None

    def create_session(self, body: dict[str, Any]) -> dict[str, Any]:
        """Persist a stable creation nonce; a second mapping is never silently created."""
        if set(body) != {"nonce", "agent"} or not isinstance(body["nonce"], str):
            raise BridgeError(400, "invalid_session")
        with self.lock:
            saved = self._session_record()
            request_digest = hashlib.sha256(_json(body).encode()).hexdigest()
            if saved:
                if saved["nonce"] != body["nonce"] or saved["digest"] != request_digest:
                    raise BridgeError(409, "session_identity_conflict")
                return {k: saved[k] for k in ("session_id", "epoch")}
            agent = body["agent"]
            if not isinstance(agent, dict) or set(agent) - {"adapter", "model", "instructions"}:
                raise BridgeError(400, "invalid_agent")
            adapter = agent.get("adapter")
            if adapter not in {"codex", "qwen-code"}:
                raise BridgeError(400, "unsupported_adapter")
            spec = AgentSpec(
                name="managed",
                runtime=adapter,
                model=agent.get("model"),
                instructions=agent.get("instructions"),
                workspace=WorkspaceSpec(path=self.workspace),
                provider=ProviderSpec(
                    base_url=os.getenv("OPENAI_BASE_URL"),
                    api_key=os.getenv("OPENAI_API_KEY"),
                    wire_api="responses" if adapter == "codex" else "chat_completions",
                ),
                permissions="full_access",
                limits=LimitsSpec(max_output_bytes=self.max_output_bytes),
            )
            self.runtime.store.put(spec)
            local = self.runtime.create_session(spec.name)
            saved = {
                "nonce": body["nonce"],
                "digest": request_digest,
                "session_id": local.id,
                "epoch": self.epoch,
            }
            with self._db() as db:
                db.execute("INSERT INTO meta(key,body) VALUES('session',?)", (_json(saved),))
            return {k: saved[k] for k in ("session_id", "epoch")}

    def _write_input(self, file: dict[str, Any]) -> None:
        if set(file) != {"path", "sha256", "data_base64"}:
            raise BridgeError(400, "invalid_file")
        path = file["path"]
        prefix = self.workspace.rstrip("/") + "/input/"
        if (
            not isinstance(path, str)
            or not path.startswith(prefix)
            or os.path.normpath(path) != path
            or "\x00" in path
            or "\\" in path
        ):
            raise BridgeError(400, "invalid_file_path")
        try:
            content = base64.b64decode(file["data_base64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise BridgeError(400, "invalid_file_data") from exc
        if (
            len(content) > self.max_file_bytes
            or hashlib.sha256(content).hexdigest() != file["sha256"]
        ):
            raise BridgeError(400, "file_digest_or_size")
        relative = path[len(self.workspace.rstrip("/")) + 1 :].split("/")
        fd = os.open(self.workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in relative[:-1]:
                if not component or component in {".", ".."}:
                    raise BridgeError(400, "invalid_file_path")
                with contextlib.suppress(FileExistsError):
                    os.mkdir(component, mode=0o700, dir_fd=fd)
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            name = relative[-1]
            try:
                target = os.open(
                    name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
                )
            except FileExistsError as exc:
                raise BridgeError(409, "input_path_exists") from exc
            with os.fdopen(target, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise BridgeError(409, "input_path_unavailable") from exc
        finally:
            os.close(fd)

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        """Persist acceptance before starting one real CLI turn, without replay after restart."""
        if set(body) - {
            "submission_id",
            "session_id",
            "input",
            "files",
            "deadline",
            "max_tool_seconds",
            "max_output_bytes",
            "max_events",
        } or not {"submission_id", "session_id", "input", "files", "deadline"} <= set(body):
            raise BridgeError(400, "invalid_submission")
        tool_seconds = body.get("max_tool_seconds", 60)
        if type(tool_seconds) not in {int, float} or not 0 < tool_seconds <= 3600:
            raise BridgeError(400, "invalid_tool_deadline")
        output_bytes, max_events = (
            body.get("max_output_bytes", self.max_output_bytes),
            body.get("max_events", 10000),
        )
        if (
            (not isinstance(output_bytes, int) or isinstance(output_bytes, bool))
            or output_bytes < 1
            or (not isinstance(max_events, int) or isinstance(max_events, bool))
            or max_events < 1
        ):
            raise BridgeError(400, "invalid_output_budget")
        rid = body["submission_id"]
        if (
            not isinstance(rid, str)
            or not re_identifier(rid)
            or not isinstance(body["input"], str)
            or len(body["input"].encode()) > 262144
        ):
            raise BridgeError(400, "invalid_submission")
        if (
            not isinstance(body["files"], list)
            or len(body["files"]) > 50
            or type(body["deadline"]) not in {int, float}
            or not math.isfinite(body["deadline"])
        ):
            raise BridgeError(400, "invalid_submission")
        identity = hashlib.sha256(_json(body).encode()).hexdigest()
        with self.lock:
            with self._db() as db:
                raw = db.execute("SELECT body FROM receipts WHERE id=?", (rid,)).fetchone()
                if raw:
                    row = json.loads(raw[0])
                    if row["digest"] != identity:
                        raise BridgeError(409, "submission_mismatch")
                    return self.get(rid)
            saved = self._session_record()
            if (
                not saved
                or saved["session_id"] != body["session_id"]
                or saved["epoch"] != self.epoch
            ):
                raise BridgeError(409, "runtime_epoch_changed")
            session = self.runtime.get_session(saved["session_id"])
            if session.status != "idle":
                raise BridgeError(409, "session_busy")
            remaining = body["deadline"] - time.time()
            if remaining < 1:
                raise BridgeError(409, "turn_deadline")
            spec = self.runtime.store.require(session.agent_name)
            spec.limits.turn_timeout_s = remaining
            spec.limits.idle_timeout_s = min(300, remaining)
            spec.limits.max_output_bytes = output_bytes
            scope = secrets.token_hex(24)
            spec.env["ABX_MANAGED_TURN_SCOPE"] = scope
            self.domains[rid] = ProcessDomain(scope)
            row = {
                "submission_id": rid,
                "session_id": session.id,
                "epoch": self.epoch,
                "turn_id": "turn_" + rid,
                "digest": identity,
                "status": "accepted",
                "created_at": time.time(),
                "error": None,
            }
            # FULL synchronous journal commit occurs before staging or process launch.
            self._put(row)
            try:
                for file in body["files"]:
                    self._write_input(file)
                self.runtime.submit(
                    session, body["input"], idempotency_key=rid, turn_id=row["turn_id"]
                )
                row["status"] = "running"
                self._put(row)
                threading.Thread(
                    target=self._watch_tools, args=(rid, float(tool_seconds)), daemon=True
                ).start()
            except Exception:
                # Some staging or launch effects may already exist. Never retry the
                # input merely because a request failed between two journal writes.
                row.update(status="uncertain", error={"code": "submission_result_uncertain"})
                self._put(row)
                raise BridgeError(409, "submission_result_uncertain") from None
            return self.get(rid)

    def _watch_tools(self, rid: str, seconds: float) -> None:
        """Enforce wall deadlines from real parser start/done events, independent of polling."""
        with self.lock:
            with self._db() as db:
                raw = db.execute("SELECT body FROM receipts WHERE id=?", (rid,)).fetchone()
            assert raw is not None
            row = json.loads(raw[0])
            session, turn = self.runtime.find_turn(row["turn_id"])
        cursor = 0
        active: dict[str, float] = {}
        while not turn.done.wait(0.02):
            for event in session.events_after(cursor):
                cursor = event.seq
                if event.turn_id != turn.id:
                    continue
                item = event.data.get("item", {})
                if item.get("type") not in {"command_execution", "mcp_call"}:
                    continue
                if event.type == "item.added":
                    active[item["id"]] = time.monotonic()
                elif event.type == "item.done":
                    active.pop(item["id"], None)
            if any(time.monotonic() - start >= seconds for start in active.values()):
                with self.lock:
                    with self._db() as db:
                        raw = db.execute("SELECT body FROM receipts WHERE id=?", (rid,)).fetchone()
                    assert raw is not None
                    row = json.loads(raw[0])
                    row["error"] = {"code": "tool_deadline_exceeded"}
                    self._put(row)
                    self.runtime.cancel_turn(turn)
                return

    def _put(self, row: dict[str, Any]) -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO receipts(id,body) VALUES(?,?) ON CONFLICT(id) DO UPDATE "
                "SET body=excluded.body",
                (row["submission_id"], _json(row)),
            )

    def _output_candidates(self, errors: list[dict[str, str]]) -> Any:
        stack = [(os.path.join(self.workspace, "outputs"), 0)]
        inspected, deadline = 0, time.monotonic() + 5
        while stack:
            directory, depth = stack.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        inspected += 1
                        if inspected > 4096 or time.monotonic() > deadline:
                            errors.append({"path": "outputs", "code": "artifact_scan_limit"})
                            return
                        if entry.is_dir(follow_symlinks=False):
                            if depth >= 8:
                                errors.append(
                                    {
                                        "path": os.path.relpath(entry.path, self.workspace),
                                        "code": "artifact_depth_limit",
                                    }
                                )
                            else:
                                stack.append((entry.path, depth + 1))
                        else:
                            yield entry.path
            except OSError:
                errors.append(
                    {
                        "path": os.path.relpath(directory, self.workspace),
                        "code": "artifact_scan_failed",
                    }
                )

    def _snapshots(self) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        artifacts: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        output = os.path.join(self.workspace, "outputs")
        if not os.path.isdir(output) or os.path.islink(output):
            return artifacts, errors
        total = 0
        for raw in self._output_candidates(errors):
            if len(artifacts) >= 100:
                errors.append({"path": "outputs", "code": "artifact_count_limit"})
                break
            relative = os.path.relpath(raw, self.workspace).replace(os.sep, "/")
            try:
                # Enumeration only supplies candidates. Every ancestor is opened
                # relative to a held workspace fd, without following links.
                parent_fd = os.open(self.workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    components = relative.split("/")
                    for component in components[:-1]:
                        child = os.open(
                            component,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent_fd,
                        )
                        os.close(parent_fd)
                        parent_fd = child
                    descriptor = os.open(
                        components[-1],
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=parent_fd,
                    )
                finally:
                    os.close(parent_fd)
                try:
                    first = os.fstat(descriptor)
                    if not stat.S_ISREG(first.st_mode) or first.st_size > self.max_file_bytes:
                        raise ValueError
                    with os.fdopen(descriptor, "rb", closefd=False) as stream:
                        content = stream.read(self.max_file_bytes + 1)
                    last = os.fstat(descriptor)
                finally:
                    os.close(descriptor)
                if (
                    len(content) > self.max_file_bytes
                    or (first.st_size, first.st_mtime_ns, first.st_ino)
                    != (last.st_size, last.st_mtime_ns, last.st_ino)
                    or total + len(content) > self.max_file_bytes
                ):
                    raise ValueError
                total += len(content)
                artifacts.append(
                    {
                        "path": relative,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "bytes": len(content),
                        "data_base64": base64.b64encode(content).decode(),
                    }
                )
            except (OSError, ValueError):
                errors.append({"path": relative, "code": "artifact_capture_failed"})
        return artifacts, errors

    def get(self, rid: str, after: int = 0) -> dict[str, Any]:
        """Return the stable receipt, current native state and explicitly gapped live events."""
        with self.lock:
            with self._db() as db:
                saved = db.execute("SELECT body FROM receipts WHERE id=?", (rid,)).fetchone()
            if not saved:
                raise BridgeError(404, "submission_not_found")
            row = json.loads(saved[0])
            if row["epoch"] != self.epoch or row["status"] == "uncertain":
                return {**row, "current_epoch": self.epoch, "events": [], "gap": True}
            session, turn = self.runtime.find_turn(row["turn_id"])
            mapper = SessionsEventMapper(session, self.runtime.store.get(session.agent_name))
            events = []
            earliest = session._base
            selected = session.events_after(after)[:256]
            for event in selected:
                for wire in mapper.map(event):
                    # Host assigns public IDs and independently controls terminal
                    # publication only after its result/artifact transaction.
                    events.append({"seq": event.seq, "wire": wire})
            if turn.done.is_set() and row["status"] not in _TERMINAL:
                domain = self.domains.pop(rid, None)
                stopped = domain.quiesce() if domain else False
                artifacts, errors = self._snapshots()
                row.update(
                    status="failed" if row.get("error") else turn.status,
                    turn=turn_object(turn),
                    items=[item_object(i) for i in turn.items],
                    artifacts=artifacts,
                    artifact_errors=errors,
                    completed_at=time.time(),
                    stop_confirmed=stopped,
                )
                self._put(row)
            returned = selected[-1].seq if selected else after
            response = {
                **row,
                "current_epoch": self.epoch,
                "events": events,
                "returned_cursor": returned,
                "latest_cursor": session.last_seq,
                "earliest_cursor": earliest,
                "gap": after + 1 < earliest,
            }
            if returned < session.last_seq:
                response.pop("artifacts", None)
                response.pop("items", None)
            return response

    def cancel(self, rid: str, body: dict[str, Any]) -> dict[str, Any]:
        """Cancel the exact receipt turn, never the next active turn."""
        if set(body) != {"epoch", "session_id"}:
            raise BridgeError(400, "invalid_cancel")
        with self.lock:
            row = self.get(rid)
            if row["epoch"] != body["epoch"] or row["session_id"] != body["session_id"]:
                raise BridgeError(409, "cancel_identity_conflict")
            if row["status"] not in _TERMINAL:
                _, turn = self.runtime.find_turn(row["turn_id"])
                self.runtime.cancel_turn(turn)
            return self.get(rid)


def re_identifier(value: str) -> bool:
    """Accept only opaque protocol IDs, never paths."""
    return 1 <= len(value) <= 128 and all(c.isascii() and (c.isalnum() or c in "_-") for c in value)


def make_bridge_server(
    bridge: ManagedBridge,
    token: str,
    *,
    host: str = "127.0.0.1",
    port: int = 9000,
    read_timeout: float = 10,
    max_connections: int = 16,
) -> ThreadingHTTPServer:
    """Build the bounded private listener; the caller owns TLS/provider ingress."""
    if len(token) < 32:
        raise ValueError("Managed bridge requires an application token of at least 32 characters")

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def __init__(self, *args: Any) -> None:
            self.slots = threading.BoundedSemaphore(max_connections)
            super().__init__(*args)

        def get_request(self) -> Any:
            connection, address = super().get_request()
            connection.settimeout(read_timeout)
            return connection, address

        def process_request(self, request: Any, address: Any) -> None:
            if not self.slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, address)
            except BaseException:
                self.slots.release()
                raise

        def process_request_thread(self, request: Any, address: Any) -> None:
            try:
                super().process_request_thread(request, address)
            finally:
                self.slots.release()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send(self, status: int, body: Any) -> None:
            data = _json(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def _handle(self, method: str) -> None:
            self.close_connection = True
            self.connection.settimeout(read_timeout)
            url = urlsplit(self.path)
            if method == "GET" and url.path in {"/health", "/healthz"}:
                self._send(200, {"status": "ok", "protocol": PROTOCOL, "epoch": bridge.epoch})
                return
            authorization = self.headers.get("Authorization", "")
            scheme, _, bearer = authorization.partition(" ")
            candidates = [self.headers.get("X-Access-Token", "")]
            if scheme.lower() == "bearer":
                candidates.append(bearer)
            if not any(
                supplied
                and supplied.isascii()
                and len(supplied) <= 4096
                and hmac.compare_digest(supplied, token)
                for supplied in candidates
            ):
                raise BridgeError(401, "unauthenticated")
            if method == "GET" and url.path == "/capabilities":
                adapters = [
                    name
                    for name, binary in (("codex", "codex"), ("qwen-code", "qwen"))
                    if shutil.which(binary, path=bridge.runtime._environ.get("PATH"))
                ]
                self._send(
                    200,
                    {
                        "protocol": PROTOCOL,
                        "epoch": bridge.epoch,
                        "adapters": adapters,
                        "streaming": "bounded_native_events_with_gaps",
                        "durable_receipts": True,
                    },
                )
                return
            body: dict[str, Any] = {}
            if method == "POST":
                if self.headers.get("Transfer-Encoding"):
                    raise BridgeError(400, "invalid_body")
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 16000000:
                    raise BridgeError(413, "body_too_large")
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict):
                    raise BridgeError(400, "invalid_body")
                body = value
            if url.path == "/managed/session":
                self._send(
                    201 if method == "POST" else 200,
                    bridge.create_session(body) if method == "POST" else bridge._session_record(),
                )
                return
            if url.path == "/managed/submissions" and method == "POST":
                self._send(201, bridge.submit(body))
                return
            parts = url.path.strip("/").split("/")
            if (
                len(parts) >= 3
                and parts[:2] == ["managed", "submissions"]
                and re_identifier(parts[2])
            ):
                if method == "GET" and len(parts) == 3:
                    query = parse_qs(url.query)
                    after = int(query.get("after", ["0"])[0])
                    if after < 0:
                        raise BridgeError(400, "invalid_cursor")
                    self._send(200, bridge.get(parts[2], after))
                    return
                if method == "POST" and parts[3:] == ["cancel"]:
                    self._send(202, bridge.cancel(parts[2], body))
                    return
            raise BridgeError(404, "endpoint_not_available")

        def _safe(self, method: str) -> None:
            try:
                self._handle(method)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                code = exc.code if isinstance(exc, BridgeError) else "bridge_unavailable"
                status = exc.status if isinstance(exc, BridgeError) else 503
                self._send(status, {"error": {"code": code}})

        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP dispatch name
            self._safe("GET")

        def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP dispatch name
            self._safe("POST")

    return Server((host, port), Handler)


def main() -> None:
    """Run the dedicated bridge explicitly; importing it has no startup side effect."""
    parser = argparse.ArgumentParser(description="Private managed Agent bridge")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()
    directory = os.getenv(
        "ABX_MANAGED_STATE_DIR", os.path.expanduser("~/.agent-sandbox/managed-bridge")
    )
    bridge = ManagedBridge(directory, os.getenv("ABX_MANAGED_WORKSPACE", "/workspace"))
    server = make_bridge_server(
        bridge,
        os.environ.get("ABX_SERVER_TOKEN", ""),
        host="0.0.0.0",  # nosec B104 - private authenticated Sandbox ingress
        port=args.port,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
