"""Transport-level agents behaviour of ``app.py``: the responses WebSocket and multipart files."""

from __future__ import annotations

import base64
import json
import os
import socket
from typing import TYPE_CHECKING, Any

import pytest
from websockets.sync.client import connect

import easy_sandbox.server.routes_agents  # noqa: F401  (registers routes)
from easy_sandbox.server.agents.local_state import get_state
from easy_sandbox.server.routes_agents import reset_agent_runtime

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from ._live import Live

CODEX_SCRIPT = """#!/bin/sh
cat >/dev/null
printf '%s\\n' '{"type":"thread.started","thread_id":"thr-ws-1"}'
printf '%s\\n' '{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"ws-ok"}}'
printf '%s\\n' '{"type":"turn.completed","usage":{"input_tokens":3,"output_tokens":2}}'
exit 0
"""


@pytest.fixture(autouse=True)
def _agents_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    codex = bindir / "codex"
    codex.write_text(CODEX_SCRIPT)
    codex.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    for name in (
        "EBX_AGENTS_DEFAULT",
        "EBX_AGENTS_CONFIG",
        "EBX_SERVER_TOKEN",
        "EBX_AGENTS_MAX_FILE_BYTES",
        "CODEX_HOME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EBX_AGENTS_PERSIST", "0")
    monkeypatch.setenv("EBX_AGENTS_RESPONSES_WORKSPACE", str(tmp_path / "responses-ws"))
    monkeypatch.setenv("EBX_SERVER_ENABLED_GROUPS", "agents")
    reset_agent_runtime()
    yield
    reset_agent_runtime()


def _recv_events(conn: Any, until: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while True:
        event = json.loads(conn.recv(timeout=20))
        events.append(event)
        if event["type"] == until or event["type"] == "error":
            return events


class TestResponsesWebSocket:
    def test_create_and_queued_steer_over_a_real_socket(
        self, live_server: Callable[..., Live]
    ) -> None:
        live = live_server()
        with connect(f"ws://127.0.0.1:{live.port}/v1/responses", open_timeout=10) as conn:
            conn.send(json.dumps({"type": "response.create", "model": "codex", "input": "hi"}))
            events = _recv_events(conn, "response.completed")
            assert events[0]["type"] == "response.created"
            first = events[-1]["response"]
            assert first["status"] == "completed"
            delta = next(e for e in events if e["type"] == "response.output_text.delta")
            assert delta["delta"] == "ws-ok"

            conn.send(
                json.dumps(
                    {
                        "type": "response.steer",
                        "model": "codex",
                        "input": "again",
                        "previous_response_id": first["id"],
                    }
                )
            )
            steered = _recv_events(conn, "response.completed")[-1]["response"]
            assert steered["previous_response_id"] == first["id"]
            assert "queued_steer" in steered["x_easy_sandbox"]["differences"]

            conn.send(json.dumps({"type": "response.bogus"}))
            assert json.loads(conn.recv(timeout=10))["type"] == "error"
            conn.send("not json")
            assert json.loads(conn.recv(timeout=10))["type"] == "error"
            conn.ping().wait(5)

    def test_plain_get_keeps_the_explicit_400(self, live_server: Callable[..., Live]) -> None:
        live = live_server()
        status, body = live.get("/v1/responses")
        assert status == 400
        assert body["error"]["code"] == "agents.websocket_upgrade_required"

    def test_upgrade_without_a_key_is_a_400_not_a_hang(
        self, live_server: Callable[..., Live]
    ) -> None:
        live = live_server()
        with socket.create_connection(("127.0.0.1", live.port), timeout=10) as sock:
            sock.sendall(
                b"GET /v1/responses HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\n"
                b"Connection: Upgrade\r\n\r\n"
            )
            head = sock.recv(4096)
        assert head.startswith(b"HTTP/1.0 400") or head.startswith(b"HTTP/1.1 400")
        assert b"agents.websocket_handshake_invalid" in head

    def test_token_is_required_for_the_upgrade(
        self, live_server: Callable[..., Live], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EBX_SERVER_TOKEN", "s3cret")
        live = live_server()
        url = f"ws://127.0.0.1:{live.port}/v1/responses"
        with socket.create_connection(("127.0.0.1", live.port), timeout=10) as sock:
            sock.sendall(
                b"GET /v1/responses HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\n"
                b"Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
            )
            assert b" 401 " in sock.recv(4096).split(b"\r\n", 1)[0]
        with connect(
            url, additional_headers={"Authorization": "Bearer s3cret"}, open_timeout=10
        ) as conn:
            conn.send(json.dumps({"type": "response.create", "model": "codex", "input": "hi"}))
            assert _recv_events(conn, "response.completed")[-1]["response"]["status"] == (
                "completed"
            )


BOUNDARY = "----ebxTestBoundary7MA4YWxkTrZu0gW"
PAYLOAD = b"\x00\x01binary\r\nline2\r\n--not-a-boundary\xff\xfe" + bytes(range(256))


def multipart(fields: dict[str, str], filename: str, data: bytes) -> bytes:
    out = b""
    for name, value in fields.items():
        out += (
            f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    out += (
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    return out + data + f"\r\n--{BOUNDARY}--\r\n".encode()


class TestMultipartFiles:
    def _post(self, live: Live, raw: bytes) -> tuple[int, Any]:
        status, body, _ = live.request(
            "POST",
            "/v1/files",
            raw_body=raw,
            headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
        )
        return status, body

    def test_multipart_upload_round_trips_the_bytes(
        self, live_server: Callable[..., Live], tmp_path: Path
    ) -> None:
        live = live_server()
        status, blob = self._post(
            live, multipart({"purpose": "user_data"}, "report.bin", PAYLOAD)
        )
        assert status == 200, blob
        assert blob["object"] == "file" and blob["bytes"] == len(PAYLOAD)
        assert blob["filename"] == "report.bin" and blob["purpose"] == "user_data"

        stored = get_state().blobs.get("local", blob["id"])
        assert stored is not None and stored.private["data"] == PAYLOAD

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        status, env = live.post(
            "/v1/agents/environments",
            {
                "environment": {
                    "type": "self_hosted",
                    "workspace_directory": str(workspace),
                    "files": [
                        {"type": "file_id", "file_id": blob["id"], "path": "/workspace/up.bin"}
                    ],
                }
            },
        )
        assert status == 200, env
        assert (workspace / "up.bin").read_bytes() == PAYLOAD

    def test_filename_field_wins_and_bad_purpose_is_refused(
        self, live_server: Callable[..., Live]
    ) -> None:
        live = live_server()
        status, blob = self._post(
            live, multipart({"purpose": "user_data", "filename": "named.txt"}, "x.txt", b"abc")
        )
        assert status == 200 and blob["filename"] == "named.txt"
        status, body = self._post(live, multipart({"purpose": "assistants"}, "x.txt", b"abc"))
        assert status == 400 and body["error"]["param"] == "purpose"

    def test_malformed_multipart_is_a_400(self, live_server: Callable[..., Live]) -> None:
        live = live_server()
        status, body = self._post(live, b"this is not multipart")
        assert status == 400

    def test_json_path_is_unchanged(self, live_server: Callable[..., Live]) -> None:
        live = live_server()
        data = base64.b64encode(b"json-bytes").decode()
        status, blob = live.post("/v1/files", {"purpose": "user_data", "data": data})
        assert status == 200 and blob["bytes"] == len(b"json-bytes")
        stored = get_state().blobs.get("local", blob["id"])
        assert stored is not None and stored.private["data"] == b"json-bytes"
