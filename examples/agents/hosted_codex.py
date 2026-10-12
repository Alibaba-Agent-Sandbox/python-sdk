#!/usr/bin/env python3
"""OpenAI-shaped client for a hosted Codex session.

This file does not start a server and does not read a model API key. Point it
at a server that already has the ``agents`` group enabled (port 9000 in the
template)::

    python hosted_codex.py http://127.0.0.1:9000

The base URL may also come from ``EBX_TEMPLATE_URL``. When ``EBX_SERVER_TOKEN``
is set it is sent as ``Authorization: Bearer``, which the agents routes accept.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


def origin() -> str:
    """Server origin from argv or ``EBX_TEMPLATE_URL`` (no ``/v1`` suffix)."""
    raw = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else ""
    if not raw:
        raw = os.environ.get("EBX_TEMPLATE_URL", "").strip()
    if not raw:
        sys.exit("pass the base URL as argv[1] or set EBX_TEMPLATE_URL")
    raw = raw.rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[:-3]
    return raw


def call(
    base: str, method: str, path: str, body: dict | None = None, *, accept: str = "application/json"
) -> tuple[int, object]:
    """One JSON call. Non-2xx responses are returned, not raised."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("Accept", accept)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    token = os.environ.get("EBX_SERVER_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: object = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed


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


def main() -> None:
    base = origin()
    status, created = call(
        base,
        "POST",
        "/v1/agents/sessions",
        {"agent": {"model": "codex", "instructions": "Be brief."}},
    )
    print(f"--- POST /v1/agents/sessions ({status})")
    print(json.dumps(created, indent=2))
    if status != 200 or not isinstance(created, dict):
        sys.exit(1)
    session_id = str(created["id"])

    status, acked = call(
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
                            "content": [{"type": "input_text", "text": "Say hello from Codex."}],
                        }
                    ],
                }
            ]
        },
    )
    print(f"--- POST /v1/agents/sessions/{{id}}/events ({status})")
    print(repr(acked))
    if status != 202:
        sys.exit(1)

    deadline = time.time() + 60
    items: object = {}
    while time.time() < deadline:
        status, items = call(
            base, "GET", f"/v1/agents/sessions/{session_id}/items?limit=100&order=asc"
        )
        if status == 200 and _texts(items):
            break
        time.sleep(0.3)
    print(f"--- GET /v1/agents/sessions/{{id}}/items ({status})")
    print(json.dumps(items, indent=2))
    if not _texts(items):
        sys.exit(1)


if __name__ == "__main__":
    main()
