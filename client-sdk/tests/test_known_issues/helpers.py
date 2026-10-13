"""Wire-level helpers for the KI-xxx regression tests.

The tests drive the real ``HttpClient`` + protocol classes against ``pytest-httpx`` so the
exact request bodies and the raw envd responses (shapes captured from a real sandbox, see
``python-sdk/e2e/KNOWN-ISSUES.md``) are what is asserted, not a mock of our own layers.
"""

from __future__ import annotations

import base64
import json
import struct
from typing import Any

from agent_sandbox.transport.auth import ApiKeyAuth, EnvdTokenManager
from agent_sandbox.transport.config import TransportConfig
from agent_sandbox.transport.http import HttpClient

API = "https://api.sandbox-test.example.com"
ENVD = "https://49983-sbx-ki.sandbox-test.example.com"


def make_http(api_key: str = "test-key") -> HttpClient:
    return HttpClient(TransportConfig(sandbox_base_url=API, http2=False), ApiKeyAuth(api_key))


def token() -> EnvdTokenManager:
    return EnvdTokenManager("envd-token")


def frame(payload: dict[str, Any], flags: int = 0x00) -> bytes:
    body = json.dumps(payload).encode()
    return struct.pack(">BI", flags, len(body)) + body


def stdout_event(text: str) -> dict[str, Any]:
    return {"event": {"data": {"stdout": base64.b64encode(text.encode()).decode()}}}


def start_event(pid: int) -> dict[str, Any]:
    return {"event": {"start": {"pid": pid}}}


def end_event(code: int = 0) -> dict[str, Any]:
    return {"event": {"end": {"exitCode": code, "exited": True, "status": "exited"}}}


def process_stream(*events: dict[str, Any]) -> bytes:
    return b"".join(frame(e) for e in events) + frame({}, flags=0x02)


def body_of(request: Any) -> dict[str, Any]:
    return json.loads(request.content)  # type: ignore[no-any-return]
