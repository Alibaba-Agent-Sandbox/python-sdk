"""PTY WebSocket authorisation under a policy (real server + real websockets client)."""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

if TYPE_CHECKING:
    from ._live import Live

TOKEN = "pty-user-token-123456"
OTHER = "no-terminal-token-654321"


def sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


POLICY: dict[str, Any] = {
    "auth": {
        "tokens": [
            {"id": "term", "token_sha256": sha(TOKEN), "scopes": ["terminal:*"]},
            {"id": "other", "token_sha256": sha(OTHER), "scopes": ["files:read"]},
        ]
    }
}


def _open(live: Live, token: str | None, session: str, header: bool = True) -> tuple[bool, Any]:
    """Return ``(connected_and_started, first_message_or_close_code)``."""
    url = f"ws://127.0.0.1:{live.pty_port}/?session_id={session}"
    headers = {"X-Access-Token": token} if token and header else {}
    if token and not header:
        url += f"&token={token}"
    try:
        with connect(url, additional_headers=headers, open_timeout=5) as ws:
            message = json.loads(ws.recv(timeout=5))
            return message.get("event") == "started", message
    except ConnectionClosed as exc:
        return False, exc.rcvd.code if exc.rcvd else None
    except InvalidStatus as exc:
        return False, exc.response.status_code


def _wait_listening(live: Live) -> None:
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with connect(f"ws://127.0.0.1:{live.pty_port}/", open_timeout=1):
                return
        except Exception:
            time.sleep(0.1)


@pytest.fixture
def live(live_server: Any) -> Any:
    server: Live = live_server(policy=POLICY)
    _wait_listening(server)
    return server


def _session(live: Live, token: str) -> str:
    status, body, _ = live.request(
        "POST", "/pty/sessions", {"shell": "/bin/sh"}, headers={"X-Access-Token": token}
    )
    assert status in (200, 201), body
    return str(body.get("id") or body.get("session_id"))


class TestPtyWebSocketAuth:
    def test_authorised_identity_connects_via_header(self, live: Live) -> None:
        session = _session(live, TOKEN)
        ok, message = _open(live, TOKEN, session)
        assert ok, message

    def test_authorised_identity_connects_via_legacy_query_token(self, live: Live) -> None:
        session = _session(live, TOKEN)
        ok, message = _open(live, TOKEN, session, header=False)
        assert ok, message

    def test_missing_credentials_rejected(self, live: Live) -> None:
        session = _session(live, TOKEN)
        ok, detail = _open(live, None, session)
        assert not ok and detail == 4001

    def test_wrong_token_rejected(self, live: Live) -> None:
        session = _session(live, TOKEN)
        ok, detail = _open(live, "wrong-token-000000", session)
        assert not ok and detail == 4001

    def test_identity_without_scope_forbidden(self, live: Live) -> None:
        session = _session(live, TOKEN)
        ok, detail = _open(live, OTHER, session)
        assert not ok and detail == 4003

    def test_session_creation_needs_scope_and_url_has_no_token(self, live: Live) -> None:
        status, _, _ = live.request(
            "POST", "/pty/sessions", {"shell": "/bin/sh"}, headers={"X-Access-Token": OTHER}
        )
        assert status == 403
        status, body, _ = live.request(
            "POST", "/pty/sessions", {"shell": "/bin/sh"}, headers={"X-Access-Token": TOKEN}
        )
        assert status in (200, 201)
        assert TOKEN not in json.dumps(body)


def test_disabled_pty_connect_is_refused(live_server: Any) -> None:
    live: Live = live_server(policy={**POLICY, "endpoints": {"pty_connect": {"enabled": False}}})
    _wait_listening(live)
    session = _session(live, TOKEN)
    ok, detail = _open(live, TOKEN, session)
    assert not ok and detail == 4003
