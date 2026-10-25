"""Create a sandbox, run a command, read the result, then kill it.

This process starts ``python -m agent_sandbox.server serve`` on 127.0.0.1, talks to it
with ``ServerClient``, and prints every response. It does not call route handlers
in-process and does not use a cloud API key.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

from agent_sandbox.api.server_client import ServerClient


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    work = Path("/tmp/abx-agent-loop")
    base = work / "base"
    base.mkdir(parents=True, exist_ok=True)
    port = _port()
    env = os.environ.copy()
    for name in (
        "ABX_SERVER_TOKEN",
        "ABX_SERVER_POLICY",
        "ABX_SERVER_POLICY_FILE",
        "ABX_SANDBOX_API_KEY",
        "E2B_API_KEY",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    ):
        env.pop(name, None)
    env["ABX_SERVER_BASE_DIR"] = str(base)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agent_sandbox.server",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(work),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    client = ServerClient(f"http://127.0.0.1:{port}", timeout=10)
    try:
        for _ in range(80):
            try:
                if client.health_sync():
                    break
            except Exception:
                pass
            if proc.poll() is not None:
                log = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
                print(log)
                return 1
        else:
            print("server did not become healthy")
            return 1

        print("step 1  create")
        print(f"  server  http://127.0.0.1:{port}")
        print(f"  health  {client.health_sync()}")

        print("step 2  exec")
        ran = client.process.shell_sync("python3 -c 'print(2 + 2)'")
        print(f"  exit    {ran.exit_code}")
        print(f"  stdout  {ran.stdout!r}")
        print(f"  stderr  {ran.stderr!r}")

        print("step 3  read result")
        target = base / "result.txt"
        uploaded = client.files.upload_sync(str(target), "answer=4\n")
        text = client.files.read_text_sync(str(target))
        print(f"  wrote   {uploaded.path} ({uploaded.size} bytes)")
        print(f"  read    {text!r}")

        print("step 4  kill")
        os.killpg(proc.pid, signal.SIGTERM)
        code = proc.wait(timeout=5)
        print(f"  signal  SIGTERM")
        print(f"  return  {code}")
        return 0 if ran.exit_code == 0 and text == "answer=4\n" else 1
    finally:
        client.aclose_sync()
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
