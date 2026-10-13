"""Client SDK ``Sandbox.run`` (named command) 全链路 E2E 测试.

启动一个真实 :class:`SandboxServer` (本地 HTTP)，然后通过
:meth:`Sandbox.run` 的 **实际 httpx 客户端路径** 进行往返调用。
覆盖：typed 参数强转、错误传递、PEP 563 注解回归。

Tests use the same fixture pattern as ``test_server_e2e.py``.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from unittest.mock import MagicMock

import httpx
import pytest

from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.api.server_client import ServerClient

pytest.importorskip("agent_sandbox.server", reason="needs the agent-sandbox-server distribution")

from agent_sandbox.server import CommandRegistry, SandboxServer  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Commands (some defined under PEP 563 — this file uses
# ``from __future__ import annotations``)
# ---------------------------------------------------------------------------


def hello(who: str) -> str:
    return f"Hello, {who}!"


def add(a: int, b: int) -> int:
    return a + b


def multiply(x: float, y: float) -> float:
    return x * y


def toggle(flag: bool) -> bool:
    return not flag


def failing() -> str:
    raise ValueError("intentional boom")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def local_server(tmp_path):
    """Start a real SandboxServer and return ``(port, registry)``."""
    registry = CommandRegistry()

    # Use the @registry.command() decorator so annotation inference runs
    # (this also validates PEP 563 handling in registry.command).
    registry.command("hello")(hello)
    registry.command("add")(add)
    registry.command("multiply")(multiply)
    registry.command("toggle")(toggle)
    registry.command("failing")(failing)

    port = _free_port()
    server = SandboxServer(host="127.0.0.1", registry=registry)

    os.environ["ABX_SERVER_BASE_DIR"] = str(tmp_path)
    t = threading.Thread(target=server.serve, kwargs={"port": port}, daemon=True)
    t.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(40):
        try:
            with httpx.Client() as c:
                r = c.get(f"{base_url}/health", timeout=2)
                if r.status_code == 200:
                    break
        except Exception:
            time.sleep(0.05)
    else:
        pytest.fail("Server did not start within 2 seconds")

    yield port, registry

    server.shutdown()
    os.environ.pop("ABX_SERVER_BASE_DIR", None)


@pytest.fixture()
async def sandbox_stub(local_server):
    """A Sandbox-like object whose ``run`` talks to the local server through a real ServerClient."""
    port, _ = local_server
    client = ServerClient(f"http://127.0.0.1:{port}", timeout=10)

    sb = MagicMock(spec=Sandbox)
    sb.server = client
    sb._info = MagicMock(envd_url=f"http://127.0.0.1:{port}")
    sb._require_data_plane = lambda feature: None
    sb.run = Sandbox.run.__get__(sb, Sandbox)

    yield sb

    await client.aclose()


# ---------------------------------------------------------------------------
# Tests — run full-round-trip via real HTTP
# ---------------------------------------------------------------------------


class TestRunCommandE2E:
    """Client SDK ``Sandbox.run`` via real HTTP to a real SandboxServer."""

    @pytest.mark.asyncio
    async def test_hello_returns_greeting(self, sandbox_stub):
        result = await sandbox_stub.run("hello", who="World")
        assert result == "Hello, World!"

    @pytest.mark.asyncio
    async def test_add_returns_integer(self, sandbox_stub):
        result = await sandbox_stub.run("add", a=2, b=40)
        assert result == 42
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_add_string_coercion(self, sandbox_stub):
        """String '2' and '40' should be coerced to int on the server side."""
        result = await sandbox_stub.run("add", a="2", b="40")
        assert result == 42
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_multiply_float_coercion(self, sandbox_stub):
        result = await sandbox_stub.run("multiply", x="3.5", y="2.0")
        assert result == 7.0
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_toggle_bool_coercion(self, sandbox_stub):
        result = await sandbox_stub.run("toggle", flag="false")
        assert result is True

    @pytest.mark.asyncio
    async def test_unknown_command_raises_command_not_found(self, sandbox_stub):
        from agent_sandbox.models.errors import CommandNotFoundError

        with pytest.raises(CommandNotFoundError, match="not found"):
            await sandbox_stub.run("nonexistent")

    @pytest.mark.asyncio
    async def test_handler_exception_raises_server_api_error(self, sandbox_stub):
        from agent_sandbox.models.errors import ServerAPIError

        with pytest.raises(ServerAPIError, match="intentional boom"):
            await sandbox_stub.run("failing")


# ---------------------------------------------------------------------------
# PEP 563 regression — annotations in this file are ALL stringified
# because of ``from __future__ import annotations`` at the top.
# The ``@registry.command()`` decorator must resolve them correctly.
# ---------------------------------------------------------------------------


class TestPEP563ServerCoercion:
    """Verify PEP 563 string annotations → real types for server commands.

    All functions (``hello``, ``add``, ``multiply``, ``toggle``) are
    defined under ``from __future__ import annotations``.  If annotation
    resolution fails, int/float/bool args would be treated as string and
    coercion would break or produce wrong results.
    """

    @pytest.mark.asyncio
    async def test_int_params_coerced(self, sandbox_stub):
        """``add(a: int, b: int)`` — verify int coercion under PEP 563."""
        result = await sandbox_stub.run("add", a="10", b="32")
        assert result == 42

    @pytest.mark.asyncio
    async def test_float_params_coerced(self, sandbox_stub):
        result = await sandbox_stub.run("multiply", x="2.5", y="4.0")
        assert result == 10.0

    @pytest.mark.asyncio
    async def test_bool_param_coerced(self, sandbox_stub):
        result = await sandbox_stub.run("toggle", flag="true")
        assert result is False

    @pytest.mark.asyncio
    async def test_str_param_unchanged(self, sandbox_stub):
        result = await sandbox_stub.run("hello", who="PEP563")
        assert result == "Hello, PEP563!"
