"""Local webhook signer and deliverer (O-06).

Events are signed the Standard Webhooks way (``webhook-id``, ``webhook-timestamp``,
``webhook-signature: v1,<base64 HMAC-SHA256>``) with the endpoint's ``whsec_`` secret, which
is why the official ``client.webhooks.unwrap`` can verify them. Delivery never follows
redirects and refuses private destinations unless ``EBX_AGENTS_ALLOW_PRIVATE_URLS=1``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from .errors import LocalApiError
from .local_state import get_state

if TYPE_CHECKING:
    from .runtime import Session

__all__ = [
    "SUPPORTED_EVENTS",
    "WebhookDeliveryError",
    "build_event",
    "deliver",
    "emit",
    "new_secret",
    "sign",
    "watch_session",
]

_log = logging.getLogger(__name__)

#: Event types this server actually sends (``agent.session.action_required`` never occurs).
SUPPORTED_EVENTS = (
    "agent.session.created",
    "agent.session.in_progress",
    "agent.session.idle",
    "agent.session.failed",
)
_TIMEOUT_S = 5.0


class WebhookDeliveryError(Exception):
    """The receiver could not be reached (not an HTTP status)."""


def new_secret() -> str:
    """A fresh ``whsec_`` signing secret."""
    return "whsec_" + base64.b64encode(os.urandom(32)).decode()


def _key(secret: str) -> bytes:
    raw = secret[6:] if secret.startswith("whsec_") else secret
    try:
        return base64.b64decode(raw, validate=True)
    except ValueError:
        return raw.encode()


def sign(secret: str, msg_id: str, timestamp: int, payload: bytes) -> str:
    """``v1,<signature>`` over ``<id>.<timestamp>.<payload>``."""
    signed = f"{msg_id}.{timestamp}.".encode() + payload
    digest = hmac.new(_key(secret), signed, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def build_event(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """The event envelope the official SDK unwraps."""
    return {
        "id": "evt_" + uuid.uuid4().hex[:24],
        "object": "event",
        "created_at": int(time.time()),
        "type": event_type,
        "data": data,
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _allow_private() -> bool:
    return os.environ.get("EBX_AGENTS_ALLOW_PRIVATE_URLS", "") == "1"


def _check_destination(url: str) -> None:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if _allow_private():
        return
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError):
        raise WebhookDeliveryError("the webhook host does not resolve") from None
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise WebhookDeliveryError("the webhook host resolves to a private address")


def deliver(url: str, secret: str, event: dict[str, Any]) -> int:
    """POST *event* signed with *secret*; returns the receiver's HTTP status."""
    _check_destination(url)
    payload = json.dumps(event, separators=(",", ":")).encode()
    timestamp = int(time.time())
    request = urllib.request.Request(  # noqa: S310
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "easy-sandbox-agents-local",
            "webhook-id": event["id"],
            "webhook-timestamp": str(timestamp),
            "webhook-signature": sign(secret, event["id"], timestamp, payload),
        },
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=_TIMEOUT_S) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, OSError, ValueError):
        raise WebhookDeliveryError("the webhook receiver could not be reached") from None


def check_endpoint_url(url: Any) -> None:
    """Admit a webhook URL: https (http only with ``EBX_AGENTS_WEBHOOK_ALLOW_HTTP=1``)."""
    from .api_common import url_check

    insecure = os.environ.get("EBX_AGENTS_WEBHOOK_ALLOW_HTTP", "") == "1"
    try:
        url_check(url, "url", https_only=not insecure)
    except LocalApiError:
        raise


def emit(owner: str, event_type: str, data: dict[str, Any]) -> None:
    """Deliver *event_type* to every endpoint of *owner* that subscribed (best effort)."""
    for record in get_state().webhooks.list(owner):
        if event_type not in record.data["event_types"]:
            continue
        event = build_event(event_type, data)
        threading.Thread(
            target=_deliver_quietly,
            args=(record.data["url"], record.private["secret"], event),
            name="agents-webhook",
            daemon=True,
        ).start()


def _deliver_quietly(url: str, secret: str, event: dict[str, Any]) -> None:
    try:
        deliver(url, secret, event)
    except WebhookDeliveryError as exc:
        _log.debug("webhook delivery failed: %s", exc)


def watch_session(session: Session, owner: str, after_seq: int, environment_id: str | None) -> None:
    """Send ``in_progress``, ``failed`` and ``idle`` events for turns after *after_seq*."""
    if not get_state().webhooks.list(owner):
        return
    data = {
        "id": session.id,
        "environment_type": "self_hosted",
        "environment_id": environment_id,
    }

    def run() -> None:
        try:
            for event in session.subscribe(after=after_seq, ping_s=5.0):
                if event is None:
                    continue
                if event.type == "session.in_progress":
                    emit(owner, "agent.session.in_progress", data)
                elif event.type == "turn.failed":
                    emit(owner, "agent.session.failed", data)
                elif event.type == "session.idle":
                    emit(owner, "agent.session.idle", data)
                    with session.cond:
                        done = (
                            session.active is None
                            and not session.queue
                            and session.last_seq == event.seq
                        )
                    if done:
                        return
        except Exception:
            _log.debug("webhook watcher stopped", exc_info=True)

    threading.Thread(target=run, name="agents-webhook-watch", daemon=True).start()
