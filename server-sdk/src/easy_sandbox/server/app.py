"""Lightweight, stdlib-only HTTP server for running inside sandbox containers.

Uses :class:`http.server.ThreadingHTTPServer` with a custom
:class:`BaseHTTPRequestHandler` subclass that dispatches requests through the
declarative :class:`~easy_sandbox.server.router.RouteTable` populated by
:mod:`easy_sandbox.server.routes`.

Typical usage (from a template's ``commands.py``)::

    from easy_sandbox.server import start
    start(9000)
"""

from __future__ import annotations

import base64
import contextlib
import email.parser
import email.policy
import hashlib
import hmac
import json
import logging
import os
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from . import routes as _routes  # noqa: F401  (import side-effect: registers routes)
from . import routes_agents as _routes_agents  # noqa: F401
from . import routes_browser as _routes_browser  # noqa: F401
from . import routes_devtools as _routes_devtools  # noqa: F401
from . import routes_files as _routes_files  # noqa: F401
from . import routes_process as _routes_process  # noqa: F401
from . import routes_pty as _routes_pty  # noqa: F401
from . import routes_system as _routes_system  # noqa: F401
from .policy import Identity, PolicyDenied, ServerPolicy
from .registry import CommandRegistry, default_registry
from .router import CapabilityGroup, RouteTable, default_table
from .runtime import PolicyEngine, apply_groups
from .types import ServerRequest, ServerResponse, SSEResponse

if TYPE_CHECKING:
    import asyncio
    import threading

__all__ = [
    "SandboxServer",
    "SandboxRequestHandler",
]

# Auth token — read once at import time so tests can monkeypatch the env var
# before importing.
_TOKEN_ENV_VAR = "EBX_SERVER_TOKEN"

# Comma-separated capability groups to enable at start (opt-in groups such as
# ``agents``); the counterpart of ``EBX_SERVER_DISABLED_GROUPS``.
_ENABLED_GROUPS_ENV_VAR = "EBX_SERVER_ENABLED_GROUPS"

# HTTP methods that may carry a JSON request body.
_BODY_METHODS = frozenset({"POST", "PUT", "DELETE"})

# Maximum allowed request body size (10 MB).
MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024

_FILES_CREATE_ROUTE = "agents_files_create"
_RESPONSES_CONNECT_ROUTE = "agents_responses_connect"
_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_WS_MAX_MESSAGE = 10 * 1024 * 1024


def _parse_multipart(content_type: str, raw: bytes) -> dict[str, Any]:
    """Parse ``multipart/form-data`` into the JSON-shaped body ``POST /v1/files`` understands.

    Text parts become ``str`` fields. The part named ``file`` becomes ``bytes`` under ``file``
    and its filename fills ``filename`` unless a ``filename`` field is also sent.
    """
    message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + raw
    )
    if not message.is_multipart():
        raise ValueError("malformed multipart body")
    fields: dict[str, Any] = {}
    uploaded_name: str | None = None
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not isinstance(name, str) or not name:
            raise ValueError("multipart part without a name")
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            raise ValueError(f"multipart part {name!r} has no body")
        if name == "file":
            fields["file"] = payload
            filename = part.get_filename()
            uploaded_name = filename if isinstance(filename, str) and filename else None
        else:
            fields[name] = payload.decode("utf-8")
    if uploaded_name is not None:
        fields.setdefault("filename", uploaded_name)
    return fields


def _ws_frame(opcode: int, payload: bytes) -> bytes:
    """One unmasked server frame (FIN set)."""
    size = len(payload)
    if size < 126:
        head = struct.pack("!BB", 0x80 | opcode, size)
    elif size < 1 << 16:
        head = struct.pack("!BBH", 0x80 | opcode, 126, size)
    else:
        head = struct.pack("!BBQ", 0x80 | opcode, 127, size)
    return head + payload


class SandboxRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler that dispatches through a :class:`RouteTable`.

    Attributes:
        server: Bound :class:`SandboxServer` instance (set automatically by
            :mod:`http.server`).  The handler reads ``auth_token``,
            ``registry`` and ``route_table`` back-references from it.
    """

    # Silence per-request log lines in production; tests can override.
    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr logging."""

    # ------------------------------------------------------------------ #
    # Auth helper
    # ------------------------------------------------------------------ #

    def _check_auth(self, route: Any = None) -> bool:
        """Validate ``X-Access-Token`` if a token is configured.

        Routes of the opt-in ``agents`` group additionally accept
        ``Authorization: Bearer <token>`` (the only credential header the
        official OpenAI clients can send).  Every other route is unchanged.

        Returns:
            ``True`` if the request is authorised; ``False`` if a 401
            response has already been sent.
        """
        token: str | None = getattr(self.server, "auth_token", None)
        if token is None:
            return True  # local mode — no auth required

        request_token = self.headers.get("X-Access-Token")
        if not request_token and route is not None and route.group == CapabilityGroup.AGENTS:
            authorization = self.headers.get("Authorization", "")
            if authorization[:7].lower() == "bearer ":
                request_token = authorization[7:].strip()
        if not request_token or not hmac.compare_digest(request_token, token):
            self._send_json(401, {"error": "unauthorized", "type": "AuthError"})
            return False
        return True

    # ------------------------------------------------------------------ #
    # Response helpers
    # ------------------------------------------------------------------ #

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        """Serialise *body* as JSON and send with appropriate headers."""
        payload = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_response(self, response: ServerResponse) -> None:
        """Send a :class:`ServerResponse` (JSON body + optional headers).

        An HTTP 202 whose body is an empty mapping is written with an empty
        payload. ``POST /v1/agents/sessions/{id}/events`` uses that shape.
        """
        empty = response.status == 202 and response.body == {}
        payload = b"" if empty else json.dumps(response.body, default=str).encode("utf-8")
        self.send_response(response.status)
        if not empty and "Content-Type" not in response.headers:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        # One write so a raw ``recv`` sees the JSON body with the headers. ``end_headers``
        # flushes first, and the handshake test reads once.
        self._headers_buffer.append(b"\r\n")
        if payload:
            self._headers_buffer.append(payload)
        self.flush_headers()

    def send_response(self, code: int, message: str | None = None) -> None:
        """Record the status code (for the audit log) and delegate."""
        self._last_status = code
        super().send_response(code, message)

    def _content_length(self) -> int | None:
        """Parse ``Content-Length`` strictly; send a 400 and return ``None`` when invalid."""
        get_all = getattr(self.headers, "get_all", None)
        values = [str(v).strip() for v in (get_all("Content-Length") if get_all else None) or []]
        if not values:
            return 0
        if len(set(values)) > 1 or not (values[0].isascii() and values[0].isdigit()):
            self._send_json(400, {"error": "Invalid Content-Length header", "type": "ValueError"})
            return None
        return int(values[0])

    def _read_json_body(
        self, limit: int = MAX_REQUEST_BODY_SIZE, route: Any = None
    ) -> dict[str, Any] | None:
        """Read and parse a JSON request body (multipart for ``POST /v1/files``).

        Args:
            limit: Maximum accepted body size in bytes.
            route: The matched route; only ``POST /v1/files`` may send ``multipart/form-data``.

        Returns:
            Parsed dict, or ``None`` if parsing fails (a 400 response will
            have been sent).  A 413 response is sent when the body exceeds *limit*.
        """
        content_length = self._content_length()
        if content_length is None:
            return None
        if content_length == 0:
            return {}
        if content_length > limit:
            self._send_json(
                413,
                {
                    "error": f"Request body too large ({content_length} bytes); limit is {limit}",
                    "type": "ValueError",
                    "code": "payload_too_large",
                    "limit": limit,
                },
            )
            return None
        content_type = self.headers.get("Content-Type", "")
        multipart = (
            route is not None
            and route.name == _FILES_CREATE_ROUTE
            and content_type.lower().lstrip().startswith("multipart/form-data")
        )
        try:
            raw = self.rfile.read(content_length)
            if multipart:
                return _parse_multipart(content_type, raw)
            return json.loads(raw)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, ValueError) as exc:
            what = "multipart body" if multipart else "JSON"
            self._send_json(400, {"error": f"Invalid {what}: {exc}", "type": "ValueError"})
            return None

    # ------------------------------------------------------------------ #
    # Unified dispatcher
    # ------------------------------------------------------------------ #

    def _route_table(self) -> RouteTable:
        """Return the bound route table, falling back to the default one."""
        table = getattr(self.server, "route_table", None)
        return table if table is not None else default_table()

    def _dispatch(self, method: str) -> None:
        """Match *method* + path against the route table and invoke the handler."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        table = self._route_table()

        route, path_params = table.match(method, path)
        if route is None:
            from .core.http import serve_ops

            if serve_ops(self, method, path, parsed.query):
                return
            self._send_json(404, {"error": f"Not found: {path}", "type": "ValueError"})
            return

        engine: PolicyEngine | None = getattr(self.server, "policy_engine", None)
        if engine is not None:
            self._dispatch_policy(engine, table, route, path, parsed.query, path_params or {})
            return

        # Auth is enforced unless the route opts out (e.g. /health).
        if route.auth_required and not self._check_auth(route):
            return

        # Capability-group gate: a disabled group makes the route unavailable.
        if not table.is_group_enabled(route.group):
            self._send_json(
                404,
                {
                    "error": f"Built-in route {route.name!r} is disabled",
                    "type": "ValueError",
                },
            )
            return

        # Read the JSON body for methods that carry one.
        body: dict[str, Any] | None = None
        if method in _BODY_METHODS:
            body = self._read_json_body(route=route)
            if body is None:
                return  # 400 already sent

        request = ServerRequest(
            method=method,
            path=path,
            query=parse_qs(parsed.query),
            headers=dict(self.headers),
            body=body,
            path_params=path_params or {},
            context={
                "registry": getattr(self.server, "registry", None),
                "route_table": table,
            },
        )
        self._invoke(route, request)

    def _invoke(
        self,
        route: Any,
        request: ServerRequest,
        release: Any = None,
    ) -> None:
        """Run *route*'s handler and send the result; *release* runs when done."""
        try:
            if route.name == _RESPONSES_CONNECT_ROUTE and self._is_websocket_upgrade():
                self._serve_responses_socket(request)
                return
            if route.streaming:
                self._dispatch_streaming(route, request)
                return
            try:
                response = route.handler(request)
            except PolicyDenied as exc:
                exc.endpoint = exc.endpoint or route.name
                self._send_denied(exc)
                return
            except Exception as exc:
                logging.getLogger(__name__).exception(
                    "Unhandled exception in handler %s: %s",
                    route.name,
                    exc,
                )
                self._send_json(
                    500,
                    {"error": str(exc), "type": type(exc).__name__},
                )
                return
            self._send_response(response)
        finally:
            if release is not None:
                release()

    # ------------------------------------------------------------------ #
    # WebSocket (GET /v1/responses)
    # ------------------------------------------------------------------ #

    def _is_websocket_upgrade(self) -> bool:
        return "websocket" in self.headers.get("Upgrade", "").lower()

    def _ws_read_frame(self) -> tuple[int, bool, bytes]:
        """Read one client frame: ``(opcode, fin, payload)``; ``ConnectionError`` on bad frames."""
        head = self.rfile.read(2)
        if len(head) < 2:
            raise ConnectionError("closed")
        fin, opcode = bool(head[0] & 0x80), head[0] & 0x0F
        masked, size = bool(head[1] & 0x80), head[1] & 0x7F
        if head[0] & 0x70 or not masked:
            raise ConnectionError("protocol error")
        if size == 126:
            size = struct.unpack("!H", self.rfile.read(2))[0]
        elif size == 127:
            size = struct.unpack("!Q", self.rfile.read(8))[0]
        if size > _WS_MAX_MESSAGE:
            raise ConnectionError("message too big")
        mask = self.rfile.read(4)
        data = bytearray(self.rfile.read(size))
        if len(mask) < 4 or len(data) < size:
            raise ConnectionError("closed")
        for i in range(size):
            data[i] ^= mask[i % 4]
        return opcode, fin, bytes(data)

    def _ws_send(self, opcode: int, payload: bytes) -> None:
        self.wfile.write(_ws_frame(opcode, payload))
        self.wfile.flush()

    def _ws_close(self, code: int, reason: str = "") -> None:
        with contextlib.suppress(OSError):
            self._ws_send(0x8, struct.pack("!H", code) + reason.encode("utf-8")[:120])

    def _serve_responses_socket(self, request: ServerRequest) -> None:
        """Upgrade ``GET /v1/responses`` and run the responses socket engine on the socket.

        Auth and admission already ran in the dispatcher, so an unauthenticated peer never
        reaches the engine. ``response.create`` and ``response.steer`` frames are JSON text.
        """
        from .agents.api_common import err, from_agent_exc
        from .agents.api_responses import ResponsesSocket
        from .agents.errors import AgentRuntimeError

        key = self.headers.get("Sec-WebSocket-Key", "").strip()
        if (
            "upgrade" not in self.headers.get("Connection", "").lower()
            or self.headers.get("Sec-WebSocket-Version", "").strip() != "13"
            or not key
        ):
            self._send_response(
                err(
                    400,
                    "invalid WebSocket handshake: Connection: Upgrade, Sec-WebSocket-Key and "
                    "Sec-WebSocket-Version: 13 are required",
                    code="agents.websocket_handshake_invalid",
                )
            )
            return
        accept = base64.b64encode(hashlib.sha1(key.encode("ascii", "ignore") + _WS_GUID).digest())
        self.protocol_version = "HTTP/1.1"
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept.decode("ascii"))
        self.send_header("X-Easy-Sandbox-Local", "1")
        self.end_headers()
        self.wfile.flush()
        self.close_connection = True

        engine = ResponsesSocket(request)
        message = bytearray()
        text_message = False
        try:
            while True:
                opcode, fin, payload = self._ws_read_frame()
                if opcode == 0x8:
                    self._ws_close(1000)
                    return
                if opcode == 0x9:
                    self._ws_send(0xA, payload)
                    continue
                if opcode == 0xA:
                    continue
                if opcode in (0x1, 0x2):
                    message = bytearray(payload)
                    text_message = opcode == 0x1
                elif opcode == 0x0:
                    message += payload
                else:
                    self._ws_close(1002, "unknown opcode")
                    return
                if len(message) > _WS_MAX_MESSAGE:
                    self._ws_close(1009, "message too big")
                    return
                if not fin:
                    continue
                if not text_message:
                    self._ws_close(1003, "text frames only")
                    return
                try:
                    frame = json.loads(bytes(message).decode("utf-8"))
                    if not isinstance(frame, dict):
                        raise ValueError("a client event is a JSON object")
                    events = engine.handle(frame)
                except AgentRuntimeError as exc:
                    events = [{"type": "error", "error": from_agent_exc(exc).body["error"]}]
                except ValueError as exc:
                    events = [
                        {"type": "error", "error": {"message": str(exc), "code": "bad_frame"}}
                    ]
                except Exception as exc:
                    logging.getLogger(__name__).exception("responses socket: %s", exc)
                    events = [
                        {"type": "error", "error": {"message": str(exc), "code": "server_error"}}
                    ]
                for event in events:
                    self._ws_send(0x1, json.dumps(event, default=str).encode("utf-8"))
                message = bytearray()
        except (ConnectionError, OSError):
            self._ws_close(1002)

    def _send_denied(self, exc: PolicyDenied) -> None:
        """Send the JSON body for a :class:`PolicyDenied` (adds ``Retry-After`` on 429)."""
        payload = json.dumps(exc.to_body(), default=str).encode("utf-8")
        self.send_response(exc.status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        retry_after = exc.extra.get("retry_after")
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _dispatch_policy(
        self,
        engine: PolicyEngine,
        table: RouteTable,
        route: Any,
        path: str,
        raw_query: str,
        path_params: dict[str, str],
    ) -> None:
        """Policy pipeline: authenticate, gate, admit, bound the body, run, audit."""
        method = self.command
        self._last_status = 0
        identity: Identity | None = None
        ctx = None
        release = None
        code = ""
        try:
            if route.auth_required:
                try:
                    identity = engine.authenticate(self.headers)
                except PolicyDenied as exc:
                    code = exc.code
                    self._send_denied(exc)
                    return
                if identity is None:
                    code = "unauthorized"
                    self._send_json(
                        401, {"error": "unauthorized", "type": "AuthError", "code": "unauthorized"}
                    )
                    return
            else:
                identity = Identity("anonymous", frozenset())

            if not table.is_group_enabled(route.group):
                code = "endpoint_disabled"
                self._send_json(
                    404,
                    {
                        "error": f"Built-in route {route.name!r} is disabled",
                        "type": "ValueError",
                        "code": "endpoint_disabled",
                    },
                )
                return

            try:
                ctx, release = engine.admit(route, identity)
            except PolicyDenied as exc:
                exc.endpoint = exc.endpoint or route.name
                code = exc.code
                self._send_denied(exc)
                return

            query = parse_qs(raw_query)
            if any(len(values) > 1 for values in query.values()):
                code = "duplicate_parameter"
                self._send_denied(
                    PolicyDenied(
                        "duplicate_parameter",
                        "Repeated query parameters are not allowed",
                        status=400,
                        endpoint=route.name,
                        error_type="ValueError",
                    )
                )
                return

            body: dict[str, Any] | None = None
            if method in _BODY_METHODS:
                if self.headers.get("Transfer-Encoding"):
                    code = "unsupported_encoding"
                    self._send_denied(
                        PolicyDenied(
                            "unsupported_encoding",
                            "Transfer-Encoding is not supported; send Content-Length",
                            status=400,
                            endpoint=route.name,
                            error_type="ValueError",
                        )
                    )
                    return
                limit = int(ctx.limit("max_request_bytes", MAX_REQUEST_BODY_SIZE))
                body = self._read_json_body(limit, route)
                if body is None:
                    code = "bad_body"
                    return

            request = ServerRequest(
                method=method,
                path=path,
                query=query,
                headers=dict(self.headers),
                body=body,
                path_params=path_params,
                context={
                    "registry": getattr(self.server, "registry", None),
                    "route_table": table,
                    "policy": ctx,
                },
            )
            release_once, release = release, None
            self._invoke(route, request, release_once)
        finally:
            if release is not None:
                release()
            status = getattr(self, "_last_status", 0)
            if not code and status >= 400:
                code = "error"
            engine.audit(
                rule=ctx.rule if ctx is not None else None,
                identity=identity,
                endpoint=route.name,
                method=method,
                status=status,
                code=code,
                paths=ctx.paths_touched if ctx is not None else None,
            )

    def _dispatch_streaming(self, route: Any, request: ServerRequest) -> None:
        """Invoke a streaming (SSE) handler and flush its events."""
        try:
            result = route.handler(request)
        except PolicyDenied as exc:
            exc.endpoint = exc.endpoint or route.name
            self._send_denied(exc)
            return
        except Exception as exc:
            logging.getLogger(__name__).exception(
                "Unhandled exception in streaming handler %s: %s",
                route.name,
                exc,
            )
            self._send_json(
                500,
                {"error": str(exc), "type": type(exc).__name__},
            )
            return
        if isinstance(result, SSEResponse):
            self.send_response(result.status)
            for key, value in result.headers.items():
                self.send_header(key, value)
            self.end_headers()
            if result.event_iterator is not None:
                for event in result.event_iterator:
                    chunk = event.encode("utf-8") if isinstance(event, str) else event
                    self.wfile.write(chunk)
                    self.wfile.flush()
        elif isinstance(result, ServerResponse):
            # A streaming route may still choose to return a normal response.
            self._send_response(result)

    # ------------------------------------------------------------------ #
    # Method entry points
    # ------------------------------------------------------------------ #

    def do_GET(self) -> None:
        """Handle GET requests."""
        self._dispatch("GET")

    def do_POST(self) -> None:
        """Handle POST requests."""
        self._dispatch("POST")

    def do_PUT(self) -> None:
        """Handle PUT requests."""
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        """Handle DELETE requests."""
        self._dispatch("DELETE")


class SandboxServer:
    """Lightweight stdlib HTTP server for sandbox containers.

    Args:
        host: Bind address (default ``"0.0.0.0"``).
        registry: Optional :class:`CommandRegistry` (defaults to the module
            singleton).
        route_table: Optional :class:`RouteTable` (defaults to the module
            singleton populated by :mod:`easy_sandbox.server.routes`).
        pty_port: PTY WebSocket port (default ``EBX_PTY_PORT`` / ``9001``).
        policy: Optional :class:`ServerPolicy` (or a dict) enabling fine-grained
            per-endpoint control.  ``None`` loads the ambient policy
            (``EBX_SERVER_POLICY``, ``EBX_SERVER_POLICY_FILE`` or
            ``/etc/easy-sandbox/server-policy.json``) and otherwise keeps the
            historical behaviour.

    Example::

        server = SandboxServer()
        server.serve(port=9000)
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        registry: CommandRegistry | None = None,
        route_table: RouteTable | None = None,
        pty_port: int | None = None,
        policy: ServerPolicy | dict[str, Any] | None = None,
    ) -> None:
        self._host = host
        self.auth_token: str | None = os.environ.get(_TOKEN_ENV_VAR) or None
        self._httpd: ThreadingHTTPServer | None = None
        self._registry: CommandRegistry = registry if registry is not None else default_registry()
        self.route_table: RouteTable = route_table if route_table is not None else default_table()
        if isinstance(policy, dict):
            policy = ServerPolicy.from_dict(policy)
        elif policy is None:
            policy = ServerPolicy.from_environment()
        self.policy: ServerPolicy | None = policy
        self.policy_engine: PolicyEngine | None = None
        if policy is not None:
            # A policy gets its own table copy so group toggles never leak into
            # the module-level default table.
            self.route_table = self.route_table.copy()
            apply_groups(self.route_table, policy)
            self.policy_engine = PolicyEngine(
                policy, self.route_table, legacy_token=self.auth_token, registry=self._registry
            )
            for warning in self.policy_engine.lint():
                logging.getLogger(__name__).warning("policy lint: %s", warning)
        for raw in os.environ.get(_ENABLED_GROUPS_ENV_VAR, "").split(","):
            try:
                self.route_table.enable_group(CapabilityGroup(raw.strip()))
            except ValueError:
                continue
        if pty_port is not None:
            self._pty_port: int = pty_port
        else:
            try:
                self._pty_port = int(os.environ.get("EBX_PTY_PORT", "9001"))
            except (ValueError, TypeError):
                self._pty_port = 9001
        self._pty_thread: threading.Thread | None = None
        self._pty_stop_event: asyncio.Event | None = None
        self._pty_loop: asyncio.AbstractEventLoop | None = None

    def serve(self, port: int = 9000) -> None:
        """Start the server and block until interrupted.

        Args:
            port: TCP port to listen on (default ``9000``).
        """
        self._httpd = ThreadingHTTPServer((self._host, port), SandboxRequestHandler)
        # Store back-references so the handler can access auth_token, registry
        # and the route table.
        self._httpd.auth_token = self.auth_token  # type: ignore[attr-defined]
        self._httpd.registry = self._registry  # type: ignore[attr-defined]
        self._httpd.route_table = self.route_table  # type: ignore[attr-defined]
        self._httpd.policy_engine = self.policy_engine  # type: ignore[attr-defined]
        self._registry.freeze()

        # Start PTY WebSocket server in a background thread if TERMINAL enabled.
        if self.route_table.is_group_enabled(CapabilityGroup.TERMINAL):
            self._start_pty_server()

        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._stop_pty_server()
            self._httpd.server_close()

    def _start_pty_server(self) -> None:
        """Start the PTY WebSocket server in a background daemon thread."""
        import threading as _threading

        def _run_pty() -> None:
            import asyncio as _asyncio

            from .routes_pty import start_pty_server

            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)
            self._pty_loop = loop
            stop = _asyncio.Event()
            self._pty_stop_event = stop
            extra: dict[str, Any] = {}
            if self.policy_engine is not None:
                extra["policy_engine"] = self.policy_engine
            loop.run_until_complete(
                start_pty_server(self._host, self._pty_port, stop_event=stop, **extra)
            )

        self._pty_thread = _threading.Thread(target=_run_pty, daemon=True)
        self._pty_thread.start()

    def _stop_pty_server(self) -> None:
        """Signal the PTY WebSocket server to stop and clean up sessions."""
        from .routes_pty import pty_session_manager

        if self._pty_stop_event is not None and self._pty_loop is not None:
            self._pty_loop.call_soon_threadsafe(self._pty_stop_event.set)
        if self._pty_thread is not None:
            self._pty_thread.join(timeout=3)
        pty_session_manager.close_all()

    def shutdown(self) -> None:
        """Gracefully shut down a running server (thread-safe)."""
        self._stop_pty_server()
        if self._httpd is not None:
            self._httpd.shutdown()


def start(
    port: int = 9000,
    host: str = "0.0.0.0",
    registry: CommandRegistry | None = None,
) -> None:
    """Convenience function — create a :class:`SandboxServer` and serve.

    Args:
        port: TCP port (default ``9000``).
        host: Bind address (default ``"0.0.0.0"``).
        registry: Optional :class:`CommandRegistry` (uses the default
            singleton when ``None``).
    """
    server = SandboxServer(host=host, registry=registry)
    server.serve(port=port)
