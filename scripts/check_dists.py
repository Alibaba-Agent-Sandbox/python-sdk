#!/usr/bin/env python3
"""Verify the built ``client-sdk`` / ``server-sdk`` distributions.

Expects ``python -m build --outdir dist/client-sdk client-sdk`` and
``python -m build --outdir dist/server-sdk server-sdk`` to have been run from the
repository root (``make build``).

Checks:

* ``py-typed`` — each wheel ships its PEP 561 marker
  (``agent_sandbox/py.typed`` for the client, ``agent_sandbox/server/py.typed`` for the server).
* ``combined-install`` — install the client alone, exercise HTTP without the runtime,
  then resolve the local server extra and verify command registration.

Usage: ``python scripts/check_dists.py [py-typed|combined-install|all]``
"""

from __future__ import annotations

import glob
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

PY_TYPED_MARKERS = {
    "client-sdk": "agent_sandbox/py.typed",
    "server-sdk": "agent_sandbox/server/py.typed",
}

CLIENT_CHECK = """
import asyncio
import importlib.metadata
import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml
from agent_sandbox import Sandbox, AsyncSandbox, ProviderSandbox, sandbox
from agent_sandbox.api import launch_template
from agent_sandbox.api.server_client import ServerClient
from agent_sandbox.code_interpreter import Sandbox as InterpreterSandbox
from agent_sandbox.code_interpreter import AsyncSandbox as AsyncInterpreterSandbox

classes = (Sandbox, AsyncSandbox, ProviderSandbox, InterpreterSandbox, AsyncInterpreterSandbox)
assert all(callable(cls.create) for cls in classes)
assert callable(launch_template) and callable(sandbox)
assert not hasattr(sandbox, "run") and not hasattr(sandbox, "run_async")
assert yaml.safe_load("spec_version: 5") == {"spec_version": 5}
assert importlib.util.find_spec("agent_sandbox.server") is None
try:
    importlib.metadata.distribution("agent-sandbox-server")
except importlib.metadata.PackageNotFoundError:
    pass
else:
    raise AssertionError("base install pulled in the server runtime")

def identity(value: str) -> str:
    return value

assert callable(sandbox(template="code-interpreter-v1")(identity))

try:
    sandbox.register(identity)
except ImportError as exc:
    assert "agent-sandbox-client[server]" in str(exc)
else:
    raise AssertionError("registration without the runtime silently succeeded")
assert sandbox.list_registered() == []

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        assert self.path == "/health"
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever)
thread.start()
async def check_http():
    client = ServerClient(f"http://127.0.0.1:{server.server_port}")
    try:
        assert await client.health()
    finally:
        await client.aclose()
try:
    asyncio.run(check_http())
finally:
    server.shutdown()
    server.server_close()
    thread.join()
print("client-only imports, explicit runtime error, and real HTTP: OK")
"""

SERVER_CHECK = """
from agent_sandbox import sandbox
from agent_sandbox.server import default_registry, start

@sandbox.register
def identity(value: str) -> str:
    return value

assert callable(start)
assert identity("registered") == "registered"
assert any(command["name"] == "identity" for command in sandbox.list_registered())
assert default_registry().get("identity") is not None
print("server extra namespace and command registration: OK")
"""


def _wheel(package: str) -> Path:
    wheels = sorted(glob.glob(str(DIST / package / "*.whl")))
    if len(wheels) != 1:
        raise SystemExit(f"expected exactly one wheel in dist/{package}, found {wheels}")
    return Path(wheels[0])


def check_py_typed() -> None:
    failed = False
    for package, marker in PY_TYPED_MARKERS.items():
        wheel = _wheel(package)
        with zipfile.ZipFile(wheel) as zf:
            names = zf.namelist()
        if marker in names:
            print(f"py.typed found in {wheel.name}: OK ({marker})")
        else:
            print(f"{marker} NOT found in {wheel}", file=sys.stderr)
            failed = True
    if failed:
        raise SystemExit(1)


def check_combined_install() -> None:
    server, client = _wheel("server-sdk"), _wheel("client-sdk")
    with tempfile.TemporaryDirectory(prefix="agent-sandbox-combined-") as tmp:
        venv = Path(tmp) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        bindir = "Scripts" if sys.platform == "win32" else "bin"
        python = venv / bindir / ("python.exe" if sys.platform == "win32" else "python")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", str(client)],
            check=True,
        )
        # Run outside the repo so the installed wheels, not the source trees, are imported.
        subprocess.run([str(python), "-c", CLIENT_CHECK], check=True, cwd=tmp)
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--quiet",
                "--no-index",
                "--find-links",
                str(server.parent),
                f"{client}[server]",
            ],
            check=True,
        )
        subprocess.run([str(python), "-c", SERVER_CHECK], check=True, cwd=tmp)
        subprocess.run([str(python), "-m", "pip", "check"], check=True, cwd=tmp)
    print("client-only and optional server wheel installation: OK")


def main(argv: list[str]) -> int:
    what = argv[1] if len(argv) > 1 else "all"
    if what not in {"py-typed", "combined-install", "all"}:
        print(__doc__, file=sys.stderr)
        return 2
    if what in {"py-typed", "all"}:
        check_py_typed()
    if what in {"combined-install", "all"}:
        check_combined_install()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
