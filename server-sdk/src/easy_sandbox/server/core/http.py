"""HTTP glue: mounts ``POST /ops/{id}`` and ``GET /ops`` on the v1 request handler.

The v1 dispatcher consults this module only for a request that matches no v1 route, so every
legacy route (including one a user registered under ``/ops/...``) is served exactly as before.
The glue reuses the handler's own helpers for body limits and response rendering, so statuses,
headers and bodies of an operation call are rendered like the legacy route it wraps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, unquote

from ..router import default_table
from ..types import ServerResponse
from .dispatch import Outcome, Pipeline, Rejected
from .policy import Policy

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler

__all__ = ["pipeline_for", "serve_ops"]

_MAX_ID_LENGTH = 128
_MAX_BODY = 10 * 1024 * 1024
_ATTR = "_ops_pipeline"


def pipeline_for(httpd: Any) -> Pipeline:
    """The pipeline of a running ``ThreadingHTTPServer`` (rebuilt if its wiring changed)."""
    table = getattr(httpd, "route_table", None) or default_table()
    engine = getattr(httpd, "policy_engine", None)
    token = getattr(httpd, "auth_token", None)
    commands = getattr(httpd, "registry", None)
    key = (id(table), id(engine), token, id(commands))
    cached = getattr(httpd, _ATTR, None)
    if cached is not None and cached[0] == key:
        pipeline: Pipeline = cached[1]
        return pipeline
    policy = (
        Policy.from_engine(engine) if engine is not None else Policy.open(table, auth_token=token)
    )
    pipeline = Pipeline(table, policy, commands)
    setattr(httpd, _ATTR, (key, pipeline))
    return pipeline


def _send(handler: Any, outcome: Outcome) -> None:
    stream = outcome.stream
    if stream is None:
        handler._send_response(ServerResponse(outcome.status, outcome.body, outcome.headers))
        return
    handler.send_response(stream.status)
    for key, value in stream.headers.items():
        handler.send_header(key, value)
    handler.end_headers()
    if stream.event_iterator is not None:
        for event in stream.event_iterator:
            handler.wfile.write(event.encode("utf-8") if isinstance(event, str) else event)
            handler.wfile.flush()


def _query_args(raw_query: str) -> dict[str, Any]:
    args: dict[str, Any] = {}
    for key, values in parse_qs(raw_query).items():
        args[key] = values if key == "ids" else values[-1]
    return args


def serve_ops(handler: BaseHTTPRequestHandler, method: str, path: str, raw_query: str = "") -> bool:
    """Serve ``POST /ops/{id}`` and ``GET /ops``; return ``False`` for any other request."""
    if method == "GET" and path == "/ops":
        op_id = "core.describe"
    elif method == "POST" and path.startswith("/ops/"):
        op_id = unquote(path[len("/ops/") :])
        if not op_id or "/" in op_id:
            return False
    else:
        return False
    op_id = op_id[:_MAX_ID_LENGTH]

    pipeline = pipeline_for(handler.server)
    handler._last_status = 0  # type: ignore[attr-defined]
    try:
        call = pipeline.begin(op_id, handler.headers)
    except Rejected as rejected:
        _send(handler, rejected.outcome)
        return True
    try:
        args: Any
        if method == "GET":
            args = _query_args(raw_query)
        else:
            if handler.headers.get("Transfer-Encoding"):
                outcome = Outcome(
                    400,
                    {
                        "error": "Transfer-Encoding is not supported; send Content-Length",
                        "type": "ValueError",
                        "code": "unsupported_encoding",
                    },
                    code="unsupported_encoding",
                )
                pipeline.finish(call, outcome)
                _send(handler, outcome)
                return True
            ctx = call.admission.ctx
            limit = int(ctx.limit("max_request_bytes", _MAX_BODY)) if ctx is not None else _MAX_BODY
            args = handler._read_json_body(limit)  # type: ignore[attr-defined]
            if args is None:
                status = getattr(handler, "_last_status", 0)
                pipeline.finish(call, Outcome(status, code="bad_body"))
                return True
            if not isinstance(args, dict):
                outcome = Outcome(
                    400,
                    {
                        "error": "Request body must be a JSON object",
                        "type": "ValueError",
                        "code": "args.invalid",
                    },
                    code="args.invalid",
                )
                pipeline.finish(call, outcome)
                _send(handler, outcome)
                return True
        outcome = pipeline.run(call, args, handler.headers)
        _send(handler, outcome)
    finally:
        call.admission.close()
    return True
