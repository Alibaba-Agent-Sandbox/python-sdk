"""Turn SDK exceptions into gRPC status text and back."""

from __future__ import annotations

import json
from typing import Any, NoReturn

import grpc

from agent_sandbox.models.errors import SandboxError


def encode_error(exc: BaseException) -> str:
    """JSON status detail. The client rebuilds the same exception type."""
    if isinstance(exc, SandboxError):
        payload = {
            "type": type(exc).__name__,
            "message": exc.message,
            "code": exc.code,
            "suggestion": exc.suggestion,
        }
        provider = getattr(exc, "provider", None)
        feature = getattr(exc, "feature", None)
        if provider and feature:
            payload["provider"] = provider
            payload["feature"] = feature
    else:
        payload = {"type": "RuntimeError", "message": str(exc)}
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
    message = str(payload.get("message") or "")
    if payload.get("provider") and payload.get("feature"):
        raise cls(
            str(payload["provider"]),
            str(payload["feature"]),
            message=message,
            code=code,
            suggestion=suggestion,
        ) from exc
    raise cls(message, code=code, suggestion=suggestion) from exc
