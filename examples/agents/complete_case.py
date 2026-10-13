#!/usr/bin/env python3
"""Complete Agents API case: Codex and Qwen Code, no model key.

This is not ``sb.agent.*``. That name is a different design (sugar over
``commands.run()``). This script talks to the sandbox HTTP Agents API.

The image does not contain the CLIs. This case writes two stand-in programs
named ``codex`` and ``qwen`` and puts them on ``PATH``. A real deployment
installs only the one it calls:

    npm install -g @openai/codex
    npm install -g @qwen-code/qwen-code

Nothing in this file reads or sends a model API key.

    python examples/agents/complete_case.py
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

_FAKE_CODEX = """#!/bin/sh
cat >/dev/null
printf '%s\\n' '{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"hello-from-fake-codex"}}'
printf '%s\\n' '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}'
exit 0
"""

_FAKE_QWEN = """#!/bin/sh
printf '%s\\n' '{"type":"assistant","message":{"id":"m1","content":[{"type":"text","text":"hello-from-fake-qwen"}]}}'
printf '%s\\n' '{"type":"result","subtype":"success"}'
exit 0
"""


def _server_src() -> None:
    root = Path(__file__).resolve().parents[2]
    src = root / "server-sdk" / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _write_cli(directory: Path, name: str, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / name
    script.write_text(body)
    script.chmod(0o755)


def call(base: str, method: str, path: str, body: dict | None = None) -> tuple[int, object, dict[str, str]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, json.loads(raw) if raw else {}, headers
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        headers = {key.lower(): value for key, value in exc.headers.items()}
        try:
            parsed: object = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed, headers


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


def _show(title: str, status: int, payload: object, headers: dict[str, str]) -> None:
    print(f"\n--- {title} ({status})")
    print("X-Easy-Sandbox-Local:", headers.get("x-easy-sandbox-local", ""))
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:1200])
    else:
        print(payload)


def _expect(status: int, want: int, title: str) -> None:
    if status != want:
        sys.exit(f"{title}: expected {want}, got {status}")


def _turn(base: str, adapter: str, needle: str) -> None:
    status, created, headers = call(base, "POST", "/v1/agents/sessions", {"agent": {"model": adapter}})
    _show(f"POST /v1/agents/sessions model={adapter}", status, created, headers)
    _expect(status, 200, "create session")
    if headers.get("x-easy-sandbox-local") != "1":
        sys.exit("missing X-Easy-Sandbox-Local")
    if not isinstance(created, dict) or "id" not in created:
        sys.exit("session has no id")
    session_id = str(created["id"])
    status, acked, headers = call(
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
                            "content": [{"type": "input_text", "text": f"Say hello from {adapter}."}],
                        }
                    ],
                }
            ]
        },
    )
    _show("POST /v1/agents/sessions/{id}/events", status, acked, headers)
    _expect(status, 202, "enqueue turn")
    deadline = time.time() + 20
    items: object = {}
    item_headers: dict[str, str] = {}
    while time.time() < deadline:
        status, items, item_headers = call(
            base, "GET", f"/v1/agents/sessions/{session_id}/items?limit=100&order=asc"
        )
        if status == 200 and needle in _texts(items):
            break
        time.sleep(0.2)
    _show("GET /v1/agents/sessions/{id}/items", status, items, item_headers)
    if needle not in _texts(items):
        sys.exit(f"items for {adapter} did not contain {needle}")
    print(f"case ok: {adapter} -> {needle}")


def main() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="ebx-agents-case-"))
    bin_dir = workspace / "bin"
    _write_cli(bin_dir, "codex", _FAKE_CODEX)
    _write_cli(bin_dir, "qwen", _FAKE_QWEN)
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    os.environ["EBX_SERVER_BASE_DIR"] = str(workspace / "files")
    (workspace / "files").mkdir()
    os.environ["EBX_SERVER_ENABLED_GROUPS"] = "agents"
    os.environ["EBX_AGENTS_PERSIST"] = "0"
    os.environ.pop("EBX_SERVER_TOKEN", None)
    os.environ.pop("EBX_AGENTS_DEFAULT", None)
    _server_src()
    from easy_sandbox.server.app import SandboxServer
    from easy_sandbox.server.router import CapabilityGroup

    server = SandboxServer(host="127.0.0.1")
    server.route_table.disable_group(CapabilityGroup.TERMINAL)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    threading.Thread(target=server.serve, args=(port,), daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 5
    while time.time() < deadline:
        status, _payload, _headers = call(base, "GET", "/health")
        if status == 200:
            break
        time.sleep(0.05)
    else:
        sys.exit("server did not become healthy")
    print(f"server {base}")
    print("CLIs on PATH: codex, qwen (stand-ins; no model key)")

    status, missing, headers = call(base, "POST", "/v1/agents/sessions", {"agent": {"model": "gpt-5"}})
    _show("POST session without an adapter name", status, missing, headers)
    _expect(status, 400, "adapter required")

    status, refused, headers = call(
        base,
        "POST",
        "/v1/agents/sessions",
        {"adapter": "claude-code", "agent": {"model": "gpt-5"}},
    )
    _show("POST session adapter=claude-code", status, refused, headers)
    _expect(status, 404, "claude-code")

    status, runtimes, headers = call(base, "GET", "/v1/agents/runtimes")
    _show("GET /v1/agents/runtimes", status, runtimes, headers)
    _expect(status, 200, "runtimes")

    _turn(base, "codex", "hello-from-fake-codex")
    _turn(base, "qwen-code", "hello-from-fake-qwen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
