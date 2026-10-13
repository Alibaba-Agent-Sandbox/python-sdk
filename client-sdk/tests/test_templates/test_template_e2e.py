"""End-to-end test for the ``python-hello`` fixture template.

The full catalog (10 templates) has its own end-to-end suite in the
single-source-of-truth repository ``alibaba-agent-sandbox/awesome-templates``
(``tests/test_commands_e2e.py``).  This copy only keeps one minimal
fixture — ``examples/templates/python-hello/`` — so the sandbox HTTP server
integration (import, discovery, dispatch, built-in routes) stays covered
fully offline in this repository.

Each test verifies:

1. **Import** — ``commands.py`` loads without errors, commands register into
   a ``CommandRegistry`` instance.
2. **Server startup** — ``/health`` returns ``200 {"status": "ok"}``.
3. **Command discovery** — ``GET /commands`` lists expected command names with
   arg schemas.
4. **Command invocation** — ``POST /commands/{name}`` dispatches correctly.
5. **Built-in routes** — ``/upload`` + ``/download`` roundtrip, ``/shell``
   echo test.
"""

from __future__ import annotations

import base64
import http.client
import importlib.util
import json
import os
import socket
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("agent_sandbox.server", reason="needs the agent-sandbox-server distribution")

if TYPE_CHECKING:
    from collections.abc import Generator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_TEMPLATES_DIR = os.path.join(_PROJECT_ROOT, "examples", "templates")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _find_free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http_get(port: int, path: str, timeout: float = 5.0) -> tuple[int, dict[str, Any]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = json.loads(resp.read())
        return resp.status, body
    finally:
        conn.close()


def _http_post(
    port: int, path: str, body: dict[str, Any], timeout: float = 15.0
) -> tuple[int, dict[str, Any]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        payload = json.dumps(body).encode()
        conn.request(
            "POST",
            path,
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        data = json.loads(resp.read())
        return resp.status, data
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Server lifecycle context manager
# ---------------------------------------------------------------------------


@contextmanager
def _template_server(template_name: str, base_dir: str) -> Generator[int, None, None]:
    """Load a template's ``commands.py``, start the sandbox HTTP server on a
    random port, yield the port, then shut down and restore global state."""
    from agent_sandbox.server import SandboxServer, default_registry, default_table

    # --- 1. Save & clean global state ---
    registry = default_registry()
    saved_commands = dict(registry._commands)
    saved_frozen = registry._frozen
    saved_base_dir = os.environ.get("ABX_SERVER_BASE_DIR")

    registry._commands.clear()
    registry._frozen = False
    default_table().clear_group_overrides()
    os.environ["ABX_SERVER_BASE_DIR"] = base_dir

    # --- 2. Import commands.py (its server start is behind ``__main__``) ---
    template_dir = os.path.join(_TEMPLATES_DIR, template_name)
    commands_path = os.path.join(template_dir, "commands.py")
    module_name = f"_e2e_{template_name.replace('-', '_')}_commands"

    spec = importlib.util.spec_from_file_location(module_name, commands_path)
    assert spec is not None and spec.loader is not None, (
        f"Cannot create module spec for {commands_path}"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules.pop(module_name, None)

    # --- 3. Start server on a random port ---
    port = _find_free_port()
    server = SandboxServer(host="127.0.0.1", registry=registry)
    thread = threading.Thread(target=lambda: server.serve(port=port), daemon=True)
    thread.start()

    # --- 4. Wait for /health ---
    deadline = time.monotonic() + 3.0
    ready = False
    while time.monotonic() < deadline:
        try:
            status, _ = _http_get(port, "/health", timeout=1.0)
            if status == 200:
                ready = True
                break
        except Exception:
            time.sleep(0.05)
    if not ready:
        raise RuntimeError(f"Server for '{template_name}' failed to start on port {port}")

    try:
        yield port
    finally:
        # --- 5. Shutdown & restore ---
        server.shutdown()
        thread.join(timeout=2.0)

        registry._commands.clear()
        registry._commands.update(saved_commands)
        registry._frozen = saved_frozen
        default_table().clear_group_overrides()
        if saved_base_dir is not None:
            os.environ["ABX_SERVER_BASE_DIR"] = saved_base_dir
        else:
            os.environ.pop("ABX_SERVER_BASE_DIR", None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def base_dir() -> Generator[str, None, None]:
    """Temporary directory used as ``ABX_SERVER_BASE_DIR``."""
    with tempfile.TemporaryDirectory(prefix="abx_e2e_") as d:
        yield d


# ---------------------------------------------------------------------------
# Shared assertion helpers
# ---------------------------------------------------------------------------


def _assert_health(port: int) -> None:
    status, body = _http_get(port, "/health")
    assert status == 200
    assert body == {"status": "ok"}


def _assert_commands_registered(port: int, expected: list[str]) -> None:
    status, body = _http_get(port, "/commands")
    assert status == 200
    names = [c["name"] for c in body["commands"]]
    for cmd_name in expected:
        assert cmd_name in names, f"Command {cmd_name!r} not found; got {names}"
    # Verify each command exposes an args schema
    for cmd in body["commands"]:
        assert isinstance(cmd.get("args"), list)


def _assert_upload_download_roundtrip(port: int, base_dir: str) -> None:
    test_data = b"E2E roundtrip payload \xc0\xff"
    content_b64 = base64.b64encode(test_data).decode()
    file_path = os.path.join(base_dir, "e2e_roundtrip.bin")

    status, body = _http_post(port, "/upload", {"path": file_path, "content_base64": content_b64})
    assert status == 200, f"Upload failed: {body}"
    assert body["bytes"] == len(test_data)

    status, body = _http_get(port, f"/download?path={file_path}")
    assert status == 200, f"Download failed: {body}"
    assert base64.b64decode(body["content_base64"]) == test_data


def _assert_shell(port: int) -> None:
    status, body = _http_post(port, "/shell", {"command": "echo hello"})
    assert status == 200, f"Shell failed: {body}"
    assert body["exit_code"] == 0
    assert "hello" in body["stdout"]


# =========================================================================
# Fixture-template E2E test
# =========================================================================


def test_python_hello_e2e(base_dir: str) -> None:
    """python-hello fixture: full E2E — hello + run_script + built-in routes."""
    with _template_server("python-hello", base_dir) as port:
        _assert_health(port)
        _assert_commands_registered(port, ["hello", "run_script"])

        # hello — explicit argument
        status, body = _http_post(port, "/commands/hello", {"name": "Alice"})
        assert status == 200
        assert body["result"] == "Hello, Alice!"

        # hello — default argument
        status, body = _http_post(port, "/commands/hello", {})
        assert status == 200
        assert body["result"] == "Hello, World!"

        # run_script
        status, body = _http_post(port, "/commands/run_script", {"code": "print(1+1)"})
        assert status == 200
        assert "2" in body["result"]

        # hidden command: callable, not listed
        status, body = _http_post(port, "/commands/_debug_info", {})
        assert status == 200 and "python" in body["result"]
        _, listing = _http_get(port, "/commands")
        assert "_debug_info" not in [c["name"] for c in listing["commands"]]

        # custom route and the opt-in group the template enables in code
        status, body = _http_get(port, "/hello/Bob")
        assert status == 200 and body == {"greeting": "Hello, Bob!"}
        _, caps = _http_get(port, "/capabilities")
        assert caps["groups"]["dev_tools"] is True and caps["groups"]["browser"] is False

        # Built-in routes
        _assert_upload_download_roundtrip(port, base_dir)
        _assert_shell(port)
