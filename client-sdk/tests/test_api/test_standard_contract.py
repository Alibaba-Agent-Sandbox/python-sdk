"""Observable standard API behavior, without importing the reference SDK at runtime."""

from __future__ import annotations

import importlib.metadata
import inspect
import json
from typing import Any

import httpx
import pytest
from google.protobuf.json_format import ParseDict
from packaging.version import Version

from agent_sandbox import AsyncSandbox, CommandExitException, ConnectionConfig, Sandbox
from agent_sandbox._standard.envd.process import process_pb2
from agent_sandbox._standard.sandbox_sync.commands.command_handle import CommandHandle
from agent_sandbox.code_interpreter import Sandbox as CodeSandbox


def connected(cls: type[Any] = Sandbox) -> Any:
    return cls(
        sandbox_id="contract-id",
        sandbox_domain="example.invalid",
        envd_version=Version("0.5.2"),
        envd_access_token="placeholder-token",
        connection_config=ConnectionConfig(
            api_key="placeholder-key", api_url="https://api.example.invalid"
        ),
    )


def test_sync_async_and_default_templates() -> None:
    assert not inspect.iscoroutinefunction(Sandbox.create)
    assert inspect.iscoroutinefunction(AsyncSandbox.create)
    assert Sandbox.default_template == "base"
    assert CodeSandbox.default_template == "code-interpreter-v1"
    import agent_sandbox

    assert {"Sandbox", "AsyncSandbox", "Template", "SandboxQuery"} <= set(dir(agent_sandbox))
    assert connected().get_host(8080) == "8080-contract-id.example.invalid"


def test_owns_runtime_without_e2b_dependency() -> None:
    assert Sandbox.__module__.startswith("agent_sandbox.")
    requirements = importlib.metadata.requires("agent-sandbox-client") or []
    assert not any(req.lower().startswith(("e2b", "e2b-code-interpreter")) for req in requirements)


def test_connection_environment_and_request_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2B_API_KEY", "placeholder-key")
    monkeypatch.setenv("E2B_API_URL", "https://api.example.invalid")
    monkeypatch.setenv("E2B_DOMAIN", "example.invalid")
    config = ConnectionConfig(request_timeout=0)
    assert config.api_key == "placeholder-key"
    assert config.api_url == "https://api.example.invalid"
    assert config.domain == "example.invalid"
    assert config.request_timeout is None
    assert ConnectionConfig(api_key="explicit-placeholder").api_key == "explicit-placeholder"


def test_create_and_class_instance_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "sandboxID": "contract-id",
                    "templateID": "base",
                    "clientID": "contract",
                    "envdVersion": "0.5.2",
                    "envdAccessToken": "placeholder-token",
                    "sandboxDomain": "example.invalid",
                },
            )
        return httpx.Response(204)

    monkeypatch.setattr(
        "agent_sandbox._standard.api.client_sync.get_transport",
        lambda *_args, **_kwargs: httpx.MockTransport(respond),
    )
    sb = Sandbox.create(
        api_key="placeholder-key",
        api_url="https://api.example.invalid",
        timeout=123,
        envs={"MODE": "test"},
        metadata={"team": "test"},
    )
    assert sb.sandbox_id == "contract-id"
    assert sb.kill() is True
    assert (
        Sandbox.kill(
            "contract-id", api_key="placeholder-key", api_url="https://api.example.invalid"
        )
        is True
    )
    payload = json.loads(calls[0].content)
    assert payload["timeout"] == 123
    assert payload["envVars"] == {"MODE": "test"}
    assert payload["metadata"] == {"team": "test"}
    assert [r.method for r in calls] == ["POST", "DELETE", "DELETE"]


def test_list_is_lazy_paginator() -> None:
    paginator = Sandbox.list(api_key="placeholder-key", api_url="https://api.example.invalid")
    assert paginator.has_next
    assert callable(paginator.next_items)
    paginator_async = AsyncSandbox.list(
        api_key="placeholder-key", api_url="https://api.example.invalid"
    )
    assert not inspect.isawaitable(paginator_async)
    assert inspect.iscoroutinefunction(paginator_async.next_items)


def test_background_handle_preserves_output_and_nonzero_error() -> None:
    def events() -> Any:
        yield ParseDict({"event": {"data": {"stdout": "aGVsbG8="}}}, process_pb2.StartResponse())
        yield ParseDict({"event": {"data": {"stderr": "ZXJyb3I="}}}, process_pb2.StartResponse())
        yield ParseDict(
            {"event": {"end": {"exitCode": 7, "exited": True}}}, process_pb2.StartResponse()
        )

    handle = CommandHandle(pid=123, handle_kill=lambda: True, events=events())
    assert handle.pid == 123
    with pytest.raises(CommandExitException) as exc:
        handle.wait()
    assert exc.value.exit_code == 7
    assert exc.value.stdout == "hello"
    assert exc.value.stderr == "error"


def test_interpreter_stream_callbacks_and_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []
    output = [
        {"type": "stdout", "text": "first\n", "timestamp": 1},
        {"type": "result", "text": "42", "is_main_result": True},
        {"type": "number_of_executions", "execution_count": 2},
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text="\n".join(json.dumps(x) for x in output))

    monkeypatch.setattr(
        "agent_sandbox.code_interpreter.code_interpreter_sync.get_transport",
        lambda *_args, **_kwargs: httpx.MockTransport(respond),
    )
    seen: list[str] = []
    result = connected(CodeSandbox).run_code(
        "value + 1", on_stdout=lambda msg: seen.append(msg.line)
    )
    assert seen == ["first\n"]
    assert result.text == "42"
    assert result.logs.stdout == ["first\n"]
    assert result.execution_count == 2
    assert calls[0].url.host == "49999-contract-id.example.invalid"
    assert calls[0].url.path == "/execute"


def test_file_urls_are_local_synchronous_strings() -> None:
    sb = connected()
    for url in (sb.upload_url("/tmp/a.txt"), sb.download_url("/tmp/a.txt")):
        assert isinstance(url, str)
        assert "signature=" in url
        assert "placeholder-token" not in url


def test_network_and_conditional_snapshot_wire_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(
                201, json={"snapshotID": "snapshot-id", "names": ["team/state:v1"]}
            )
        if request.method == "GET":
            return httpx.Response(
                200, json=[{"snapshotID": "snapshot-id", "names": ["team/state:v1"]}]
            )
        return httpx.Response(204)

    monkeypatch.setattr(
        "agent_sandbox._standard.api.client_sync.get_transport",
        lambda *_args, **_kwargs: httpx.MockTransport(respond),
    )
    sb = connected()
    sb.update_network({"deny_out": ["0.0.0.0/0"]})
    assert calls[-1].method == "PUT"
    assert calls[-1].url.path == "/sandboxes/contract-id/network"
    assert json.loads(calls[-1].content)["denyOut"] == ["0.0.0.0/0"]
    snapshot = sb.create_snapshot(name="state:v1", request_timeout=300)
    assert snapshot.snapshot_id == "snapshot-id"
    assert snapshot.names == ["team/state:v1"]
    assert calls[-1].url.path == "/sandboxes/contract-id/snapshots"
    assert json.loads(calls[-1].content) == {"name": "state:v1"}
    options = {"api_key": "placeholder-key", "api_url": "https://api.example.invalid"}
    paginator = Sandbox.list_snapshots(sandbox_id=sb.sandbox_id, name="state", **options)
    assert paginator.next_items()[0].snapshot_id == "snapshot-id"
    assert calls[-1].url.params["sandboxID"] == "contract-id"
    assert calls[-1].url.params["name"] == "state"
    assert Sandbox.delete_snapshot("team/state:v1", **options)
    assert calls[-1].url.raw_path == b"/templates/team%2Fstate%3Av1"


def test_explicit_domain_derives_api_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E2B_API_URL", raising=False)
    assert ConnectionConfig(domain="example.invalid").api_url == "https://api.example.invalid"
    assert ConnectionConfig(debug=True).api_url == "http://localhost:3000"
    monkeypatch.setenv("E2B_DOMAIN", "environment.example.invalid")
    assert ConnectionConfig().api_url == "https://api.environment.example.invalid"


async def test_async_snapshot_name_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=[{"snapshotID": "snapshot-id", "names": ["team/state:v1"]}])

    monkeypatch.setattr(
        "agent_sandbox._standard.api.client_async.get_transport",
        lambda *_args, **_kwargs: httpx.MockTransport(respond),
    )
    paginator = AsyncSandbox.list_snapshots(
        name="team/state", api_key="placeholder-key", api_url="https://api.example.invalid"
    )
    assert (await paginator.next_items())[0].names == ["team/state:v1"]
    assert calls[0].url.params["name"] == "team/state"


@pytest.mark.parametrize("state", ["snapshotting", "snapshot_failed"])
def test_list_accepts_documented_alibaba_snapshot_states(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/sandboxes"
        return httpx.Response(
            200,
            json=[
                {
                    "sandboxID": "contract-id",
                    "templateID": "base",
                    "clientID": "client",
                    "cpuCount": 1,
                    "memoryMB": 1024,
                    "diskSizeMB": 10240,
                    "envdVersion": "0.6.1",
                    "state": state,
                    "startedAt": "2026-10-16T00:00:00Z",
                    "endAt": "2026-10-16T00:05:00Z",
                }
            ],
        )

    monkeypatch.setattr(
        "agent_sandbox._standard.api.client_sync.get_transport",
        lambda *_args, **_kwargs: httpx.MockTransport(respond),
    )
    paginator = Sandbox.list(api_key="placeholder-key", api_url="https://api.example.invalid")
    assert paginator.next_items()[0].state.value == state
