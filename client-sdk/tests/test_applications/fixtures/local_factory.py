"""Trusted local verification wiring; no cloud or OS sandbox isolation is claimed."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request, urlopen

from agent_sandbox.api.server_client import ServerClient
from agent_sandbox.applications import (
    Application,
    ApplicationRuntime,
    ExternalAgentExecutor,
    Store,
    sign_invocation,
)
from agent_sandbox.applications.config import FileAuthenticator


class ScriptedToolModel:
    """Deterministic trusted model fixture which exercises actual remote file APIs."""

    def __init__(self):
        self.step = 0

    async def complete(self, messages, tools):
        self.step += 1
        if self.step == 1:
            function = {
                "name": "write_file",
                "arguments": json.dumps({"path": "answer.txt", "content": messages[1]["content"]}),
            }
        elif self.step == 2:
            function = {
                "name": "artifact",
                "arguments": json.dumps({"path": "answer.txt", "name": "answer.txt"}),
            }
        else:
            return {"role": "assistant", "content": "remote file completed"}
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": f"call-{self.step}", "type": "function", "function": function}],
        }


async def spawn_local_server(context):
    """Start the real sandbox server in a separate process, without executing generated code."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    root = Path(os.environ["ABX_LOCAL_WORKSPACE"]) / context.run_id
    root.mkdir()
    token = os.environ["ABX_APP_INTERNAL_TOKEN"]
    env = {**os.environ, "ABX_SERVER_TOKEN": token}
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agent_sandbox.server",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--pty-port",
            "0",
            "--preset",
            "transfer-only",
            "--base-dir",
            str(root),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = ServerClient(f"http://127.0.0.1:{port}", token=token)
    try:
        for _ in range(100):
            try:
                await client.discover()
                break
            except Exception:
                if process.poll() is not None:
                    raise RuntimeError("Local sandbox server exited") from None
                await asyncio.sleep(0.05)
        else:
            raise RuntimeError("Local sandbox server did not become ready")
    except BaseException:
        process.terminate()
        process.wait(timeout=10)
        await client.aclose()
        raise

    async def close():
        await client.aclose()
        process.terminate()
        process.wait(timeout=10)

    async def write(path, content):
        return await client.files.upload(str(root / Path(path).name), content)

    async def read(path):
        return await client.files.read_text(str(root / Path(path).name))

    return SimpleNamespace(
        sandbox_id=f"local-server-{process.pid}",
        files=SimpleNamespace(write=write, read=read),
        kill=close,
    )


def factory():
    """Create the same durable runtime in gateway, dispatcher and worker processes."""
    app = Application("local-revision", "external", {"model": "scripted-local-verification"})
    store = Store(os.environ["ABX_APP_DATABASE_URL"], local=True)

    def send(payload):
        request = Request(
            os.environ["ABX_LOCAL_WORKER_URL"] + "/invoke",
            data=json.dumps(
                sign_invocation(payload, os.environ["ABX_APP_INTERNAL_TOKEN"], role="worker")
            ).encode(),
            method="POST",
        )
        with contextlib.closing(urlopen(request, timeout=30)) as response:
            if response.status != 200:
                raise RuntimeError("Local task invocation failed")

    return ApplicationRuntime(
        store,
        {app.revision: app},
        lambda _: ExternalAgentExecutor(ScriptedToolModel(), spawn_local_server),
        send,
        FileAuthenticator(os.environ["ABX_APP_AUTH_FILE"]),
        heartbeat_seconds=0.1,
        cleanup_seconds=3,
    )
