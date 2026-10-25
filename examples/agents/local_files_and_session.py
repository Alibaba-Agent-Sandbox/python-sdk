#!/usr/bin/env python3
"""Upload one file and run one Codex session against a local sandbox server.

The Codex binary is a local program, described in ``examples/agents/README.md``:
a Python executable named ``codex`` on ``PATH`` that consumes stdin and prints one
JSONL agent message plus ``turn.completed``. This file does not read or send
a model API key.

With no arguments the script starts ``SandboxServer`` on 127.0.0.1, with
``agents`` enabled and that local ``codex`` on ``PATH``. Pass a base URL to talk
to a server you already started; that process must see the same local
``codex``, and ``ABX_SERVER_ENABLED_GROUPS`` must include ``agents``.

    python local_files_and_session.py
    python local_files_and_session.py http://127.0.0.1:9000
"""

from __future__ import annotations

import base64
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_FAKE_CODEX = """#!/usr/bin/env python3
import json, sys
if "--version" in sys.argv:
    print("codex 0.162.1")
else:
    sys.stdin.read()
    print(json.dumps({"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": "hello-from-fake-codex"}}))
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}))
"""


def install_fake_codex(directory: Path) -> None:
    """Put the fake ``codex`` script on ``PATH``. No API key is written."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "codex"
    script.write_text(_FAKE_CODEX)
    script.chmod(0o755)
    os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_local(base_dir: Path, bin_dir: Path) -> str:
    """Start a local server. Returns ``http://127.0.0.1:<port>``."""
    install_fake_codex(bin_dir)
    os.environ["ABX_SERVER_BASE_DIR"] = str(base_dir)
    os.environ["ABX_SERVER_ENABLED_GROUPS"] = "agents,file_ops"
    os.environ["ABX_AGENTS_PERSIST"] = "0"
    os.environ.pop("ABX_SERVER_TOKEN", None)
    from agent_sandbox.server.app import SandboxServer
    from agent_sandbox.server.router import CapabilityGroup

    server = SandboxServer(host="127.0.0.1")
    server.route_table.disable_group(CapabilityGroup.TERMINAL)
    port = _free_port()
    thread = threading.Thread(target=server.serve, args=(port,), daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{port}"
    deadline = time.time() + 5
    while time.time() < deadline:
        status, _payload, _headers = call(origin, "GET", "/health")
        if status == 200:
            return origin
        time.sleep(0.05)
    sys.exit("local server did not answer GET /health")


def origin_from_argv() -> str | None:
    """Base URL from argv, without a ``/v1`` suffix. ``None`` means start one."""
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        return None
    raw = sys.argv[1].strip().rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[:-3]
    return raw


def call(
    base: str, method: str, path: str, body: dict | None = None
) -> tuple[int, object, dict[str, str]]:
    """One JSON call. Non-2xx responses are returned, not raised."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            headers = {k.lower(): v for k, v in response.headers.items()}
            return response.status, json.loads(raw) if raw else {}, headers
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        try:
            parsed: object = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed, headers


def show(title: str, status: int, payload: object) -> bool:
    """Print one call and report whether the status is in the 200 range."""
    print(f"--- {title} ({status})")
    if payload == "" or payload == b"":
        print("(empty body)")
    else:
        print(
            json.dumps(payload, ensure_ascii=False, indent=2)
            if not isinstance(payload, str)
            else payload
        )
    return 200 <= status < 300


def _texts(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    found: list[str] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("text"):
                found.append(str(part["text"]))
    return found


def main() -> int:
    given = origin_from_argv()
    workspace = Path(tempfile.mkdtemp(prefix="abx-agents-"))
    files = workspace / "files"
    files.mkdir()
    if given is None:
        base = start_local(files, workspace / "bin")
        print(f"local server {base}")
    else:
        base = given

    # The server this script starts uses ``files`` as ABX_SERVER_BASE_DIR.
    # A server you already started still uses the default base `/home/user`.
    upload_path = str(files / "note.txt") if given is None else "/home/user/abx-note.txt"
    payload = base64.b64encode(b"hello-from-files\n").decode("ascii")
    status, body, _headers = call(
        base,
        "POST",
        "/files/upload-stream",
        {"path": upload_path, "content_base64": payload},
    )
    ok = show("POST /files/upload-stream", status, body)
    if not ok:
        return 1

    query = urllib.parse.urlencode({"path": upload_path})
    status, body, _headers = call(base, "GET", f"/files/download-stream?{query}")
    ok = show("GET /files/download-stream", status, body) and ok

    status, created, headers = call(
        base,
        "POST",
        "/v1/agents/sessions",
        {
            "agent": {"model": "codex"},
            "environment": {
                "type": "self_hosted",
                "workspace_directory": str(workspace),
            },
        },
    )
    print(f"--- POST /v1/agents/sessions ({status})")
    print("X-Agent-Sandbox-Local:", headers.get("x-agent-sandbox-local", ""))
    print(json.dumps(created, indent=2) if isinstance(created, dict) else created)
    if status != 200 or not isinstance(created, dict) or "id" not in created:
        return 1
    session_id = str(created["id"])

    status, acked, _headers = call(
        base,
        "POST",
        f"/v1/agents/sessions/{session_id}/events",
        {
            "events": [
                {
                    "type": "agent.session.input.message",
                    "input": [
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": "Say hello."}],
                        }
                    ],
                }
            ]
        },
    )
    print(f"--- POST /v1/agents/sessions/{{id}}/events ({status})")
    print(repr(acked) if acked != {} else "(empty body)")
    if status != 202:
        return 1

    deadline = time.time() + 20
    items: object = {}
    while time.time() < deadline:
        status, items, _headers = call(
            base, "GET", f"/v1/agents/sessions/{session_id}/items?limit=20&order=asc"
        )
        if status == 200 and _texts(items):
            break
        time.sleep(0.2)
    ok = show("GET /v1/agents/sessions/{id}/items", status, items) and ok
    if "hello-from-fake-codex" not in _texts(items):
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
