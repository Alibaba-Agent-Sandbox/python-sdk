"""Process OS users must reach envd without changing shared authentication."""

from __future__ import annotations

import asyncio
import base64
import json
import struct

import httpx
import pytest

from agent_sandbox.providers.alicloud_express.auth import ApiKeyAuth
from agent_sandbox.providers.shared.e2b.auth import EnvdTokenManager
from agent_sandbox.providers.shared.e2b.process import ProcessProtocol
from agent_sandbox.transport.config import TransportConfig
from agent_sandbox.transport.http import HttpClient


def _frame(payload: dict) -> bytes:
    body = json.dumps(payload).encode()
    return struct.pack(">BI", 0, len(body)) + body


@pytest.mark.parametrize("default_user", ["user", "root"])
async def test_concurrent_process_users_preserve_gateway_and_default_auth(httpx_mock, default_user):
    """Inspect real HttpClient wire requests, including interleaved stream consumption."""
    token = EnvdTokenManager(
        "placeholder-envd-token", "placeholder-sandbox", basic_user=default_user
    )
    original_headers = token.get_headers()
    seen = []

    async def respond(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0)
        principal = base64.b64decode(request.headers["Authorization"].split()[1]).decode()
        assert principal.endswith(":")
        assert request.headers["X-Access-Token"] == "placeholder-envd-token"
        assert request.headers["E2b-Sandbox-Id"] == "placeholder-sandbox"
        assert request.headers["E2b-Sandbox-Port"] == "49983"
        payload = json.loads(request.content[5:])
        assert payload["process"] == {"cmd": "id", "args": ["-u"]}
        assert payload["stdin"] is False
        seen.append(principal)
        return httpx.Response(
            200,
            content=_frame(
                {"event": {"data": {"stdout": base64.b64encode(principal.encode()).decode()}}}
            )
            + _frame({"event": {"end": {"exitCode": 0}}}),
        )

    httpx_mock.add_callback(respond, is_reusable=True)
    http = HttpClient(
        config=TransportConfig(sandbox_base_url="https://platform.example.test", http2=False),
        auth=ApiKeyAuth("placeholder-control-plane-key"),
    )
    protocol = ProcessProtocol(http)

    async def run(user: str) -> str:
        reader = await protocol.start(
            "https://envd.example.test", token, cmd="id", args=["-u"], user=user
        )
        return "".join([chunk.data or "" async for chunk in reader])

    try:
        assert await asyncio.gather(run("root"), run("user"), run("")) == [
            "root:",
            "user:",
            f"{default_user}:",
        ]
        assert await run("") == f"{default_user}:"
        assert token.get_headers() == original_headers
        assert len(seen) == 4
    finally:
        await http.close()


@pytest.mark.parametrize("user", ["root:password", "root\n", "root\r", "root\x00"])
async def test_invalid_basic_principal_fails_before_any_request(httpx_mock, user):
    httpx_mock.add_response(content=_frame({"event": {"end": {"exitCode": 0}}}), is_optional=True)
    http = HttpClient(
        config=TransportConfig(sandbox_base_url="https://platform.example.test", http2=False),
        auth=ApiKeyAuth("placeholder-control-plane-key"),
    )
    try:
        with pytest.raises(ValueError, match="user"):
            reader = await ProcessProtocol(http).start(
                "https://envd.example.test",
                EnvdTokenManager("placeholder-token"),
                cmd="id",
                user=user,
            )
            async for _ in reader:
                pass
        assert httpx_mock.get_requests() == []
    finally:
        await http.close()
