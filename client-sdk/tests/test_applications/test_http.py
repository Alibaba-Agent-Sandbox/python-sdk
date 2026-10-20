"""Real subprocess/HTTP/local server integration; no cloud isolation is implied."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from agent_sandbox.applications import ApplicationClient, sign_invocation


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.integration)])
def application_database_url(request, tmp_path):
    """Run the same real HTTP roles against each supported database without containers."""
    if request.param == "sqlite":
        yield "sqlite:///" + str(tmp_path / "state.db")
        return
    pgserver = pytest.importorskip("pgserver", reason="Optional PostgreSQL binary is unavailable")
    pytest.importorskip("psycopg")
    server = pgserver.get_server(tmp_path / "postgres", cleanup_mode="stop")
    try:
        yield server.get_uri()
    finally:
        server.cleanup()


def test_three_process_http_remote_tools_and_restart(tmp_path, application_database_url):
    """Gateway acceptance survives restart; real worker drives remote server file APIs."""
    token = "local-business-token-placeholder-" + "x" * 32
    internal = "local-internal-token-placeholder-" + "y" * 32
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "tokens": [
                    {
                        "sha256": hashlib.sha256(token.encode()).hexdigest(),
                        "owner": "local-owner",
                        "revisions": ["local-revision"],
                        "scopes": ["runs:read", "runs:write"],
                    }
                ]
            }
        )
    )
    ports = {role: free_port() for role in ("gateway", "worker", "dispatcher")}
    urls = {role: f"http://127.0.0.1:{port}" for role, port in ports.items()}
    env = {
        **os.environ,
        "ABX_APP_FACTORY": "local_factory:factory",
        "ABX_APP_BIND": "127.0.0.1",
        "ABX_APP_AUTH_FILE": str(auth),
        "ABX_APP_INTERNAL_TOKEN": internal,
        "ABX_APP_DATABASE_URL": application_database_url,
        "ABX_LOCAL_WORKSPACE": str(tmp_path),
        "ABX_LOCAL_WORKER_URL": urls["worker"],
        "PYTHONPATH": str(Path(__file__).parent / "fixtures"),
    }
    processes = []

    def start(role):
        process = subprocess.Popen(
            [sys.executable, "-m", "agent_sandbox.applications", role],
            env={**env, "ABX_APP_PORT": str(ports[role])},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(process)
        for _ in range(150):
            try:
                if httpx.get(urls[role] + "/healthz", timeout=0.2).status_code == 200:
                    return process
            except httpx.HTTPError:
                pass
            if process.poll() is not None:
                pytest.fail("Application subprocess exited before readiness")
            time.sleep(0.05)
        pytest.fail("Application subprocess did not become ready")

    try:
        gateway = start("gateway")
        headers = {"Authorization": "Bearer " + token, "Idempotency-Key": "request-1"}
        body = {
            "applicationRevision": "local-revision",
            "input": {"text": "hello remote filesystem"},
        }
        response = httpx.post(urls["gateway"] + "/v1/agent-runs", headers=headers, json=body)
        assert response.status_code == 202
        run_id = response.json()["id"]
        gateway.terminate()
        gateway.wait(timeout=10)
        start("gateway")
        repeat = httpx.post(urls["gateway"] + "/v1/agent-runs", headers=headers, json=body)
        assert repeat.status_code == 202 and repeat.json()["id"] == run_id
        assert httpx.get(urls["gateway"] + "/v1/agent-runs/" + run_id).status_code == 401
        start("worker")
        start("dispatcher")
        assert httpx.post(urls["worker"] + "/invoke", json={"runId": run_id}).status_code == 401
        dispatched = httpx.post(
            urls["dispatcher"] + "/invoke",
            json={
                "triggerTime": "2026-10-20T00:00:00Z",
                "triggerName": "dispatcher",
                "payload": json.dumps(sign_invocation({}, internal, role="dispatcher")),
            },
            timeout=30,
        )
        assert dispatched.status_code == 200 and dispatched.json()["dispatched"] == 1

        async def inspect():
            async with ApplicationClient(urls["gateway"], token) as client:
                state = await client.get(run_id)
                assert state.status == "succeeded"
                result = await client.result(run_id)
                assert result.output_text == "remote file completed"
                assert (
                    await client.artifact(run_id, result.artifacts[0].id)
                    == b"hello remote filesystem"
                )
                events = [event async for event in client.events(run_id)]
                assert events[0].type == "run.accepted" and events[-1].type == "run.completed"
                assert [e.seq for e in events] == list(range(1, len(events) + 1))
                assert (await client.cancel(run_id)).status == "succeeded"
                replay = [event async for event in client.events(run_id, after=events[-2].seq)]
                assert len(replay) == 1 and replay[0].seq == events[-1].seq

        asyncio.run(inspect())
        assert (tmp_path / run_id / "answer.txt").read_text() == "hello remote filesystem"
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
