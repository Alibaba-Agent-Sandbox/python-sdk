#!/usr/bin/env python3
"""Local check of the Agents API template.

The server must already be running with ``E2E_RUN_LLM=0`` so ``e2e-bin`` is
on ``PATH``. No model API key is read or sent.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:9000").rstrip("/")


def call(method: str, path: str, body: dict | None = None) -> tuple[int, object, dict[str, str]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(BASE + path, data=data, method=method)
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
        headers = {k.lower(): v for k, v in exc.headers.items()}
        try:
            parsed: object = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed, headers


def texts(payload: object) -> list[str]:
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


def expect(title: str, status: int, want: int, payload: object) -> None:
    print(f"[{'ok' if status == want else 'fail'}] {title} ({status})")
    if status != want:
        print(json.dumps(payload, ensure_ascii=False)[:500])
        raise SystemExit(1)


def turn(adapter: str, needle: str) -> None:
    status, created, headers = call(
        "POST",
        "/v1/agents/sessions",
        {"agent": {"model": adapter}},
    )
    expect(f"POST session {adapter}", status, 200, created)
    if headers.get("x-easy-sandbox-local") != "1":
        print("missing X-Easy-Sandbox-Local")
        raise SystemExit(1)
    if not isinstance(created, dict) or "id" not in created:
        print(created)
        raise SystemExit(1)
    session_id = str(created["id"])
    status, acked, _headers = call(
        "POST",
        f"/v1/agents/sessions/{session_id}/events",
        {
            "events": [
                {
                    "type": "agent.session.input.message",
                    "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
                }
            ]
        },
    )
    expect(f"POST events {adapter}", status, 202, acked)
    deadline = time.time() + 20
    items: object = {}
    status = 0
    while time.time() < deadline:
        status, items, _headers = call(
            "GET", f"/v1/agents/sessions/{session_id}/items?limit=100&order=asc"
        )
        if status == 200 and needle in texts(items):
            print(f"[ok] items {adapter} contains {needle}")
            return
        time.sleep(0.2)
    print(f"[fail] items {adapter} missing {needle} ({status})")
    print(json.dumps(items, ensure_ascii=False)[:800])
    raise SystemExit(1)


def main() -> int:
    status, health, _headers = call("GET", "/health")
    expect("GET /health", status, 200, health)

    status, shell, _headers = call("POST", "/shell", {"command": "echo no"})
    expect("POST /shell stays closed", status, 404, shell)

    status, definitions, _headers = call("POST", "/v1/agents", {"model": "codex"})
    expect("POST /v1/agents stays closed", status, 404, definitions)

    status, missing, _headers = call("POST", "/v1/agents/sessions", {"agent": {"model": "gpt-5"}})
    expect("omitted adapter uses the first runtime", status, 200, missing)
    agent = missing.get("agent") if isinstance(missing, dict) else None
    if not isinstance(agent, dict) or agent.get("id") != "codex" or agent.get("model") != "gpt-5":
        print(missing)
        raise SystemExit(1)

    status, refused, _headers = call(
        "POST",
        "/v1/agents/sessions",
        {"adapter": "claude-code", "agent": {"model": "gpt-5"}},
    )
    expect("claude-code is not in this slice", status, 404, refused)

    turn("codex", "hello-from-fake-codex")
    turn("qwen-code", "hello-from-fake-qwen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
