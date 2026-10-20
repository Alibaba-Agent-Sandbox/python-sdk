"""Small HTTP entrypoints for standalone or FC custom-container applications."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from .invocations import verify_invocation
from .models import TERMINAL, ApplicationError, Principal, canonical, public_run

if TYPE_CHECKING:
    from .runtime import ApplicationRuntime


def make_server(
    runtime: ApplicationRuntime,
    *,
    mode: str = "gateway",
    host: str = "127.0.0.1",
    port: int = 9000,
    internal_token: str = "",
) -> ThreadingHTTPServer:
    """Build a gateway or private /invoke listener; callers control TLS/ingress.

    Worker/dispatcher listeners are private control-plane services, not business
    APIs. FC custom containers receive InvokeFunction payloads at POST /invoke.
    There is no work scheduled after the invocation response is returned.
    """
    if mode not in {"gateway", "worker", "dispatcher"}:
        raise ValueError("Invalid application server mode")
    if mode != "gateway" and len(internal_token) < 32:
        raise ValueError("Private invocation token must contain at least 32 characters")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            # Default request logging can leak paths/headers from untrusted input.
            return

        def _send(self, status: int, value: Any, content_type: str = "application/json") -> None:
            payload = value if isinstance(value, bytes) else canonical(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def _principal(self) -> Principal:
            raw = self.headers.get("Authorization", "")
            principal = runtime.authenticate(raw[7:]) if raw.startswith("Bearer ") else None
            if principal is None:
                raise ApplicationError(401, "unauthenticated", "A valid bearer token is required")
            return principal

        def _body(self) -> dict[str, Any]:
            if self.headers.get("Transfer-Encoding"):
                raise ApplicationError(400, "invalid_request", "Chunked requests are unsupported")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ApplicationError(400, "invalid_request", "Invalid body length") from exc
            if length < 1 or length > 262144:
                raise ApplicationError(400, "invalid_request", "Request body exceeds size limit")
            try:
                value = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeError) as exc:
                raise ApplicationError(400, "invalid_request", "Expected a JSON object") from exc
            if not isinstance(value, dict):
                raise ApplicationError(400, "invalid_request", "Expected a JSON object")
            return value

        def _owned(self, principal: Principal, run_id: str) -> dict[str, Any]:
            row = runtime.store.get(run_id, principal.owner)
            if row["revision"] not in principal.revisions:
                raise ApplicationError(404, "not_found", "Run was not found")
            return row

        def _events(self, principal: Principal, run_id: str) -> None:
            raw = self.headers.get("Last-Event-ID", "0")
            if not raw.isascii() or not raw.isdecimal() or len(raw) > 12:
                raise ApplicationError(400, "invalid_cursor", "Invalid event cursor")
            cursor = int(raw)
            pending = runtime.store.events(run_id, principal.owner, cursor)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            self.end_headers()
            end = time.monotonic() + 20
            self.close_connection = True
            while True:
                for event in pending:
                    frame = (
                        f"id: {event['seq']}\nevent: {event['type']}\ndata: {canonical(event)}\n\n"
                    )
                    self.wfile.write(frame.encode())
                    cursor = event["seq"]
                self.wfile.flush()
                try:
                    refreshed = self._principal()
                    refreshed.require("runs:read")
                    row = self._owned(refreshed, run_id)
                except ApplicationError:
                    # Headers are already committed; revoke by ending the stream.
                    return
                if (row["status"] in TERMINAL and cursor >= row["seq"]) or time.monotonic() >= end:
                    return
                time.sleep(0.2)
                pending = runtime.store.events(run_id, principal.owner, cursor)
                if not pending:
                    self.wfile.write(b": heartbeat\n\n")

        def _handle(self, method: str) -> None:
            # Closing each request bounds malformed-body/pipeline ambiguity.
            self.close_connection = True
            path = urlsplit(self.path).path
            if method == "GET" and path in {"/health", "/healthz"}:
                revision = os.getenv("ABX_APP_REVISION", next(iter(runtime.applications), ""))
                self._send(
                    200,
                    {
                        "status": "ok",
                        "mode": mode,
                        "revision": revision,
                        "protocol": "agent-sandbox-runs/v1",
                        "operations": (
                            ["create", "get", "cancel", "events", "result", "artifact"]
                            if mode == "gateway"
                            else ["invoke"]
                        ),
                    },
                )
                return
            if mode != "gateway":
                if method != "POST" or path != "/invoke":
                    raise ApplicationError(404, "not_found", "Endpoint was not found")
                supplied = self.headers.get("X-ABX-Internal-Token", "")
                body = self._body()
                if not supplied.isascii() or not hmac.compare_digest(supplied, internal_token):
                    body = verify_invocation(body, internal_token, role=mode)
                if mode == "worker":
                    run_id = body.get("runId")
                    if set(body) != {"runId"} or not isinstance(run_id, str) or len(run_id) > 128:
                        raise ApplicationError(400, "invalid_request", "Expected a run ID")
                    claimed = asyncio.run(runtime.work(run_id))
                    self._send(200, {"claimed": claimed})
                else:
                    if set(body) - {"limit"} or not isinstance(body.get("limit", 20), int):
                        raise ApplicationError(400, "invalid_request", "Invalid dispatch request")
                    self._send(200, {"dispatched": runtime.dispatch(limit=body.get("limit", 20))})
                return
            principal = self._principal()
            principal.require("runs:write" if method == "POST" else "runs:read")
            if path == "/v1/agent-runs" and method == "POST":
                self._send(
                    202,
                    public_run(
                        runtime.create(
                            principal,
                            self.headers.get("Idempotency-Key", ""),
                            self._body(),
                        )
                    ),
                )
                return
            parts = path.strip("/").split("/")
            if len(parts) < 3 or parts[:2] != ["v1", "agent-runs"]:
                raise ApplicationError(404, "not_found", "Endpoint was not found")
            run_id = parts[2]
            row = self._owned(principal, run_id)
            tail = parts[3:]
            if not tail and method == "GET":
                self._send(200, public_run(row))
            elif tail == ["cancel"] and method == "POST":
                self._send(202, public_run(runtime.store.cancel(run_id, principal.owner)))
            elif tail == ["events"] and method == "GET":
                self._events(principal, run_id)
            elif tail == ["result"] and method == "GET":
                self._send(200, runtime.store.result(run_id, principal.owner))
            elif (
                len(tail) == 3
                and tail[0] == "artifacts"
                and tail[2] == "content"
                and method == "GET"
            ):
                content, _ = runtime.store.artifact(run_id, principal.owner, tail[1])
                # Untrusted model output is always a download, never executable HTML.
                self._send(200, content, "application/octet-stream")
            else:
                raise ApplicationError(404, "not_found", "Endpoint was not found")

        def _safe(self, method: str) -> None:
            self.connection.settimeout(35)
            try:
                self._handle(method)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                return
            except Exception as exc:
                if isinstance(exc, ApplicationError):
                    status, code, message = exc.status, exc.code, exc.message
                else:
                    status, code, message = 503, "unavailable", "Application service is unavailable"
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    self._send(
                        status,
                        {
                            "error": {
                                "code": code,
                                "message": message,
                                "requestId": uuid.uuid4().hex,
                            }
                        },
                    )

        def do_GET(self) -> None:
            self._safe("GET")

        def do_POST(self) -> None:
            self._safe("POST")

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server
