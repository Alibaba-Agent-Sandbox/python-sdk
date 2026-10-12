"""Subprocess end-to-end coverage for the agents WebSocket and ``POST /v1/files``.

Starts ``python -m easy_sandbox.server serve`` on ``127.0.0.1`` and talks to it
from this process. Handlers are never called in-process.
"""

from __future__ import annotations

import base64
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from websockets.sync.client import connect

TOKEN = "test-token"
SDK_ROOT = Path(__file__).resolve().parents[1]
SERVER_SRC = SDK_ROOT / "server-sdk" / "src"
BOUNDARY = "----ebxTestBoundary7MA4YWxkTrZu0gW"
PAYLOAD = b"\x00\x01binary\r\nline2\r\n--not-a-boundary\xff\xfe" + bytes(range(32))

CODEX_SCRIPT = """#!/bin/sh
cat >/dev/null
printf '%s\\n' '{"type":"thread.started","thread_id":"thr-ws-1"}'
printf '%s\\n' '{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"ws-ok"}}'
printf '%s\\n' '{"type":"turn.completed","usage":{"input_tokens":3,"output_tokens":2}}'
exit 0
"""


class Live:
    """Base URL of the subprocess server."""

    def __init__(self, base: str, port: int) -> None:
        self.base = base
        self.port = port


def _detail(status: int, raw: bytes) -> str:
    return f"status={status} body={raw.decode('utf-8', 'replace')}"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ready(base: str, proc: subprocess.Popen[bytes], log: Path) -> None:
    deadline = time.monotonic() + 20
    last = "no response"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
            raise RuntimeError(f"server exited {proc.returncode}: {text}")
        try:
            with urllib.request.urlopen(base + "/health", timeout=1) as resp:
                if resp.status == 200:
                    return
                last = f"health status={resp.status}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = str(exc)
        time.sleep(0.1)
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    raise RuntimeError(f"server did not become ready ({last}): {text}")


@pytest.fixture(scope="module")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Real ``python -m easy_sandbox.server serve`` on an ephemeral port."""
    root = tmp_path_factory.mktemp("agents-transport-e2e")
    bindir = root / "bin"
    bindir.mkdir()
    codex = bindir / "codex"
    codex.write_text(CODEX_SCRIPT)
    codex.chmod(0o755)
    responses = root / "responses"
    responses.mkdir()
    port = _free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SERVER_SRC)
    env["EBX_SERVER_ENABLED_GROUPS"] = "agents"
    env["EBX_SERVER_TOKEN"] = TOKEN
    env["EBX_SERVER_DISABLED_GROUPS"] = "terminal"
    env["EBX_AGENTS_PERSIST"] = "0"
    env["EBX_AGENTS_RESPONSES_WORKSPACE"] = str(responses)
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    env.pop("EBX_SERVER_POLICY", None)
    env.pop("EBX_SERVER_POLICY_FILE", None)
    log = root / "server.log"
    log_fh = log.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "easy_sandbox.server",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(SDK_ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_ready(base, proc, log)
        yield Live(base, port)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
        log_fh.close()


def _request(
    live: Live,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    token: bool = True,
) -> tuple[int, bytes, Any]:
    req_headers = dict(headers or {})
    if token:
        req_headers["X-Access-Token"] = TOKEN
    request = urllib.request.Request(
        live.base + path, data=body, headers=req_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers


def _json(status: int, raw: bytes) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pytest.fail(_detail(status, raw))


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


def _recv_until(conn: Any, until: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while True:
        event = json.loads(conn.recv(timeout=30))
        events.append(event)
        if event.get("type") in (until, "error"):
            return events


def _completed(events: list[dict[str, Any]], label: str) -> dict[str, Any]:
    dumped = json.dumps(events)
    assert events, f"{label} status=ws body={dumped}"
    assert events[0].get("type") == "response.created", f"{label} status=ws body={dumped}"
    assert events[-1].get("type") == "response.completed", f"{label} status=ws body={dumped}"
    response = events[-1]["response"]
    assert response["status"] == "completed", f"{label} status=ws body={dumped}"
    delta = next(
        (event for event in events if event.get("type") == "response.output_text.delta"),
        None,
    )
    assert delta is not None and delta.get("delta") == "ws-ok", f"{label} status=ws body={dumped}"
    return response


def _raw_upgrade_without_token(port: int) -> tuple[int, bytes]:
    request = (
        "GET /v1/responses HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "\r\n"
    ).encode()
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(request)
        sock.settimeout(5)
        chunks: list[bytes] = []
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        except TimeoutError:
            pass
    raw = b"".join(chunks)
    head, _, body = raw.partition(b"\r\n\r\n")
    line = head.split(b"\r\n", 1)[0]
    parts = line.split(b" ")
    status = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    return status, body if body else raw


def _bytes_for_file_id(live: Live, file_id: str, workspace: Path) -> bytes:
    """Ask the server to materialize *file_id* and read the bytes it wrote."""
    workspace.mkdir()
    status, raw, _headers = _request(
        live,
        "POST",
        "/v1/agents/environments",
        body=json.dumps(
            {
                "environment": {
                    "type": "self_hosted",
                    "workspace_directory": str(workspace),
                    "files": [
                        {
                            "type": "file_id",
                            "file_id": file_id,
                            "path": "/workspace/blob.bin",
                        }
                    ],
                }
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    assert status == 200, _detail(status, raw)
    path = workspace / "blob.bin"
    assert path.is_file(), f"file id {file_id} was not written; {_detail(status, raw)}"
    return path.read_bytes()


def test_responses_websocket_create_and_queued_steer(live_server: Live) -> None:
    status, raw, _headers = _request(live_server, "GET", "/v1/responses")
    body = _json(status, raw)
    assert status == 400, _detail(status, raw)
    assert body["error"]["code"] == "agents.websocket_upgrade_required", _detail(status, raw)

    status, raw, _headers = _request(live_server, "GET", "/v1/responses", token=False)
    assert status == 401, _detail(status, raw)

    status, raw = _raw_upgrade_without_token(live_server.port)
    assert status == 401, _detail(status, raw)

    url = f"ws://127.0.0.1:{live_server.port}/v1/responses"
    with connect(
        url,
        additional_headers={"X-Access-Token": TOKEN},
        open_timeout=10,
        proxy=None,
    ) as conn:
        conn.send(json.dumps({"type": "response.create", "model": "codex", "input": "hi"}))
        created = _completed(_recv_until(conn, "response.completed"), "response.create")
        conn.send(
            json.dumps(
                {
                    "type": "response.steer",
                    "model": "codex",
                    "input": "again",
                    "previous_response_id": created["id"],
                }
            )
        )
        steered = _completed(_recv_until(conn, "response.completed"), "response.steer")
        assert steered["previous_response_id"] == created["id"], json.dumps(steered)
        assert "queued_steer" in steered["x_easy_sandbox"]["differences"], json.dumps(steered)


def test_files_multipart_and_json_base64_round_trip(live_server: Live, tmp_path: Path) -> None:
    status, raw, headers = _request(
        live_server,
        "POST",
        "/v1/files",
        body=multipart({"purpose": "user_data"}, "report.bin", PAYLOAD),
        headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
    )
    assert status == 200, _detail(status, raw)
    assert headers.get("X-Easy-Sandbox-Local") == "1", _detail(status, raw)
    created = _json(status, raw)
    assert created["object"] == "file", _detail(status, raw)
    assert created["bytes"] == len(PAYLOAD), _detail(status, raw)
    assert _bytes_for_file_id(live_server, created["id"], tmp_path / "multipart") == PAYLOAD, (
        _detail(status, raw)
    )

    encoded = base64.b64encode(PAYLOAD).decode("ascii")
    status, raw, headers = _request(
        live_server,
        "POST",
        "/v1/files",
        body=json.dumps(
            {"purpose": "user_data", "filename": "report.bin", "data": encoded}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    assert status == 200, _detail(status, raw)
    assert headers.get("X-Easy-Sandbox-Local") == "1", _detail(status, raw)
    created = _json(status, raw)
    assert created["bytes"] == len(PAYLOAD), _detail(status, raw)
    assert _bytes_for_file_id(live_server, created["id"], tmp_path / "json") == PAYLOAD, _detail(
        status, raw
    )
