#!/usr/bin/env python3
"""Call a template server that is already running.

Base URL: the first argument, or the ABX_TEMPLATE_URL environment variable.
Token: ABX_SERVER_TOKEN, sent as X-Access-Token only when that variable is set.
This file does not contain a URL or a credential.

    python call_api.py http://127.0.0.1:9000
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def base_url() -> str:
    """Return the server origin from argv or ABX_TEMPLATE_URL."""
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip().rstrip("/")
    url = os.environ.get("ABX_TEMPLATE_URL", "").strip()
    if not url:
        sys.exit("pass the base URL as argv[1] or set ABX_TEMPLATE_URL")
    return url.rstrip("/")


def call(origin: str, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    """Send one JSON request. A non-2xx response is returned, not raised."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(origin + path, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    # Local mode leaves ABX_SERVER_TOKEN unset; the server then accepts every route.
    token = os.environ.get("ABX_SERVER_TOKEN")
    if token:
        request.add_header("X-Access-Token", token)
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


def show(title: str, status: int, payload: object) -> bool:
    """Print one call and report whether the status is in the 200 range."""
    print(f"--- {title} ({status})")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 200 <= status < 300


def main() -> int:
    origin = base_url()
    ok = True

    # Open even when ABX_SERVER_TOKEN is set.
    status, payload = call(origin, "GET", "/health")
    ok = show("GET /health", status, payload) and ok

    # Requires X-Access-Token when a token is configured.
    status, payload = call(origin, "GET", "/capabilities")
    ok = show("GET /capabilities", status, payload) and ok

    status, payload = call(origin, "GET", "/commands")
    ok = show("GET /commands", status, payload) and ok

    # file_ops. The path must stay under ABX_SERVER_BASE_DIR (default /home/user).
    base_dir = os.environ.get("ABX_SERVER_BASE_DIR", "/home/user").rstrip("/")
    status, payload = call(
        origin,
        "POST",
        "/files/upload-stream",
        {
            "path": f"{base_dir}/call-api.txt",
            "content_base64": base64.b64encode(b"hello\n").decode("ascii"),
        },
    )
    ok = show("POST /files/upload-stream", status, payload) and ok

    assert isinstance(payload, dict) and payload["bytes"] == len(b"hello\n")
    query = urllib.parse.urlencode({"path": f"{base_dir}/call-api.txt"})
    status, downloaded = call(origin, "GET", f"/files/download-stream?{query}")
    ok = show("GET /files/download-stream", status, downloaded) and ok
    assert isinstance(downloaded, dict)
    assert base64.b64decode(downloaded["content_base64"], validate=True) == b"hello\n"

    # process. shlex.split + shell=False, so this is a single argv, not a pipeline.
    status, payload = call(origin, "POST", "/shell", {"command": "echo hello-from-template"})
    ok = show("POST /shell", status, payload) and ok

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
