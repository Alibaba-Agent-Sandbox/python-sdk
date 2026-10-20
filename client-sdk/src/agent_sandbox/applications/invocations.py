"""Body-authenticated FC invocation envelopes, independent of header forwarding."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from .models import ApplicationError, canonical

PROTOCOL = "agent-sandbox-invoke/v1"


def sign_invocation(payload: dict[str, Any], token: str, *, role: str) -> dict[str, Any]:
    """Sign a run-scoped/task or bounded dispatcher invocation without embedding a secret.

    A replay cannot claim a run twice. Dispatcher replays only drain durable state
    under its own leases. No expiry is used because asynchronous queues can delay
    delivery; business run deadlines remain authoritative. Rotate the shared key
    with deployment coordination for queued envelopes.
    """
    if role not in {"worker", "dispatcher"} or len(token) < 32:
        raise ValueError("A valid private role and at least 32-character token are required")
    value = {"protocol": PROTOCOL, "role": role, "payload": payload}
    signature = hmac.new(token.encode(), canonical(value).encode(), hashlib.sha256).hexdigest()
    return {**value, "signature": signature}


def verify_invocation(envelope: dict[str, Any], token: str, *, role: str) -> dict[str, Any]:
    """Verify the body before dispatching an operation; never expose signature details."""
    # FC timer events wrap the configured string payload in documented metadata.
    # Metadata is not an authentication signal; only the inner HMAC is trusted.
    if role == "dispatcher" and set(envelope) == {"triggerTime", "triggerName", "payload"}:
        try:
            nested = json.loads(envelope["payload"])
        except (ValueError, TypeError) as exc:
            raise ApplicationError(401, "unauthenticated", "Private invocation required") from exc
        if not isinstance(nested, dict):
            raise ApplicationError(401, "unauthenticated", "Private invocation required")
        envelope = nested
    payload, signature = envelope.get("payload"), envelope.get("signature")
    if (
        set(envelope) != {"protocol", "role", "payload", "signature"}
        or envelope.get("protocol") != PROTOCOL
        or envelope.get("role") != role
        or not isinstance(payload, dict)
        or not isinstance(signature, str)
        or len(signature) != 64
        or not signature.isascii()
    ):
        raise ApplicationError(401, "unauthenticated", "Private invocation required")
    expected = sign_invocation(payload, token, role=role)["signature"]
    if not hmac.compare_digest(signature, expected):
        raise ApplicationError(401, "unauthenticated", "Private invocation required")
    return payload
