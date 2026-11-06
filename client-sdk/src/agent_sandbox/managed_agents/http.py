"""Finite authenticated Gateway/control listeners and durable SSE subscriptions."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import math
import threading
import time
import uuid
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from .dispatch import ManagedDispatcher, verify_invocation
from .models import PROTOCOL, ManagedError, canonical
from .store import new_object

if TYPE_CHECKING:
    from .service import ManagedService


class TokenAuthenticator:
    """Validate owner/scopes from token hashes; a file-backed source supports revocation."""

    def __init__(self, source: Any) -> None:
        self.source = source

    def authenticate(self, token: str, write: bool) -> str:
        """Return an authenticated owner or a bounded public authorization error."""
        document = self.source() if callable(self.source) else self.source
        hashed = hashlib.sha256(token.encode()).hexdigest()
        for row in document.get("tokens", []):
            if hmac.compare_digest(str(row.get("sha256", "")), hashed):
                expiry = row.get("expiresAt")
                if expiry is not None and (
                    type(expiry) not in {int, float}
                    or not math.isfinite(expiry)
                    or expiry <= time.time()
                ):
                    break
                if ("agents:write" if write else "agents:read") not in row.get("scopes", []):
                    raise ManagedError(403, "forbidden", "This operation is not authorized")
                owner = row.get("owner")
                if not isinstance(owner, str) or not owner:
                    break
                return owner
        raise ManagedError(401, "unauthenticated", "A valid business bearer token is required")


def make_server(
    service: ManagedService,
    auth: TokenAuthenticator | None = None,
    *,
    mode: str = "gateway",
    dispatcher: ManagedDispatcher | None = None,
    internal_token: str = "",
    host: str = "127.0.0.1",
    port: int = 9000,
    read_timeout: float = 10,
    max_connections: int = 64,
    write_timeout: float = 1,
    max_frame_bytes: int = 1048576,
) -> ThreadingHTTPServer:
    """Build a Gateway or private invocation listener; imports never start one."""
    if mode not in {"gateway", "worker", "dispatcher"} or (
        mode != "gateway" and (len(internal_token) < 32 or dispatcher is None)
    ):
        raise ValueError("A valid listener mode and private control dependencies are required")

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
                with contextlib.suppress(OSError):
                    request.sendall(
                        b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n"
                    )
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

        def _send(self, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
            payload = (
                body
                if isinstance(body, bytes)
                else b""
                if body is None
                else canonical(body).encode()
            )
            headers = headers or {}
            self.send_response(status)
            self.send_header("Content-Type", headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Request-Id", self.request_id)
            self.send_header(
                "Access-Control-Expose-Headers",
                "Location, X-Request-Id, X-Agent-Sandbox-Submission-Id, "
                "X-Agent-Sandbox-Operation-Id",
            )
            if status == 429:
                self.send_header("Retry-After", "1")
            for key, value in headers.items():
                if key.lower() != "content-type":
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        def _chunk(self, payload: bytes) -> None:
            self.connection.settimeout(write_timeout)
            self.wfile.write(f"{len(payload):X}\r\n".encode("ascii") + payload + b"\r\n")
            self.wfile.flush()

        def _owner(self, write: bool = False) -> str:
            supplied = self.headers.get("Authorization", "")
            if auth is None or not supplied.startswith("Bearer "):
                raise ManagedError(
                    401, "unauthenticated", "A valid business bearer token is required"
                )
            return auth.authenticate(supplied[7:], write)

        def _raw(self) -> bytes:
            if self.headers.get("Transfer-Encoding"):
                raise ManagedError(400, "invalid_body", "Chunked request bodies are not supported")
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ManagedError(400, "invalid_body", "Invalid content length") from exc
            budget = service.config.storage["maxFileBytes"] + 16384
            if not 0 <= size <= budget:
                raise ManagedError(413, "body_too_large", "Request exceeds its byte budget")
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ManagedError(400, "incomplete_body", "Incomplete request body")
            return raw

        def _body(self, *, allow_octet_stream: bool = False) -> dict[str, Any]:
            raw = self._raw()
            if not raw:
                return {}
            content_type = self.headers.get_content_type()
            if content_type != "application/json" and not (
                allow_octet_stream and content_type == "application/octet-stream"
            ):
                raise ManagedError(415, "unsupported_media_type", "Use application/json")
            try:
                value = json.loads(raw)
                canonical(value)
            except (ValueError, TypeError) as exc:
                raise ManagedError(400, "invalid_json", "Expected finite JSON") from exc
            if not isinstance(value, dict):
                raise ManagedError(400, "invalid_json", "Expected a JSON object")
            return value

        def _file(self, owner: str, key: str) -> None:
            content_type = self.headers.get("Content-Type", "")
            if self.headers.get_content_type() != "multipart/form-data" or len(content_type) > 1024:
                raise ManagedError(415, "unsupported_media_type", "Use multipart/form-data")
            raw = self._raw()
            message = BytesParser(policy=default).parsebytes(
                b"Content-Type: "
                + content_type.encode("ascii")
                + b"\r\nMIME-Version: 1.0\r\n\r\n"
                + raw
            )
            if not message.is_multipart():
                raise ManagedError(
                    400, "invalid_multipart", "Expected a multipart file and purpose"
                )
            fields: dict[str, Any] = {}
            filename = ""
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if name not in {"file", "purpose"} or name in fields or part.is_multipart():
                    raise ManagedError(
                        400, "invalid_multipart", "Expected exactly one file and purpose"
                    )
                fields[name] = part.get_payload(decode=True) or b""
                if name == "file":
                    filename = part.get_filename() or ""
            if set(fields) != {"file", "purpose"}:
                raise ManagedError(400, "invalid_multipart", "Expected file and purpose")
            try:
                purpose = fields["purpose"].decode("ascii")
            except UnicodeError as exc:
                raise ManagedError(400, "invalid_purpose", "Invalid file purpose") from exc
            self._send(200, service.upload_file(owner, filename, purpose, fields["file"], key))

        def _events(
            self,
            owner: str,
            sid: str,
            query: dict[str, str],
            *,
            status: int = 200,
            headers: dict[str, str] | None = None,
        ) -> None:
            header, after = self.headers.get("Last-Event-ID"), query.get("after")
            if header and after and header != after:
                raise ManagedError(400, "invalid_cursor", "Conflicting event cursors")
            cursor = header or after
            subscription_id = None
            stream_started = stream_aborted = False
            with service.store.transaction() as tx:
                session = service._session(tx, sid, owner)
                if cursor is None:
                    cursor = f"evt_{sid}_{session.get('_seq', 0)}"
                subscriptions = [
                    r for r in tx.list("subscription", parent=sid) if r["expires_at"] > time.time()
                ]
                if len(subscriptions) >= service.config.limits["maxSubscribersPerSession"]:
                    raise ManagedError(
                        429, "subscriber_limit", "Session subscription budget exhausted"
                    )
                row = new_object("subscription", owner, parent=sid, expires_at=time.time() + 30)
                subscription_id = row["id"]
                tx.put(row)
            try:
                pending = service.events(owner, sid, cursor)

                def admit(event_id: str) -> bool:
                    try:
                        # This database admission is ordered with DELETE in every
                        # Gateway process. A single admitted frame is in flight;
                        # socket I/O never holds the application transaction lock.
                        with service.store.transaction() as tx:
                            service._session(tx, sid, owner)
                            if self._owner() != owner:
                                return False
                            current = tx.get(subscription_id, owner)
                            current["_admitted_event"] = event_id
                            tx.put(current)
                        return True
                    except ManagedError as error:
                        if error.status in {401, 403, 404, 410}:
                            return False
                        raise

                if not admit(cursor):
                    raise ManagedError(404, "resource_not_found", "Session was removed")
                self.send_response(status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("X-Request-Id", self.request_id)
                self.send_header("Connection", "close")
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self._stream_started = stream_started = True
                self.end_headers()
                end = time.monotonic() + 20
                while time.monotonic() < end:
                    try:
                        authorized = self._owner() == owner
                    except ManagedError as error:
                        if error.status not in {401, 403}:
                            raise
                        authorized = False
                    if not authorized:
                        break
                    for event in pending:
                        with service.store.session_gate(sid):
                            if not admit(event["event_id"]):
                                return
                            payload = event
                            if len(canonical(payload).encode()) > max_frame_bytes:
                                payload = {
                                    "event_id": event["event_id"],
                                    "session_id": sid,
                                    "type": "agent.session.events.gap",
                                    "reason": "sse_frame_limit",
                                }
                            frame = (
                                f"id: {event['event_id']}\nevent: {payload['type']}\n"
                                f"data: {canonical(payload)}\n\n"
                            )
                            self._chunk(frame.encode())
                            cursor = event["event_id"]
                    if not pending:
                        self._chunk(b": heartbeat\n\n")
                    time.sleep(0.2)
                    try:
                        pending = service.events(owner, sid, cursor)
                    except ManagedError as error:
                        if error.status in {404, 410}:
                            break
                        raise
            except BaseException:
                stream_aborted = True
                raise
            finally:
                if subscription_id:
                    with service.store.transaction() as tx:
                        tx.execute(
                            "DELETE FROM managed_objects WHERE application=? AND id=?",
                            (tx.application, subscription_id),
                        )
                if stream_started and not stream_aborted:
                    self._chunk(b"")

        def _handle(self, method: str) -> None:
            self.close_connection = True
            self.connection.settimeout(read_timeout)
            self.request_id = uuid.uuid4().hex
            url = urlsplit(self.path)
            if method == "GET" and url.path in {"/health", "/healthz"}:
                with service.store.transaction() as tx:
                    tx.execute("SELECT 1").fetchone()
                self._send(
                    200,
                    {
                        "status": "ok",
                        "protocol": PROTOCOL,
                        "mode": mode,
                        "revision": service.config.revision,
                    },
                )
                return
            if mode != "gateway":
                if method != "POST" or url.path != "/invoke" or dispatcher is None:
                    raise ManagedError(
                        404, "endpoint_not_available", "Only private invocation is available"
                    )
                payload = verify_invocation(
                    self._body(allow_octet_stream=True), internal_token, mode
                )
                if mode == "worker":
                    if set(payload) - {"sessionId", "submissionId"} or not isinstance(
                        payload.get("sessionId"), str
                    ):
                        raise ManagedError(400, "invalid_invocation", "Expected a Session identity")
                    result = {"claimed": asyncio.run(dispatcher.worker.run(payload["sessionId"]))}
                else:
                    result = asyncio.run(dispatcher.invoke(payload))
                self._send(200, result)
                return
            owner = self._owner(method != "GET")
            key = self.headers.get("Idempotency-Key", "")
            if method == "POST" and url.path == "/v1/files":
                self._file(owner, key)
                return
            query_values = parse_qs(url.query, keep_blank_values=True)
            if any(len(v) != 1 for v in query_values.values()):
                raise ManagedError(
                    400, "invalid_query", "Repeated query parameters are not supported"
                )
            query = {k: v[0] for k, v in query_values.items()}
            segments = url.path.strip("/").split("/")
            if (
                method == "GET"
                and len(segments) == 5
                and segments[:3] == ["v1", "agents", "sessions"]
                and segments[4] == "events"
            ):
                self._events(owner, segments[3], query)
                return
            body = self._body() if method in {"POST", "DELETE"} else {}
            status, result, headers = service.handle(owner, method, url.path, body, query, key)
            if method == "POST" and url.path == "/v1/agents/sessions" and body.get("stream"):
                # Creation is committed. Replay its stream; disconnect does not
                # cancel or authorize re-execution of the accepted initial input.
                self._events(owner, result["id"], {"after": "0"}, status=status, headers=headers)
            else:
                self._send(status, result, headers)

        def _safe(self, method: str) -> None:
            self.request_id = uuid.uuid4().hex
            self._stream_started = False
            try:
                self._handle(method)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                return
            except Exception as exc:
                if self._stream_started:
                    self.close_connection = True
                    return
                error = (
                    exc
                    if isinstance(exc, ManagedError)
                    else ManagedError(
                        503, "service_unavailable", "The application service is unavailable"
                    )
                )
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    self._send(error.status, error.body())

        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP dispatch name
            self._safe("GET")

        def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP dispatch name
            self._safe("POST")

        def do_DELETE(self) -> None:  # noqa: N802 - stdlib HTTP dispatch name
            self._safe("DELETE")

    return Server((host, port), Handler)
