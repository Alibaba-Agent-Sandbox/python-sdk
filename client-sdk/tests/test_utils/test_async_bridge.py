"""Tests for async/sync bridging utilities."""

from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agent_sandbox import ProviderSandbox
from agent_sandbox.models.sandbox import SandboxInfo
from agent_sandbox.providers.shared.e2b.sandbox import SandboxProtocol
from agent_sandbox.transport.auth_contract import ApiKeyAuth, SessionAuth
from agent_sandbox.transport.config import TransportConfig
from agent_sandbox.transport.http import HttpClient
from agent_sandbox.utils.async_bridge import make_sync, run_sync


class TestRunSync:
    def test_executes_coroutine(self):
        async def greet():
            return "hello"

        result = run_sync(greet())
        assert result == "hello"

    def test_propagates_exception(self):
        async def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            run_sync(fail())

    def test_returns_correct_type(self):
        async def compute():
            return 42

        result = run_sync(compute())
        assert result == 42
        assert isinstance(result, int)


class TestMakeSync:
    def test_creates_sync_wrapper(self):
        async def async_method(x: int) -> int:
            return x * 2

        sync_method = make_sync(async_method)
        result = sync_method(5)
        assert result == 10

    def test_has_sync_wrapper_attribute(self):
        async def async_method():
            return "ok"

        sync_method = make_sync(async_method)
        assert hasattr(sync_method, "_is_sync_wrapper")
        assert sync_method._is_sync_wrapper is True

    def test_preserves_function_name(self):
        async def my_function():
            return "ok"

        sync_fn = make_sync(my_function)
        assert sync_fn.__name__ == "my_function"

    def test_propagates_exception(self):
        async def fail():
            raise RuntimeError("nope")

        sync_fn = make_sync(fail)
        with pytest.raises(RuntimeError, match="nope"):
            sync_fn()


@pytest.mark.parametrize("inside_async", [False, True])
def test_sync_sandbox_reuses_http_connection_and_closes(inside_async):
    connections = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            connections.append(self.connection)
            data = json.dumps({"sandboxID": "sync-test", "status": "running"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    config = TransportConfig(sandbox_base_url=url, http2=False)
    auth = ApiKeyAuth("placeholder")
    http = HttpClient(config, auth)
    sandbox = ProviderSandbox(
        SandboxInfo(sandbox_id="sync-test", envd_url=url),
        config,
        http,
        auth,
        SessionAuth("placeholder", "sync-test"),
        sandbox_protocol=SandboxProtocol(http),
        process_protocol=object(),
        filesystem_protocol=object(),
        code_interpreter_protocol=object(),
    )

    def check():
        try:
            assert sandbox.refresh_info_sync().sandbox_id == "sync-test"
            assert sandbox.refresh_info_sync().sandbox_id == "sync-test"
            assert len(connections) == 2
            assert connections[0] is connections[1]
        finally:
            sandbox.close_sync()

    async def check_inside_async():
        check()

    try:
        if inside_async:
            asyncio.run(check_inside_async())
        else:
            check()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_concurrent_sync_calls_share_one_loop():
    async def current_loop():
        await asyncio.sleep(0)
        return asyncio.get_running_loop()

    with ThreadPoolExecutor(max_workers=4) as pool:
        loops = list(pool.map(lambda _: run_sync(current_loop()), range(12)))
    assert all(loop is loops[0] for loop in loops)


def test_nested_sync_callback_fails_without_deadlocking():
    async def nested():
        return run_sync(asyncio.sleep(0))

    with pytest.raises(RuntimeError, match="synchronous SDK callback"):
        run_sync(nested())
