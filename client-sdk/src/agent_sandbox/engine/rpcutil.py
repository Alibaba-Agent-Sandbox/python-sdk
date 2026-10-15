"""Turn SDK exceptions into gRPC status text and back."""

from __future__ import annotations

import json
from typing import Any, NoReturn

import grpc

from agent_sandbox.models.errors import SandboxError


def _public_message(exc: BaseException) -> str:
    """A non-empty message. ``str(StopAsyncIteration())`` and some RPC errors are blank."""
    text = str(exc).strip()
    if text:
        return text
    details = getattr(exc, "details", None)
    if callable(details):
        try:
            rendered = details()
        except Exception:
            rendered = ""
        if isinstance(rendered, str) and rendered.strip():
            return rendered.strip()
    return type(exc).__name__


def encode_error(exc: BaseException) -> str:
    """JSON status detail. The client rebuilds the same exception type."""
    if isinstance(exc, SandboxError):
        payload: dict[str, Any] = {
            "type": type(exc).__name__,
            "message": exc.message or _public_message(exc),
            "code": exc.code,
            "suggestion": exc.suggestion,
        }
        provider = getattr(exc, "provider", None)
        feature = getattr(exc, "feature", None)
        if provider and feature:
            payload["provider"] = provider
            payload["feature"] = feature
        envd_error = getattr(exc, "envd_error", None)
        if isinstance(envd_error, dict):
            payload["envd_error"] = envd_error
        rpc_path = getattr(exc, "rpc_path", None)
        if isinstance(rpc_path, str) and rpc_path:
            payload["rpc_path"] = rpc_path
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int) and status_code:
            payload["status_code"] = status_code
        body_text = getattr(exc, "body_text", None)
        if isinstance(body_text, str) and body_text:
            payload["body_text"] = body_text
    else:
        payload = {"type": type(exc).__name__, "message": _public_message(exc)}
    return json.dumps(payload)


async def abort_exc(context: Any, exc: BaseException) -> None:
    """Fail the RPC with *exc*. ``abort`` raises, so this does not return."""
    await context.abort(grpc.StatusCode.FAILED_PRECONDITION, encode_error(exc))


def _types() -> dict[str, type[SandboxError]]:
    import agent_sandbox.models.errors as errors

    return {
        name: obj
        for name, obj in vars(errors).items()
        if isinstance(obj, type) and issubclass(obj, SandboxError)
    }


def reraise(exc: BaseException) -> NoReturn:
    """Rebuild a :class:`SandboxError` from a gRPC failure, or raise *exc*."""
    details = getattr(exc, "details", None)
    text = details() if callable(details) else ""
    if not text:
        raise exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise exc from None
    if not isinstance(payload, dict):
        raise exc
    cls = _types().get(str(payload.get("type", "")))
    if cls is None:
        raise RuntimeError(str(payload.get("message") or text)) from exc
    code = payload.get("code") or None
    suggestion = payload.get("suggestion") or None
    message = str(payload.get("message") or "").strip() or str(
        payload.get("type") or "RuntimeError"
    )
    if payload.get("provider") and payload.get("feature"):
        raise cls(
            str(payload["provider"]),
            str(payload["feature"]),
            message=message,
            code=code,
            suggestion=suggestion,
        ) from exc
    extra: dict[str, Any] = {}
    if isinstance(payload.get("envd_error"), dict):
        extra["envd_error"] = payload["envd_error"]
    if isinstance(payload.get("rpc_path"), str) and payload["rpc_path"]:
        extra["rpc_path"] = payload["rpc_path"]
    if isinstance(payload.get("status_code"), int):
        extra["status_code"] = payload["status_code"]
    if isinstance(payload.get("body_text"), str):
        extra["body_text"] = payload["body_text"]
    raise cls(message, code=code, suggestion=suggestion, **extra) from exc
