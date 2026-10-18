"""Binary transfer behavior with local HTTP streams and fake sandbox delegates."""

from __future__ import annotations

import base64
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from agent_sandbox.agent.binary_files import MAX_FILE_BYTES
from agent_sandbox.agent.mcp import _STDIO_READ_LIMIT, SandboxMCPServer
from agent_sandbox.agent.tools import dispatch_tool
from agent_sandbox.api.files import FilesModule
from agent_sandbox.models.errors import FileSizeLimitError
from agent_sandbox.protocol.filesystem import FilesystemProtocol
from agent_sandbox.transport.auth import ApiKeyAuth, EnvdTokenManager
from agent_sandbox.transport.config import TransportConfig
from agent_sandbox.transport.http import HttpClient


def manager():
    files = SimpleNamespace(write=AsyncMock(), read_bytes=AsyncMock())
    owner = SimpleNamespace(get_sandbox=AsyncMock(return_value=SimpleNamespace(files=files)))
    return owner, files


@pytest.mark.parametrize("data", [b"", bytes(range(256)) * 4096], ids=["empty", "max-binary"])
async def test_byte_exact_upload_download_and_maximum_json_frame(data):
    owner, files = manager()
    encoded = base64.b64encode(data).decode()
    files.read_bytes.return_value = data
    server = SandboxMCPServer()
    server._manager = owner
    upload = {
        "name": "upload_file",
        "arguments": {"path": "/tmp/artifact", "content_base64": encoded},
    }
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": upload}
    assert len(json.dumps(request).encode()) + 1 < _STDIO_READ_LIMIT
    reply = await server.handle_request(request)
    assert not reply["result"]["isError"]
    files.write.assert_awaited_once_with("/tmp/artifact", data)
    request["params"] = {
        "name": "download_file",
        "arguments": {"path": "/tmp/artifact", "sandbox_id": "owned"},
    }
    reply = await server.handle_request(request)
    assert not reply["result"]["isError"]
    result = json.loads(reply["result"]["content"][0]["text"])
    assert result == {
        "content_base64": encoded,
        "bytes_read": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    assert len(json.dumps(reply).encode()) + 1 < _STDIO_READ_LIMIT
    files.read_bytes.assert_awaited_once_with("/tmp/artifact", max_bytes=MAX_FILE_BYTES)
    owner.get_sandbox.assert_awaited_with("owned")


@pytest.mark.parametrize(
    "extra",
    [
        {"content_base64": "@bad"},
        {"content_base64": "\u2603"},
        {"content_base64": "A" * 1398105},
        {"content_base64": base64.b64encode(b"x" * (MAX_FILE_BYTES + 1)).decode()},
        {"path": "../host"},
        {"path": "/tmp/../secret"},
        {"path": "/tmp/\0bad"},
        {"path": "/" + "\u2603" * 4096},
        {"sandbox_id": True},
        {"sandbox_id": None},
        {"host_path": "/etc/secret"},
    ],
    ids=[
        "bad-base64",
        "unicode",
        "encoded-limit",
        "decoded-limit",
        "relative",
        "traversal",
        "nul",
        "path-bytes",
        "sandbox-type",
        "sandbox-null",
        "unknown",
    ],
)
async def test_upload_invalid_before_any_remote_effect(extra):
    owner, files = manager()
    args = {"path": "/tmp/data", "content_base64": "eA=="} | extra
    result = await dispatch_tool("upload_file", args, owner)
    assert result["error_category"] == "invalid_input"
    owner.get_sandbox.assert_not_awaited()
    files.write.assert_not_awaited()


async def test_download_errors_have_no_raw_upstream_details(caplog):
    owner, files = manager()
    files.read_bytes.side_effect = RuntimeError("synthetic-private-file-contents-or-token")
    result = await dispatch_tool("download_file", {"path": "/tmp/file"}, owner)
    assert result["error_category"] == "file_transfer"
    assert "synthetic-private" not in json.dumps(result) + caplog.text
    files.read_bytes.side_effect = FileSizeLimitError(MAX_FILE_BYTES)
    result = await dispatch_tool("download_file", {"path": "/tmp/file"}, owner)
    assert result["error_category"] == "size_limit" and "content_base64" not in result


class ByteStream(httpx.AsyncByteStream):
    def __init__(self, *, fail=False):
        self.closed = False
        self.count = 0
        self.fail = fail

    async def __aiter__(self):
        for _ in range(100):
            self.count += 1
            yield b"\0\xff" * 32768
            if self.fail:
                raise httpx.ReadError("synthetic private upstream detail")

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("limit", [0, 70000, MAX_FILE_BYTES])
async def test_real_streamed_limit_ignores_missing_or_false_content_length(limit):
    stream = ByteStream()
    client = HttpClient(TransportConfig(), ApiKeyAuth("placeholder"))
    transport = httpx.AsyncClient(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=stream, headers={"content-length": "0"})
        ),
    )
    client._envd_clients["https://example.invalid"] = transport
    fs = FilesModule(
        "https://example.invalid", EnvdTokenManager("placeholder"), FilesystemProtocol(client)
    )
    try:
        with pytest.raises(FileSizeLimitError) as exc:
            await fs.read_bytes("/dev/zero", max_bytes=limit)
        assert exc.value.limit == limit
        assert stream.closed and stream.count <= limit // 65536 + 1
    finally:
        await client.close()


async def test_stream_failure_closes_response_and_default_read_remains_compatible():
    stream = ByteStream(fail=True)
    client = HttpClient(TransportConfig(), ApiKeyAuth("placeholder"))
    transport = httpx.AsyncClient(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)),
    )
    client._envd_clients["https://example.invalid"] = transport
    fs = FilesModule(
        "https://example.invalid", EnvdTokenManager("placeholder"), FilesystemProtocol(client)
    )
    try:
        with pytest.raises(httpx.ReadError):
            await fs.read_bytes("/tmp/file", max_bytes=MAX_FILE_BYTES)
        assert stream.closed
    finally:
        await client.close()
    protocol = AsyncMock()
    protocol.read.return_value = b"\0\xff"
    fs = FilesModule("url", EnvdTokenManager("placeholder"), protocol)
    assert await fs.read_bytes("/tmp/file") == b"\0\xff"
    protocol.read.assert_awaited_once_with("url", fs._envd_token, path="/tmp/file")


def test_maximum_binary_payload_through_real_stdio_process():
    """Real framing, fake file delegate: this proves transport capacity, not cloud."""
    import os
    import subprocess
    import sys

    from .test_mcp_stdio import _readline, _send, _stop

    code = """
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from agent_sandbox.agent.mcp import SandboxMCPServer
stored = b''
async def write(path, data):
    global stored
    stored = data
async def read(path, **kwargs):
    return stored
server = SandboxMCPServer()
server._manager = SimpleNamespace(get_sandbox=AsyncMock(return_value=SimpleNamespace(
    files=SimpleNamespace(write=write,read_bytes=read))), shutdown=AsyncMock())
asyncio.run(server.run())
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )
    data = bytes(range(256)) * 4096
    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "upload_file",
                    "arguments": {
                        "path": "/tmp/binary",
                        "content_base64": base64.b64encode(data).decode(),
                    },
                },
            },
        )
        uploaded = _readline(proc)
        assert not uploaded["result"]["isError"]
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "download_file", "arguments": {"path": "/tmp/binary"}},
            },
        )
        downloaded = _readline(proc)
        assert not downloaded["result"]["isError"]
        result = json.loads(downloaded["result"]["content"][0]["text"])
        assert base64.b64decode(result["content_base64"]) == data
    finally:
        _stop(proc)


def test_maximum_binary_payload_through_http_session():
    from starlette.testclient import TestClient

    from agent_sandbox.agent.mcp_http import create_mcp_app

    app = create_mcp_app(auth_token="placeholder")
    data = bytes(range(256)) * 4096
    owner, files = manager()
    owner.shutdown = AsyncMock()
    files.read_bytes.return_value = data
    with TestClient(app) as client:
        initialized = client.post(
            "/mcp",
            headers={"Authorization": "Bearer placeholder"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
        )
        session_id = initialized.headers["Mcp-Session-Id"]
        app.state.session_store.get_session(session_id)._manager = owner
        headers = {"Authorization": "Bearer placeholder", "Mcp-Session-Id": session_id}
        uploaded = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "upload_file",
                    "arguments": {
                        "path": "/tmp/binary",
                        "content_base64": base64.b64encode(data).decode(),
                    },
                },
            },
        )
        assert not uploaded.json()["result"]["isError"]
        downloaded = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "download_file", "arguments": {"path": "/tmp/binary"}},
            },
        )
        assert not downloaded.json()["result"]["isError"]
        result = json.loads(downloaded.json()["result"]["content"][0]["text"])
        assert base64.b64decode(result["content_base64"]) == data
    files.write.assert_awaited_once_with("/tmp/binary", data)


@pytest.mark.parametrize("status", [403, 404, 500])
async def test_bounded_stream_http_error_closes_without_reading_body(status):
    from agent_sandbox.models.errors import (
        FileNotFoundError_,
        FileOperationError,
        PermissionDeniedError,
    )

    stream = ByteStream()
    client = HttpClient(TransportConfig(), ApiKeyAuth("placeholder"))
    client._envd_clients["https://example.invalid"] = httpx.AsyncClient(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(lambda request: httpx.Response(status, stream=stream)),
    )
    fs = FilesModule(
        "https://example.invalid", EnvdTokenManager("placeholder"), FilesystemProtocol(client)
    )
    try:
        with pytest.raises(
            {403: PermissionDeniedError, 404: FileNotFoundError_, 500: FileOperationError}[status]
        ):
            await fs.read_bytes("/tmp/missing", max_bytes=MAX_FILE_BYTES)
        assert stream.closed and stream.count == 0
    finally:
        await client.close()


@pytest.mark.parametrize("tool", ["upload_file", "download_file"])
async def test_binary_file_tools_preserve_explicit_external_adoption_and_shutdown(
    tool, monkeypatch
):
    from agent_sandbox.agent.mcp import SandboxManager

    files = SimpleNamespace(write=AsyncMock(), read_bytes=AsyncMock(return_value=b"x"))
    sandbox = SimpleNamespace(
        id="external", files=files, set_timeout=AsyncMock(), kill=AsyncMock(), close=AsyncMock()
    )
    monkeypatch.setattr(
        "agent_sandbox.api.sandbox.Sandbox.connect", AsyncMock(return_value=sandbox)
    )
    owner = SandboxManager()
    args = {"path": "/tmp/file", "sandbox_id": "external"}
    if tool == "upload_file":
        args["content_base64"] = "eA=="
    result = await dispatch_tool(tool, args, owner)
    assert "error" not in result and owner._sandboxes["external"] is sandbox
    await owner.shutdown()
    sandbox.kill.assert_awaited_once()


async def test_encoded_size_rejection_precedes_base64_allocation(monkeypatch):
    from agent_sandbox.agent import binary_files

    def should_not_decode(*args, **kwargs):
        raise AssertionError("oversized input must not reach the decoder")

    monkeypatch.setattr(binary_files.base64, "b64decode", should_not_decode)
    owner, _ = manager()
    result = await dispatch_tool(
        "upload_file",
        {"path": "/tmp/file", "content_base64": "A" * (binary_files.MAX_BASE64_CHARS + 1)},
        owner,
    )
    assert result["error_category"] == "invalid_input"
    owner.get_sandbox.assert_not_awaited()


async def test_cancelled_download_closes_stream():
    import asyncio

    started = asyncio.Event()

    class WaitingStream(ByteStream):
        async def __aiter__(self):
            started.set()
            await asyncio.Event().wait()
            yield b"unreachable"

    stream = WaitingStream()
    client = HttpClient(TransportConfig(), ApiKeyAuth("placeholder"))
    client._envd_clients["https://example.invalid"] = httpx.AsyncClient(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)),
    )
    fs = FilesModule(
        "https://example.invalid", EnvdTokenManager("placeholder"), FilesystemProtocol(client)
    )
    task = asyncio.create_task(fs.read_bytes("/tmp/file", max_bytes=MAX_FILE_BYTES))
    try:
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stream.closed
    finally:
        await client.close()


async def test_node_provider_bounded_read_never_falls_back_to_unlimited_download():
    from agent_sandbox.models.errors import ProviderFeatureNotSupportedError
    from agent_sandbox.providers.engine_provider import EngineFilesystemProtocol

    client = SimpleNamespace(request=AsyncMock())
    protocol = EngineFilesystemProtocol(client, "example", frozenset({"files.rw"}))
    with pytest.raises(ProviderFeatureNotSupportedError):
        await protocol.read(
            "engine://example/owned",
            EnvdTokenManager("placeholder"),
            path="/tmp/file",
            max_bytes=MAX_FILE_BYTES,
        )
    client.request.assert_not_awaited()


@pytest.mark.parametrize("limit", [True, -1, "1"], ids=["bool", "negative", "string"])
async def test_invalid_sdk_byte_limits_fail_before_http_creation(limit):
    client = HttpClient(TransportConfig(), ApiKeyAuth("placeholder"))
    fs = FilesModule(
        "https://example.invalid", EnvdTokenManager("placeholder"), FilesystemProtocol(client)
    )
    with pytest.raises(ValueError):
        await fs.read_bytes("/tmp/file", max_bytes=limit)
    assert not client._envd_clients


@pytest.mark.parametrize("encoding", ["gzip", "br", "deflate", "gzip, identity"])
async def test_bounded_download_requests_identity_and_rejects_encoded_body_before_read(encoding):
    from agent_sandbox.models.errors import FileOperationError

    stream = ByteStream()
    requests = []

    def response(request):
        requests.append(request)
        return httpx.Response(200, stream=stream, headers={"content-encoding": encoding})

    client = HttpClient(TransportConfig(), ApiKeyAuth("placeholder"))
    client._envd_clients["https://example.invalid"] = httpx.AsyncClient(
        base_url="https://example.invalid", transport=httpx.MockTransport(response)
    )
    try:
        with pytest.raises(FileOperationError):
            await client.envd_http_request(
                "https://example.invalid",
                "GET",
                "/files",
                envd_token=EnvdTokenManager("placeholder"),
                max_response_bytes=MAX_FILE_BYTES,
                headers={"accept-encoding": "gzip"},
            )
        assert requests[0].headers["accept-encoding"] == "identity"
        assert stream.count == 0 and stream.closed
    finally:
        await client.close()


async def test_default_download_still_decodes_gzip_but_bounded_materialized_headers_match_bytes():
    import gzip

    body = b"\0\xffgzip-compatible"

    async def response(request):
        if request.headers.get("accept-encoding") == "identity":
            return httpx.Response(
                200,
                stream=httpx.ByteStream(body),
                headers={"content-encoding": "identity", "content-length": str(len(body))},
            )
        return httpx.Response(
            200, content=gzip.compress(body), headers={"content-encoding": "gzip"}
        )

    client = HttpClient(TransportConfig(), ApiKeyAuth("placeholder"))
    client._envd_clients["https://example.invalid"] = httpx.AsyncClient(
        base_url="https://example.invalid", transport=httpx.MockTransport(response)
    )
    try:
        token = EnvdTokenManager("placeholder")
        default = await client.envd_http_request(
            "https://example.invalid", "GET", "/files", envd_token=token
        )
        assert default.content == body
        bounded = await client.envd_http_request(
            "https://example.invalid",
            "GET",
            "/files",
            envd_token=token,
            max_response_bytes=MAX_FILE_BYTES,
        )
        assert bounded.content == body
        assert "content-encoding" not in bounded.headers
        assert int(bounded.headers["content-length"]) == len(body)
    finally:
        await client.close()


async def test_tool_timeout_category_includes_python310_asyncio_timeout():
    import asyncio

    owner, files = manager()
    files.read_bytes.side_effect = asyncio.TimeoutError()
    result = await dispatch_tool("download_file", {"path": "/tmp/file"}, owner)
    assert result["error_category"] == "timeout" and "content_base64" not in result
