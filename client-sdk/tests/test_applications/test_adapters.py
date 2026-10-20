"""Optional delivery adapter shape, authentication and configuration regressions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import threading
from types import SimpleNamespace

import pytest

from agent_sandbox.applications.config import FileAuthenticator, application_from_env


@pytest.mark.asyncio
async def test_in_sandbox_required_endpoints_match_real_core_discovery(monkeypatch):
    from agent_sandbox.server import CommandRegistry, SandboxServer

    from agent_sandbox.api.server_client import ServerClient
    from agent_sandbox.applications import InSandboxAgentExecutor

    token = "local-core-token-placeholder-" + "x" * 32
    monkeypatch.setenv("ABX_SERVER_TOKEN", token)
    server = SandboxServer(
        host="127.0.0.1", pty_port=0, policy={"groups": ["agents"]}, registry=CommandRegistry()
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    thread = threading.Thread(target=server.serve, args=(port,), daemon=True)
    thread.start()
    client = ServerClient(f"http://127.0.0.1:{port}", token=token)
    try:
        for _ in range(100):
            try:
                discovery = await client.discover()
                break
            except Exception:
                await asyncio.sleep(0.01)
        else:
            pytest.fail("Core sandbox server discovery did not become ready")
        assert all(
            discovery.can(endpoint) for endpoint in InSandboxAgentExecutor.required_endpoints
        )
        assert not discovery.can("agents_events_create")
    finally:
        await client.aclose()
        server.shutdown()
        thread.join(timeout=5)


def test_file_auth_reload_revocation_and_scopes(tmp_path):
    path = tmp_path / "auth.json"
    token = "business-placeholder-" + "x" * 32
    path.write_text(
        json.dumps(
            {
                "tokens": [
                    {
                        "sha256": hashlib.sha256(token.encode()).hexdigest(),
                        "owner": "team",
                        "revisions": ["revision"],
                        "scopes": ["runs:read"],
                    }
                ]
            }
        )
    )
    authenticate = FileAuthenticator(str(path))
    assert authenticate(token).scopes == frozenset({"runs:read"})
    assert authenticate("wrong") is None
    path.write_text('{"tokens":[]}')
    assert authenticate(token) is None
    path.write_text("broken")
    assert authenticate(token) is None


def test_cli_packaged_single_template_spec_snapshot(monkeypatch):
    monkeypatch.setenv(
        "ABX_APP_SPEC_JSON",
        json.dumps(
            {
                "name": "app",
                "runtime": {"placement": "external", "driver": "python-remote-tools"},
                "sandbox": {
                    "provider": "alicloud-express",
                    "lifetime": "per-run",
                    "workspace": "exclusive",
                },
                "state": {"profile": "durable", "bindingRef": "state"},
                "bindings": {"model": "model-ref"},
                "limits": {"maxToolSeconds": 10, "maxOutputBytes": 8388608},
            }
        ),
    )
    monkeypatch.setenv("ABX_APP_SANDBOX_TEMPLATE", "prepared-ref")
    monkeypatch.setenv("ABX_APP_SANDBOX_PROVIDER", "alicloud-express")
    monkeypatch.setenv("ABX_APP_REVISION", "plan-digest")
    monkeypatch.setenv("ABX_APP_MODEL", "model-v1")
    monkeypatch.setenv("ABX_APP_MODEL_ENDPOINT", "https://model.example.com/v1/chat/completions")
    app = application_from_env()
    assert app.snapshot["sandbox"]["template"] == "prepared-ref"
    assert app.max_tool_seconds == 10
    assert app.execution_snapshot()["limits"]["outputBytes"] == 8388608
    assert app.snapshot["model"]["name"] == "model-v1"
    assert app.snapshot["model"]["endpoint"] == "https://model.example.com/v1/chat/completions"
    snapshot = app.execution_snapshot()
    monkeypatch.setenv("ABX_APP_MODEL_ENDPOINT", "https://other.example.com/v1/chat/completions")
    assert application_from_env().execution_snapshot() != snapshot


def test_signed_fc_sender_uses_official_sdk_payload_and_async_task_id():
    pytest.importorskip("alibabacloud_fc20230330")
    from agent_sandbox.applications.fc import FCTaskSender

    calls = []

    class Client:
        def invoke_function_with_options(self, function, request, headers, options):
            calls.append(
                (function, json.loads(request.body.read()), headers.to_map(), options.to_map())
            )
            return SimpleNamespace(status_code=202)

    private = "private-invoke-placeholder-" + "z" * 32
    sender = FCTaskSender("example.cn-hangzhou.fc.aliyuncs.com", "worker", private, client=Client())
    sender({"runId": "run_example"})
    function, payload, headers, options = calls[0]
    assert function == "worker"
    from agent_sandbox.applications import verify_invocation

    assert verify_invocation(payload, private, role="worker") == {"runId": "run_example"}
    assert headers["x-fc-invocation-type"] == "Async"
    assert headers["x-fc-async-task-id"] == "run_example"
    assert "commonHeaders" not in headers or not headers["commonHeaders"]
    assert options["autoretry"] is False


def test_body_invocation_signature_tamper_role_and_timer_wrapper():
    from agent_sandbox.applications import ApplicationError, sign_invocation, verify_invocation

    token = "local-hmac-placeholder-" + "x" * 32
    signed = sign_invocation({"runId": "run_example"}, token, role="worker")
    assert token not in json.dumps(signed)
    assert verify_invocation(signed, token, role="worker") == {"runId": "run_example"}
    with pytest.raises(ApplicationError):
        verify_invocation(signed, token, role="dispatcher")
    with pytest.raises(ApplicationError):
        verify_invocation({**signed, "payload": {"runId": "run_other"}}, token, role="worker")
    dispatch = sign_invocation({"limit": 20}, token, role="dispatcher")
    wrapped = {
        "triggerTime": "2026-10-20T00:00:00Z",
        "triggerName": "dispatcher",
        "payload": json.dumps(dispatch),
    }
    assert verify_invocation(wrapped, token, role="dispatcher") == {"limit": 20}
