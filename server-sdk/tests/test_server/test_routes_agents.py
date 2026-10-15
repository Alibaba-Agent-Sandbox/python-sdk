"""HTTP tests for the Codex / Qwen Code agents slice.

Fake ``codex`` and ``qwen`` executables are shell scripts on ``PATH``. They emit
one JSONL line and exit 0. No real CLI is downloaded.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import threading
import time
from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

import agent_sandbox.server.routes_agents  # noqa: F401  (registers routes)
from agent_sandbox.server.app import SandboxRequestHandler
from agent_sandbox.server.router import CapabilityGroup, default_table
from agent_sandbox.server.routes_agents import reset_agent_runtime

from ._live import wire


def _fake_script(payload: dict[str, Any]) -> str:
    """Shell script that prints one JSONL line and exits 0."""
    line = json.dumps(payload, separators=(",", ":"))
    return f"#!/bin/sh\nprintf '%s\\n' '{line}'\nexit 0\n"


_CODEX_SH = _fake_script(
    {
        "type": "item.completed",
        "item": {"id": "m1", "type": "agent_message", "text": "codex-fake-ok"},
    }
)
_QWEN_SH = _fake_script(
    {
        "type": "assistant",
        "message": {
            "id": "m1",
            "content": [{"type": "text", "text": "qwen-fake-ok"}],
        },
    }
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(port: int, *, auth_token: str | None = None) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), SandboxRequestHandler)
    wire(httpd, auth_token=auth_token)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    return httpd


def _request(
    port: int,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    *,
    timeout: float = 15,
) -> tuple[int, Any, dict[str, str]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    payload = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    conn.request(method, path, body=payload, headers=hdrs)
    resp = conn.getresponse()
    raw = resp.read()
    response_headers = {key.lower(): value for key, value in resp.getheaders()}
    status = resp.status
    conn.close()
    if not raw:
        return status, {}, response_headers
    return status, json.loads(raw.decode()), response_headers


def _message_texts(payload: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for item in payload.get("data") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("text"):
                texts.append(str(part["text"]))
    return texts


def _wait_for_text(port: int, session_id: str, needle: str) -> dict[str, Any]:
    deadline = time.time() + 15
    last_items: Any = None
    last_turns: Any = None
    while time.time() < deadline:
        status, items, _ = _request(
            port, "GET", f"/v1/agents/sessions/{session_id}/items?limit=100&order=asc"
        )
        assert status == 200
        last_items = items
        if any(needle in text for text in _message_texts(items)):
            return items
        status, turns, _ = _request(
            port, "GET", f"/v1/agents/sessions/{session_id}/turns?limit=100&order=asc"
        )
        assert status == 200
        last_turns = turns
        for turn in turns.get("data") or []:
            if turn.get("status") in ("failed", "cancelled"):
                pytest.fail(f"turn {turn.get('status')}: {turn.get('error')} items={items}")
        time.sleep(0.05)
    pytest.fail(f"timed out waiting for {needle!r}: items={last_items} turns={last_turns}")


def _wait_for_completed_turn(port: int, session_id: str) -> dict[str, Any]:
    """The message text can land before the turn row flips to completed."""
    deadline = time.time() + 15
    last: Any = None
    while time.time() < deadline:
        status, turns, _ = _request(
            port, "GET", f"/v1/agents/sessions/{session_id}/turns?limit=100&order=asc"
        )
        assert status == 200
        last = turns
        data = turns.get("data") or []
        if data and data[-1].get("status") == "completed":
            return turns
        for turn in data:
            if turn.get("status") in ("failed", "cancelled"):
                pytest.fail(f"turn {turn.get('status')}: {turn.get('error')}")
        time.sleep(0.05)
    pytest.fail(f"timed out waiting for a completed turn: {last}")


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("ABX_AGENTS_PERSIST", "0")
    monkeypatch.delenv("ABX_AGENTS_DEFAULT", raising=False)
    monkeypatch.delenv("ABX_AGENTS_CONFIG", raising=False)
    monkeypatch.delenv("ABX_SERVER_TOKEN", raising=False)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, script in (("codex", _CODEX_SH), ("qwen", _QWEN_SH)):
        path = bindir / name
        path.write_text(script)
        path.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    reset_agent_runtime()
    yield
    reset_agent_runtime()


@pytest.fixture()
def workspace(tmp_path: Path) -> str:
    root = tmp_path / "workspace"
    root.mkdir()
    return str(root)


def _enable() -> None:
    default_table().enable_group(CapabilityGroup.AGENTS)


class TestRoutesAgents:
    def test_group_off_unless_enabled(self, workspace: str) -> None:
        table = default_table()
        table.disable_group(CapabilityGroup.AGENTS)
        assert table.group_overrides[CapabilityGroup.AGENTS] is False
        port = _find_free_port()
        httpd = _start_server(port)
        try:
            status, body, _ = _request(
                port,
                "POST",
                "/v1/agents/sessions",
                {"agent": {"model": "codex"}, "environment": {"workspace_directory": workspace}},
            )
            assert status == 404
            assert "disabled" in str(body.get("error"))
        finally:
            httpd.shutdown()

    def test_each_adapter_event_and_items(self, workspace: str) -> None:
        _enable()
        port = _find_free_port()
        httpd = _start_server(port)
        try:
            for model, needle in (("codex", "codex-fake-ok"), ("qwen-code", "qwen-fake-ok")):
                status, created, _ = _request(
                    port,
                    "POST",
                    "/v1/agents/sessions",
                    {
                        "agent": {"model": model},
                        "environment": {
                            "type": "self_hosted",
                            "workspace_directory": workspace,
                        },
                    },
                )
                assert status == 200, created
                assert created["object"] == "agent.session"
                session_id = created["id"]

                status, ack, _ = _request(
                    port,
                    "POST",
                    f"/v1/agents/sessions/{session_id}/events",
                    {
                        "events": [
                            {
                                "type": "agent.session.input.message",
                                "input": [
                                    {
                                        "type": "message",
                                        "role": "user",
                                        "content": [{"type": "input_text", "text": "hello"}],
                                    }
                                ],
                            }
                        ]
                    },
                )
                assert status == 202
                assert ack == {}

                items = _wait_for_text(port, session_id, needle)
                assert any(needle in text for text in _message_texts(items))

                turns = _wait_for_completed_turn(port, session_id)
                assert turns["data"][-1]["status"] == "completed"
                turn_id = turns["data"][-1]["id"]
                status, one, _ = _request(
                    port, "GET", f"/v1/agents/sessions/{session_id}/turns/{turn_id}"
                )
                assert status == 200
                assert one["id"] == turn_id
                status, turn_items, _ = _request(
                    port,
                    "GET",
                    f"/v1/agents/sessions/{session_id}/turns/{turn_id}/items?limit=100",
                )
                assert status == 200
                assert any(needle in text for text in _message_texts(turn_items))
        finally:
            httpd.shutdown()

    def test_aliases_unknown_adapter_and_default(self, workspace: str, tmp_path: Path) -> None:
        _enable()
        port = _find_free_port()
        httpd = _start_server(port)
        env = {"type": "self_hosted", "workspace_directory": workspace}
        try:
            status, body, headers = _request(
                port,
                "POST",
                "/v1/agents/sessions",
                {"agent": {"model": "gpt-5-codex"}, "environment": env},
            )
            assert status == 200, body
            assert body["agent"]["id"] == "codex"
            assert body["agent"]["model"] == "gpt-5-codex"
            assert headers.get("x-agent-sandbox-local") == "1"

            status, runtimes, _ = _request(port, "GET", "/v1/agents/runtimes?limit=100&order=asc")
            assert status == 200
            assert [item["name"] for item in runtimes["data"]] == [
                "codex",
                "qwen-code",
                "claude-code",
                "command",
                "cursor",
            ]
            assert [item["implemented"] for item in runtimes["data"]] == [
                True,
                True,
                False,
                False,
                False,
            ]
            assert [item["default"] for item in runtimes["data"]] == [True] + [False] * 4

            status, body, headers = _request(
                port,
                "POST",
                "/v1/agents/sessions",
                {"adapter": "claude-code", "environment": env},
            )
            assert status == 404
            assert body["error"]["type"] == "not_found_error"
            assert headers.get("x-should-retry") == "false"

            status, body, headers = _request(
                port,
                "POST",
                "/v1/agents/sessions",
                {"agent": {"model": "cursor"}, "environment": env},
                headers={"X-ABX-Adapter": "cursor"},
            )
            assert status == 404
            assert body["error"]["type"] == "not_found_error"
            assert headers.get("x-should-retry") == "false"

            for model in ("qwen", "qwencode"):
                status, created, _ = _request(
                    port,
                    "POST",
                    "/v1/agents/sessions",
                    {"agent": {"model": model}, "environment": env},
                )
                assert status == 200, created
                assert created["agent"]["id"] == "qwen-code"

            os.environ["ABX_AGENTS_DEFAULT"] = "qwen-code"
            reset_agent_runtime()
            status, runtimes, _ = _request(port, "GET", "/v1/agents/runtimes?limit=100&order=asc")
            assert status == 200
            assert [item["default"] for item in runtimes["data"]] == [False, True] + [False] * 3
            status, created, _ = _request(
                port,
                "POST",
                "/v1/agents/sessions",
                {"agent": {"model": "gpt-5-codex"}, "environment": env},
            )
            assert status == 200, created
            assert created["agent"]["id"] == "qwen-code"
            assert created["agent"]["model"] == "gpt-5-codex"

            config = tmp_path / "agents.json"
            config.write_text(json.dumps({"agents": {"default": "qwen-code"}}))
            os.environ.pop("ABX_AGENTS_DEFAULT", None)
            os.environ["ABX_AGENTS_CONFIG"] = str(config)
            status, created, _ = _request(
                port,
                "POST",
                "/v1/agents/sessions",
                {"agent": {"model": "gpt-5-codex"}, "environment": env},
            )
            assert status == 200, created
            assert created["agent"]["id"] == "qwen-code"
        finally:
            os.environ.pop("ABX_AGENTS_DEFAULT", None)
            os.environ.pop("ABX_AGENTS_CONFIG", None)
            httpd.shutdown()

    def test_idempotency_key_replays_202(self, workspace: str) -> None:
        _enable()
        port = _find_free_port()
        httpd = _start_server(port)
        try:
            status, created, _ = _request(
                port,
                "POST",
                "/v1/agents/sessions",
                {
                    "adapter": "codex",
                    "environment": {"workspace_directory": workspace},
                },
            )
            assert status == 200, created
            session_id = created["id"]
            payload = {
                "events": [
                    {"type": "agent.session.input.message", "input": "hello"},
                ]
            }
            headers = {"Idempotency-Key": "same-key"}
            first, _, _ = _request(
                port, "POST", f"/v1/agents/sessions/{session_id}/events", payload, headers=headers
            )
            second, _, _ = _request(
                port, "POST", f"/v1/agents/sessions/{session_id}/events", payload, headers=headers
            )
            assert first == 202
            assert second == 202
            _wait_for_text(port, session_id, "codex-fake-ok")
            status, turns, _ = _request(
                port, "GET", f"/v1/agents/sessions/{session_id}/turns?limit=100"
            )
            assert status == 200
            assert len(turns["data"]) == 1

            mismatch, body, headers = _request(
                port,
                "POST",
                f"/v1/agents/sessions/{session_id}/events",
                {"events": [{"type": "agent.session.input.message", "input": "other"}]},
                headers=headers,
            )
            assert mismatch == 409
            assert body["error"]["code"] == "idempotency.mismatch"
            assert headers.get("x-should-retry") == "false"
            status, turns, _ = _request(
                port, "GET", f"/v1/agents/sessions/{session_id}/turns?limit=100"
            )
            assert len(turns["data"]) == 1
        finally:
            httpd.shutdown()

    def test_event_stream_and_runtimes(self, workspace: str) -> None:
        _enable()
        port = _find_free_port()
        httpd = _start_server(port)
        try:
            status, created, _ = _request(
                port,
                "POST",
                "/v1/agents/sessions",
                {"adapter": "qwen", "environment": {"workspace_directory": workspace}},
            )
            assert status == 200, created
            session_id = created["id"]
            status, _, _ = _request(
                port,
                "POST",
                f"/v1/agents/sessions/{session_id}/events",
                {"events": [{"type": "agent.session.input.message", "input": "hello"}]},
            )
            assert status == 202
            _wait_for_text(port, session_id, "qwen-fake-ok")

            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request(
                "GET",
                f"/v1/agents/sessions/{session_id}/events?after=0",
                headers={"Accept": "text/event-stream"},
            )
            resp = conn.getresponse()
            assert resp.status == 200
            assert resp.getheader("Content-Type", "").startswith("text/event-stream")
            streamed = resp.read().decode()
            conn.close()
            assert "qwen-fake-ok" in streamed
            assert "agent.session.turn.completed" in streamed

            status, runtimes, _ = _request(port, "GET", "/v1/agents/runtimes?limit=100")
            assert status == 200
            assert [item["name"] for item in runtimes["data"]] == [
                "cursor",
                "command",
                "claude-code",
                "qwen-code",
                "codex",
            ]
            by_name = {item["name"]: item["default"] for item in runtimes["data"]}
            assert by_name["codex"] is True
            assert not any(v for k, v in by_name.items() if k != "codex")

            status, _, _ = _request(port, "DELETE", f"/v1/agents/sessions/{session_id}")
            assert status == 200
            status, missing, headers = _request(port, "GET", f"/v1/agents/sessions/{session_id}")
            assert status == 404
            assert missing["error"]["type"] == "not_found_error"
            assert headers.get("x-should-retry") == "false"
        finally:
            httpd.shutdown()

    def test_bearer_token(self, workspace: str) -> None:
        _enable()
        port = _find_free_port()
        httpd = _start_server(port, auth_token="test-token")
        try:
            body = {"adapter": "codex", "environment": {"workspace_directory": workspace}}
            status, _, _ = _request(port, "POST", "/v1/agents/sessions", body)
            assert status == 401
            status, created, _ = _request(
                port,
                "POST",
                "/v1/agents/sessions",
                body,
                headers={"Authorization": "Bearer test-token"},
            )
            assert status == 200, created
        finally:
            httpd.shutdown()
