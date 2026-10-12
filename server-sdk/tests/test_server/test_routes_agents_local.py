"""Tests for the local Agents API operations (codex and qwen-code only).

Handlers are exercised through the default route table (so registration order and path
matching are real); a handful of tests also go over a live HTTP server. Fake ``codex`` and
``qwen`` shell scripts sit on ``PATH``: no real CLI, no API key.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import os
import socket
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

import easy_sandbox.server.routes_agents  # noqa: F401  (registers routes)
from easy_sandbox.server.agents.api_responses import ResponsesSocket
from easy_sandbox.server.app import SandboxRequestHandler
from easy_sandbox.server.router import CapabilityGroup, default_table
from easy_sandbox.server.routes_agents import get_agent_runtime, reset_agent_runtime
from easy_sandbox.server.types import ServerRequest, ServerResponse, SSEResponse

CANARY = "canary-secret-7f3a91c2d4e5"
MCP_URL = "https://mcp.example.com/mcp"


# ---------------------------------------------------------------------- #
# Fake CLIs
# ---------------------------------------------------------------------- #


def _script(lines: list[Any], *, pre: str = "", post: str = "", exit_code: int = 0) -> str:
    out = ["#!/bin/sh", "cat >/dev/null", pre]
    for line in lines:
        text = json.dumps(line, separators=(",", ":")).replace("'", "'\\''")
        out.append(f"printf '%s\\n' '{text}'")
    out += [post, f"exit {exit_code}", ""]
    return "\n".join(out)


def codex_lines(text: str = "codex-fake-ok", *extra: Any) -> list[Any]:
    return [
        {"type": "thread.started", "thread_id": "thr-parent-0001"},
        *extra,
        {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": text}},
        {"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 2}},
    ]


def qwen_lines(text: str = "qwen-fake-ok", *extra: Any) -> list[Any]:
    return [
        {"type": "system", "subtype": "init", "session_id": "qs-1"},
        *extra,
        {
            "type": "assistant",
            "message": {"id": "m1", "content": [{"type": "text", "text": text}]},
        },
        {"type": "result", "subtype": "success", "is_error": False, "result": text},
    ]


DUMP = "printf '%s\\n' \"$@\" > argv.txt; env > env.txt\n"


@pytest.fixture
def install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Path]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))

    def put(name: str, script: str) -> Path:
        path = bindir / name
        path.write_text(script)
        path.chmod(0o755)
        return path

    return put


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, install: Callable[..., Path]) -> Any:
    for name in (
        "EBX_AGENTS_DEFAULT",
        "EBX_AGENTS_CONFIG",
        "EBX_SERVER_TOKEN",
        "EBX_AGENTS_TRACES",
        "EBX_AGENTS_ALLOW_PRIVATE_URLS",
        "EBX_AGENTS_WEBHOOK_ALLOW_HTTP",
        "EBX_AGENTS_MAX_FILE_BYTES",
        "CODEX_HOME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EBX_AGENTS_PERSIST", "0")
    rw = tmp_path / "responses-ws"
    monkeypatch.setenv("EBX_AGENTS_RESPONSES_WORKSPACE", str(rw))
    install("codex", _script(codex_lines()))
    install("qwen", _script(qwen_lines()))
    reset_agent_runtime()
    yield
    reset_agent_runtime()


# ---------------------------------------------------------------------- #
# Direct dispatch through the route table
# ---------------------------------------------------------------------- #


def call(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    principal: str | None = None,
) -> Any:
    raw_path, _, query = path.partition("?")
    route, params = default_table().match(method, raw_path)
    assert route is not None, f"{method} {raw_path} is not registered"
    context: dict[str, Any] = {}
    if principal:
        context["policy"] = types.SimpleNamespace(identity=types.SimpleNamespace(id=principal))
    request = ServerRequest(
        method=method,
        path=raw_path,
        query=parse_qs(query),
        headers=headers or {},
        body=body,
        path_params=params or {},
        context=context,
    )
    return route.handler(request)


def ok(response: Any, status: int = 200) -> Any:
    assert isinstance(response, ServerResponse), response
    assert response.status == status, response.body
    assert response.headers.get("X-Easy-Sandbox-Local") == "1"
    return response.body


def refused(
    response: Any, status: int, *, param: str | None = None, code: str | None = None
) -> Any:
    assert isinstance(response, ServerResponse), response
    assert response.status == status, response.body
    error = response.body["error"]
    assert response.headers.get("x-should-retry") == "false"
    assert response.headers.get("X-Easy-Sandbox-Local") == "1"
    assert error["type"] == ("not_found_error" if status == 404 else "invalid_request_error")
    if param is not None:
        assert error["param"] == param
    if code is not None:
        assert error["code"] == code
    return error


def sse_text(response: Any) -> str:
    assert isinstance(response, SSEResponse)
    return "".join(
        chunk if isinstance(chunk, str) else chunk.decode() for chunk in response.event_iterator
    )


def sse_events(response: Any) -> list[dict[str, Any]]:
    events = []
    for frame in sse_text(response).split("\n\n"):
        for line in frame.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def wait_idle(
    session_id: str, principal: str | None = None, timeout: float = 20.0
) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        session = ok(call("GET", f"/v1/agents/sessions/{session_id}", principal=principal))
        if session["status"] == "idle":
            turns = ok(
                call(
                    "GET", f"/v1/agents/sessions/{session_id}/turns?order=asc", principal=principal
                )
            )["data"]
            if turns and all(t["status"] in ("completed", "failed", "cancelled") for t in turns):
                return session
        time.sleep(0.03)
    pytest.fail("session did not become idle")


def send(session_id: str, text: str = "go", principal: str | None = None) -> ServerResponse:
    return call(
        "POST",
        f"/v1/agents/sessions/{session_id}/events",
        {"events": [{"type": "agent.session.input.message", "input": text}]},
        principal=principal,
    )


def new_session(workspace: Path, adapter: str = "codex", **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "adapter": adapter,
        "environment": {"type": "self_hosted", "workspace_directory": str(workspace)},
        **extra,
    }
    return ok(call("POST", "/v1/agents/sessions", body, principal=extra.pop("_p", None)))


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    path = tmp_path / "workspace"
    path.mkdir()
    return path


def b64(data: bytes | str) -> str:
    raw = data.encode() if isinstance(data, str) else data
    return base64.b64encode(raw).decode()


def make_env(ws: Path, **fields: Any) -> dict[str, Any]:
    environment = {"type": "self_hosted", "workspace_directory": str(ws), **fields}
    return ok(call("POST", "/v1/agents/environments", {"environment": environment}))


def walk_strings(node: Any) -> list[str]:
    if isinstance(node, dict):
        return [s for v in node.values() for s in walk_strings(v)] + [str(k) for k in node]
    if isinstance(node, list):
        return [s for v in node for s in walk_strings(v)]
    return [str(node)]


# ---------------------------------------------------------------------- #
# Label contract and CANNOT routes
# ---------------------------------------------------------------------- #


class TestLabelContract:
    def test_existing_and_new_objects_carry_the_label(self, ws: Path) -> None:
        session = new_session(ws)
        assert session["x_easy_sandbox"]["local"] is True
        assert session["x_easy_sandbox"]["compute"] == "local_process"
        assert "queued_not_steered" in session["x_easy_sandbox"]["differences"]
        send(session["id"])
        wait_idle(session["id"])
        turn = ok(call("GET", f"/v1/agents/sessions/{session['id']}/turns"))["data"][0]
        item = ok(call("GET", f"/v1/agents/sessions/{session['id']}/items"))["data"][0]
        for obj in (turn, item):
            assert obj["x_easy_sandbox"]["local"] is True
            assert obj["x_easy_sandbox"]["compute"] != "openai_hosted"
        runtimes = ok(call("GET", "/v1/agents/runtimes"))["data"]
        assert all(r["x_easy_sandbox"]["local"] for r in runtimes)

    def test_no_object_claims_hosted_compute(self, ws: Path) -> None:
        env = make_env(ws)
        vault = ok(call("POST", "/v1/vaults", {"name": "v"}))
        agent = ok(call("POST", "/v1/agents", {"model": "codex"}))
        tmpl = ok(call("POST", "/v1/agents/environments/templates", {"name": "t"}))
        for obj in (env, vault, agent, tmpl):
            assert obj["x_easy_sandbox"]["compute"] in ("local_state", "local_process", "none")
            assert "openai_hosted" not in json.dumps(obj["x_easy_sandbox"])

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("POST", "/v1/responses/input_tokens"),
            ("DELETE", "/v1/models/codex"),
            ("POST", "/v1/agents/environments/env_x/register"),
            ("GET", "/v1/agents/environments/env_x/connect"),
        ],
    )
    def test_cannot_routes_are_labeled_404(self, method: str, path: str) -> None:
        response = call(method, path, {})
        error = refused(response, 404, code="agents.not_implemented_locally")
        assert error["x_easy_sandbox"]["differences"] == ["not_implemented_locally"]
        assert response.status != 501
        assert response.body != {}

    def test_cannot_routes_over_http(self) -> None:
        port = _free_port()
        httpd = _serve(port)
        try:
            for method, path in (
                ("POST", "/v1/responses/input_tokens"),
                ("DELETE", "/v1/models/codex"),
            ):
                status, body, headers = _http(port, method, path, {"model": "codex", "input": "x"})
                assert status == 404
                assert body["error"]["type"] == "not_found_error"
                assert headers["x-should-retry"] == "false"
                assert headers["x-easy-sandbox-local"] == "1"
        finally:
            httpd.shutdown()

    def test_other_adapters_stay_404(self, ws: Path) -> None:
        for name in ("claude-code", "claude_code", "cursor", "qoder", "command", "bogus"):
            refused(
                call("POST", "/v1/agents", {"model": "m", "adapter": name}),
                404,
                param="adapter",
            )
            refused(
                call(
                    "POST",
                    "/v1/responses",
                    {"model": "m", "input": "hi"},
                    headers={"X-EBX-Adapter": name},
                ),
                404,
                param="adapter",
            )
        ids = [m["id"] for m in ok(call("GET", "/v1/models"))["data"]]
        assert ids == ["codex", "qwen-code"]
        names = {r["name"] for r in ok(call("GET", "/v1/agents/runtimes?limit=100"))["data"]}
        assert names == {"codex", "qwen-code"}

    def test_group_disabled_hides_every_new_route(self) -> None:
        table = default_table()
        table.disable_group(CapabilityGroup.AGENTS)
        port = _free_port()
        httpd = _serve(port, enable=False)
        try:
            for method, path in (
                ("GET", "/v1/agents"),
                ("GET", "/v1/vaults"),
                ("GET", "/v1/models"),
                ("POST", "/v1/files"),
                ("GET", "/v1/webhook_event_types"),
                ("POST", "/v1/responses"),
            ):
                status, _, _ = _http(port, method, path, {} if method == "POST" else None)
                assert status == 404, path
        finally:
            httpd.shutdown()


# ---------------------------------------------------------------------- #
# A-01..A-05 definitions
# ---------------------------------------------------------------------- #


class TestDefinitions:
    def test_crud_and_ids(self) -> None:
        created = ok(
            call(
                "POST",
                "/v1/agents",
                {
                    "model": "gpt-5-codex",
                    "adapter": "codex",
                    "name": "reviewer",
                    "instructions": "be brief",
                    "metadata": {"team": "a"},
                },
            )
        )
        assert created["object"] == "agent"
        assert created["id"].startswith("agent_") and created["id"] != "reviewer"
        assert created["model"] == "gpt-5-codex"
        assert created["multi_agent"]["enabled"] is False
        assert created["x_easy_sandbox"]["runtime"] == "codex"
        got = ok(call("GET", f"/v1/agents/{created['id']}"))
        assert got == created
        updated = ok(
            call(
                "POST",
                f"/v1/agents/{created['id']}",
                {"instructions": "be long", "metadata": {}},
            )
        )
        assert updated["instructions"] == "be long"
        assert updated["metadata"] == {}
        assert updated["model"] == "gpt-5-codex"
        listing = ok(call("GET", "/v1/agents"))
        assert [a["id"] for a in listing["data"]] == [created["id"]]
        deleted = ok(call("DELETE", f"/v1/agents/{created['id']}"))
        assert deleted == {
            "id": created["id"],
            "object": "agent.deleted",
            "deleted": True,
            "x_easy_sandbox": deleted["x_easy_sandbox"],
        }
        refused(call("GET", f"/v1/agents/{created['id']}"), 404, code="resource_not_found")

    def test_literal_agent_routes_are_not_shadowed(self) -> None:
        assert ok(call("GET", "/v1/agents/runtimes"))["object"] == "list"
        assert ok(call("GET", "/v1/agents/sessions"))["object"] == "list"
        assert ok(call("GET", "/v1/agents/environments"))["object"] == "list"
        assert ok(call("GET", "/v1/agents/environments/templates"))["object"] == "list"

    @pytest.mark.parametrize(
        ("patch", "param"),
        [
            ({"tools": [{"type": "web_search"}]}, "tools[0].type"),
            ({"tools": [{"type": "function", "name": "f"}]}, "tools[0].type"),
            ({"multi_agent": {"enabled": True}}, "multi_agent.enabled"),
            ({"service_tier": "priority"}, "service_tier"),
            ({"text": {"verbosity": "high"}}, "text.verbosity"),
            ({"text": {"format": {"type": "json_object"}}}, "text.format"),
            ({"reasoning": {"summary": "auto"}}, "reasoning.summary"),
            ({"surprise": 1}, "surprise"),
            (
                {
                    "tools": [
                        {
                            "type": "mcp",
                            "server_label": "x",
                            "transport": {"type": "stdio", "command": "x", "cwd": "/"},
                        }
                    ]
                },
                "tools[0].transport.type",
            ),
            (
                {
                    "tools": [
                        {
                            "type": "mcp",
                            "server_label": "x",
                            "transport": {"type": "http", "server_url": MCP_URL + "?token=abc"},
                        }
                    ]
                },
                "tools[0].transport.server_url",
            ),
            (
                {
                    "tools": [
                        {
                            "type": "mcp",
                            "server_label": "x",
                            "allowed_tools": ["a"],
                            "transport": {"type": "http", "server_url": MCP_URL},
                        }
                    ]
                },
                "tools[0].allowed_tools",
            ),
        ],
    )
    def test_variant_refusals_are_400(self, patch: dict[str, Any], param: str) -> None:
        body = {"model": "gpt-5-codex", "adapter": "codex", **patch}
        refused(call("POST", "/v1/agents", body), 400, param=param)

    def test_reasoning_effort_only_where_honoured(self) -> None:
        ok(
            call(
                "POST",
                "/v1/agents",
                {"model": "m", "adapter": "codex", "reasoning": {"effort": "high"}},
            )
        )
        refused(
            call(
                "POST",
                "/v1/agents",
                {"model": "m", "adapter": "qwen", "reasoning": {"effort": "high"}},
            ),
            400,
            param="reasoning.effort",
        )

    def test_mcp_header_values_are_never_echoed(self) -> None:
        tool = {
            "type": "mcp",
            "server_label": "docs",
            "transport": {
                "type": "http",
                "server_url": MCP_URL,
                "headers": {"X-Api-Key": CANARY},
            },
        }
        created = ok(
            call("POST", "/v1/agents", {"model": "m", "adapter": "codex", "tools": [tool]})
        )
        assert CANARY not in json.dumps(created)
        assert created["tools"][0]["transport"]["headers"] == {"X-Api-Key": "***"}
        assert CANARY not in json.dumps(ok(call("GET", f"/v1/agents/{created['id']}")))
        assert CANARY not in json.dumps(ok(call("GET", "/v1/agents")))

    def test_session_uses_definition_and_keeps_its_snapshot(
        self, ws: Path, install: Callable[..., Path]
    ) -> None:
        install("codex", _script(codex_lines(), pre=DUMP))
        agent = ok(
            call(
                "POST",
                "/v1/agents",
                {"model": "gpt-5-codex", "adapter": "codex", "instructions": "first"},
            )
        )
        session = ok(
            call(
                "POST",
                "/v1/agents/sessions",
                {
                    "agent_id": agent["id"],
                    "environment": {"type": "self_hosted", "workspace_directory": str(ws)},
                },
            )
        )
        assert session["agent"]["id"] == agent["id"]
        assert session["agent"]["model"] == "gpt-5-codex"
        assert ok(call("GET", "/v1/agents?limit=5"))["data"][0]["id"] == agent["id"]
        ok(call("POST", f"/v1/agents/{agent['id']}", {"instructions": "second"}))
        send(session["id"], "hello")
        wait_idle(session["id"])
        stdin_args = (ws / "argv.txt").read_text()
        assert "gpt-5-codex" in stdin_args
        ok(call("DELETE", f"/v1/agents/{agent['id']}"))
        again = ok(call("GET", f"/v1/agents/sessions/{session['id']}"))
        assert again["agent"]["id"] == agent["id"]
        send(session["id"], "again")
        wait_idle(session["id"])
        by_agent = ok(call("GET", f"/v1/agents/sessions?agent_id={agent['id']}"))["data"]
        assert [s["id"] for s in by_agent] == [session["id"]]
        assert ok(call("GET", "/v1/agents/sessions?agent_id=nope"))["data"] == []

    def test_agent_id_and_inline_agent_are_exclusive(self, ws: Path) -> None:
        agent = ok(call("POST", "/v1/agents", {"model": "m", "adapter": "codex"}))
        refused(
            call(
                "POST",
                "/v1/agents/sessions",
                {"agent_id": agent["id"], "agent": {"model": "m"}, "adapter": "codex"},
            ),
            400,
            param="agent_id",
        )
        refused(
            call("POST", "/v1/agents/sessions", {"agent_id": "agent_missing"}),
            404,
            param="agent_id",
        )

    def test_inline_session_agent_is_validated_not_ignored(self, ws: Path) -> None:
        for agent, param in (
            ({"model": "m", "tools": [{"type": "web_search"}]}, "agent.tools[0].type"),
            ({"model": "m", "multi_agent": {"enabled": True}}, "agent.multi_agent.enabled"),
            ({"model": "m", "service_tier": "fast"}, "agent.service_tier"),
        ):
            refused(
                call(
                    "POST",
                    "/v1/agents/sessions",
                    {
                        "adapter": "codex",
                        "agent": agent,
                        "environment": {"workspace_directory": str(ws)},
                    },
                ),
                400,
                param=param,
            )


# ---------------------------------------------------------------------- #
# A-06..A-15 environments, files, templates, O-03 blobs
# ---------------------------------------------------------------------- #


class TestEnvironments:
    def test_create_get_list_and_label(self, ws: Path) -> None:
        env = make_env(ws)
        assert env["object"] == "agent.environment"
        assert env["type"] == "self_hosted"
        assert env["status"] == "ready"
        assert env["id"].startswith("env_")
        assert "local_workspace" in env["x_easy_sandbox"]["differences"]
        assert ok(call("GET", f"/v1/agents/environments/{env['id']}")) == env
        assert [e["id"] for e in ok(call("GET", "/v1/agents/environments"))["data"]] == [env["id"]]
        assert ok(call("GET", "/v1/agents/environments?type=openai_hosted"))["data"] == []

    def test_empty_hosted_request_is_converted_and_says_so(self, ws: Path, monkeypatch) -> None:
        monkeypatch.setattr(
            "easy_sandbox.server.agents.api_environments.check_workspace_root",
            lambda path, field="": str(ws),
        )
        body = ok(
            call("POST", "/v1/agents/environments", {"environment": {"type": "openai_hosted"}})
        )
        assert body["type"] == "self_hosted"
        assert "hosted_request_converted" in body["x_easy_sandbox"]["differences"]

    def test_configured_hosted_request_is_refused(self, ws: Path) -> None:
        refused(
            call(
                "POST",
                "/v1/agents/environments",
                {"environment": {"type": "openai_hosted", "env": {"A": "b"}}},
            ),
            400,
            param="environment.type",
        )

    @pytest.mark.parametrize(
        "field",
        [
            "network",
            "packages",
            "setup_commands",
            "plugins",
            "skills",
            "desktop",
            "container_size",
            "capability_directories",
        ],
    )
    def test_hosted_only_fields_are_400(self, ws: Path, field: str) -> None:
        value: Any = {"enabled": True} if field == "desktop" else ["x"]
        if field in ("network", "packages"):
            value = {"access": "disabled"} if field == "network" else {"npm": ["x"]}
        refused(
            call(
                "POST",
                "/v1/agents/environments",
                {
                    "environment": {
                        "type": "self_hosted",
                        "workspace_directory": str(ws),
                        field: value,
                    }
                },
            ),
            400,
            param=f"environment.{field}",
        )

    def test_env_files_and_vault_ids_applied_at_create(self, ws: Path) -> None:
        vault = ok(call("POST", "/v1/vaults", {"name": "v"}))
        env = make_env(
            ws,
            env={"MY_VAR": "1"},
            files=[{"type": "inline", "path": "/workspace/conf/a.txt", "data": b64("hello")}],
        )
        assert (ws / "conf" / "a.txt").read_text() == "hello"
        assert env["files"][0]["path"] == "/workspace/conf/a.txt"
        assert env["files"][0]["size_bytes"] == 5
        assert "MY_VAR" not in json.dumps(env)
        second = ok(
            call(
                "POST",
                "/v1/agents/environments",
                {
                    "environment": {"type": "self_hosted", "workspace_directory": str(ws)},
                    "vault_ids": [vault["id"]],
                },
            )
        )
        assert second["vault_ids"] == [vault["id"]]
        refused(
            call(
                "POST",
                "/v1/agents/environments",
                {
                    "environment": {"type": "self_hosted", "workspace_directory": str(ws)},
                    "vault_ids": ["vlt_missing"],
                },
            ),
            404,
            param="vault_ids[0]",
        )

    def test_workspace_must_be_admitted(self) -> None:
        for bad in ("/", "/etc", "/proc/1", "relative", "/tmp/../etc"):
            refused(
                call(
                    "POST",
                    "/v1/agents/environments",
                    {"environment": {"type": "self_hosted", "workspace_directory": bad}},
                ),
                400,
                param="environment.workspace_directory",
            )

    @pytest.mark.parametrize(
        "name",
        [
            "PATH",
            "HOME",
            "OPENAI_BASE_URL",
            "OPENAI_API_KEY",
            "HTTPS_PROXY",
            "CODEX_HOME",
            "NODE_OPTIONS",
            "PYTHONPATH",
            "GIT_SSH_COMMAND",
            "EBX_SERVER_TOKEN",
            "LD_PRELOAD",
        ],
    )
    def test_env_deny_list(self, ws: Path, name: str) -> None:
        refused(
            call(
                "POST",
                "/v1/agents/environments",
                {
                    "environment": {
                        "type": "self_hosted",
                        "workspace_directory": str(ws),
                        "env": {name: "x"},
                    }
                },
            ),
            400,
        )


class TestEnvironmentFiles:
    def _create(self, env_id: str, path: str, data: str = "x", **extra: Any) -> ServerResponse:
        body = {"type": "inline", "path": path, "data": b64(data), **extra}
        return call("POST", f"/v1/agents/environments/{env_id}/files", body)

    def test_write_list_and_no_overwrite(self, ws: Path) -> None:
        env = make_env(ws)
        written = ok(self._create(env["id"], "/workspace/src/main.py", "print(1)"))
        assert written["object"] == "agent.environment.file"
        assert written["environment_id"] == env["id"]
        assert written["path"] == "/workspace/src/main.py"
        assert written["size_bytes"] == 8
        assert written["x_easy_sandbox"]["differences"] == ["local_workspace", "no_overwrite"]
        assert (ws / "src" / "main.py").read_text() == "print(1)"
        ok(self._create(env["id"], "/workspace/src/main.py", "print(1)"))
        refused(
            self._create(env["id"], "/workspace/src/main.py", "other"),
            400,
            param="path",
            code="agents.file_exists",
        )
        assert (ws / "src" / "main.py").read_text() == "print(1)"
        ok(self._create(env["id"], "/workspace/b.txt", "b"))
        (ws / ".git").mkdir()
        (ws / ".git" / "config").write_text("secret")
        rows = ok(call("GET", f"/v1/agents/environments/{env['id']}/files?order=asc"))
        assert [r["path"] for r in rows["data"]] == ["/workspace/b.txt", "/workspace/src/main.py"]
        only = ok(call("GET", f"/v1/agents/environments/{env['id']}/files?path=/workspace/src"))
        assert [r["path"] for r in only["data"]] == ["/workspace/src/main.py"]

    def test_listing_pages_with_opaque_token(self, ws: Path) -> None:
        env = make_env(ws)
        for name in ("a", "b", "c"):
            ok(self._create(env["id"], f"/workspace/{name}.txt"))
        url = f"/v1/agents/environments/{env['id']}/files?order=asc&limit=2"
        first = ok(call("GET", url))
        assert first["has_more"] is True and len(first["data"]) == 2
        second = ok(call("GET", url + f"&page={first['next']}"))
        assert [r["path"] for r in second["data"]] == ["/workspace/c.txt"]
        assert second["has_more"] is False and second["next"] is None
        refused(call("GET", url + "&page=junk"), 400, param="page")

    def test_symlinks_never_followed(self, ws: Path, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        env = make_env(ws)
        (ws / "link").symlink_to(outside)
        refused(self._create(env["id"], "/workspace/link/x.txt"), 400, code="agents.path_refused")
        assert list(outside.iterdir()) == []
        (ws / "file-link").symlink_to(outside / "target.txt")
        refused(self._create(env["id"], "/workspace/file-link"), 400)
        assert not (outside / "target.txt").exists()
        (ws / "visible.txt").write_text("x")
        rows = ok(call("GET", f"/v1/agents/environments/{env['id']}/files"))["data"]
        assert [r["path"] for r in rows] == ["/workspace/visible.txt"]

    @pytest.mark.parametrize(
        "path",
        [
            "/workspace/.git/hooks/pre-commit",
            "/workspace/.codex/config.toml",
            "/workspace/.qwen/settings.json",
            "/workspace/.mcp.json",
            "/workspace/AGENTS.md",
            "/workspace/sub/.bashrc",
        ],
    )
    def test_agent_config_locations_are_refused(self, ws: Path, path: str) -> None:
        env = make_env(ws)
        refused(self._create(env["id"], path), 400, code="agents.path_refused")

    @pytest.mark.parametrize("path", ["relative.txt", "/workspace/../escape", "/workspace", "/"])
    def test_bad_paths(self, ws: Path, path: str) -> None:
        env = make_env(ws)
        refused(self._create(env["id"], path), 400)

    def test_size_cap_and_bad_base64(self, ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EBX_AGENTS_MAX_FILE_BYTES", "8")
        env = make_env(ws)
        refused(
            self._create(env["id"], "/workspace/big", "123456789"),
            400,
            code="agents.file_too_large",
        )
        refused(
            call(
                "POST",
                f"/v1/agents/environments/{env['id']}/files",
                {"type": "inline", "path": "/workspace/x", "data": "***"},
            ),
            400,
        )

    def test_foreign_principal_cannot_reach_an_environment(self, ws: Path) -> None:
        env = make_env(ws)
        refused(
            call("GET", f"/v1/agents/environments/{env['id']}", principal="bob"),
            404,
            code="resource_not_found",
        )
        refused(self._create_as(env["id"], "bob"), 404)
        refused(call("GET", f"/v1/agents/environments/{env['id']}/files", principal="bob"), 404)

    def _create_as(self, env_id: str, principal: str) -> ServerResponse:
        return call(
            "POST",
            f"/v1/agents/environments/{env_id}/files",
            {"type": "inline", "path": "/workspace/x", "data": b64("x")},
            principal=principal,
        )


class TestBlobStore:
    def test_file_id_round_trip(self, ws: Path) -> None:
        blob = ok(
            call(
                "POST",
                "/v1/files",
                {"purpose": "user_data", "filename": "n.txt", "data": b64("from blob")},
            )
        )
        assert blob["id"].startswith("file-") and blob["object"] == "file"
        assert blob["bytes"] == 9 and blob["purpose"] == "user_data"
        assert blob["x_easy_sandbox"]["differences"] == ["local_blob"]
        env = make_env(ws)
        written = ok(
            call(
                "POST",
                f"/v1/agents/environments/{env['id']}/files",
                {"type": "file_id", "file_id": blob["id"], "path": "/workspace/n.txt"},
            )
        )
        assert written["size_bytes"] == 9
        assert (ws / "n.txt").read_text() == "from blob"

    def test_unknown_and_foreign_file_ids_are_400(self, ws: Path) -> None:
        blob = ok(call("POST", "/v1/files", {"purpose": "user_data", "data": b64("x")}))
        env = make_env(ws)
        for file_id, principal in (("file-abc123", None), (blob["id"], "bob")):
            if principal:
                env_b = ok(
                    call(
                        "POST",
                        "/v1/agents/environments",
                        {"environment": {"workspace_directory": str(ws / "b")}},
                        principal=principal,
                    )
                )
                target = env_b["id"]
            else:
                target = env["id"]
            refused(
                call(
                    "POST",
                    f"/v1/agents/environments/{target}/files",
                    {"type": "file_id", "file_id": file_id, "path": "/workspace/z"},
                    principal=principal,
                ),
                400,
                param="file.file_id",
                code="agents.file_not_found",
            )

    def test_only_user_data(self) -> None:
        refused(
            call("POST", "/v1/files", {"purpose": "assistants", "data": b64("x")}),
            400,
            param="purpose",
        )


class TestTemplates:
    def test_crud_is_reduced_and_write_only(self, ws: Path) -> None:
        created = ok(
            call(
                "POST",
                "/v1/agents/environments/templates",
                {
                    "name": "base",
                    "env": {"TEMPLATE_VAR": CANARY},
                    "files": [{"type": "inline", "path": "/workspace/t.txt", "data": b64(CANARY)}],
                },
            )
        )
        assert created["object"] == "agent.environment.template"
        assert created["files"] == [
            {"type": "inline", "path": "/workspace/t.txt", "size_bytes": 26}
        ]
        assert created["x_easy_sandbox"]["differences"] == [
            "not_hosted_template",
            "applies_env_and_files_only",
        ]
        tid = created["id"]
        assert CANARY not in json.dumps(ok(call("GET", f"/v1/agents/environments/templates/{tid}")))
        listed = ok(call("GET", "/v1/agents/environments/templates"))
        assert CANARY not in json.dumps(listed)
        updated = ok(call("POST", f"/v1/agents/environments/templates/{tid}", {"name": "renamed"}))
        assert updated["name"] == "renamed" and len(updated["files"]) == 1
        deleted = ok(call("DELETE", f"/v1/agents/environments/templates/{tid}"))
        assert deleted["object"] == "agent.environment.template.deleted"
        refused(call("GET", f"/v1/agents/environments/templates/{tid}"), 404)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("network", {"access": "disabled"}),
            ("packages", {"python": ["x"]}),
            ("setup_commands", [{"command": "x"}]),
            ("plugins", [{"type": "inline"}]),
            ("skills", [{"type": "skill_reference", "skill_id": "s"}]),
            ("desktop", {"enabled": True}),
            ("capability_directories", ["/x"]),
        ],
    )
    def test_refused_fields_are_400_on_create_and_update(self, field: str, value: Any) -> None:
        refused(call("POST", "/v1/agents/environments/templates", {field: value}), 400, param=field)
        tid = ok(call("POST", "/v1/agents/environments/templates", {"name": "t"}))["id"]
        refused(
            call("POST", f"/v1/agents/environments/templates/{tid}", {field: value}),
            400,
            param=field,
        )

    def test_environment_template_id_applies_env_and_files(
        self, ws: Path, install: Callable[..., Path]
    ) -> None:
        install("codex", _script(codex_lines(), pre=DUMP))
        tid = ok(
            call(
                "POST",
                "/v1/agents/environments/templates",
                {
                    "env": {"TEMPLATE_VAR": "from-template"},
                    "files": [{"type": "inline", "path": "/workspace/t.txt", "data": b64("tpl")}],
                },
            )
        )["id"]
        env = ok(
            call(
                "POST",
                "/v1/agents/environments",
                {
                    "environment": {
                        "type": "self_hosted",
                        "workspace_directory": str(ws),
                        "environment_template_id": tid,
                        "env": {"EXTRA_VAR": "inline"},
                    }
                },
            )
        )
        assert (ws / "t.txt").read_text() == "tpl"
        session = ok(
            call(
                "POST",
                "/v1/agents/sessions",
                {"adapter": "codex", "environment": {"type": "self_hosted", "id": env["id"]}},
            )
        )
        assert session["environment"]["id"] == env["id"]
        send(session["id"])
        wait_idle(session["id"])
        env_dump = (ws / "env.txt").read_text()
        assert "TEMPLATE_VAR=from-template" in env_dump
        assert "EXTRA_VAR=inline" in env_dump
        refused(
            call(
                "POST",
                "/v1/agents/environments",
                {"environment": {"environment_template_id": "envtmpl_missing"}},
            ),
            404,
            param="environment.environment_template_id",
        )

    def test_file_id_files_in_templates(self, ws: Path) -> None:
        blob = ok(call("POST", "/v1/files", {"purpose": "user_data", "data": b64("blobbed")}))
        template = ok(
            call(
                "POST",
                "/v1/agents/environments/templates",
                {"files": [{"type": "file_id", "file_id": blob["id"], "path": "/workspace/b.txt"}]},
            )
        )
        assert template["files"][0]["file_id"] == blob["id"]
        make_env(ws, environment_template_id=template["id"])
        assert (ws / "b.txt").read_text() == "blobbed"


# ---------------------------------------------------------------------- #
# A-38..A-47 vaults and credentials
# ---------------------------------------------------------------------- #

TOOL = {
    "type": "mcp",
    "server_label": "docs",
    "transport": {"type": "http", "server_url": MCP_URL},
}


def cred_body(token: str = CANARY, url: str = MCP_URL, **auth: Any) -> dict[str, Any]:
    return {
        "name": "docs-token",
        "auth": {"type": "static_bearer", "token": token, "mcp_server_url": url, **auth},
    }


class TestVaults:
    def test_vault_crud(self) -> None:
        vault = ok(call("POST", "/v1/vaults", {"name": "team", "metadata": {"k": "v"}}))
        assert vault["object"] == "vault"
        assert set(vault) == {"id", "object", "created_at", "metadata", "name", "x_easy_sandbox"}
        assert vault["x_easy_sandbox"]["differences"] == ["memory_only"]
        assert ok(call("GET", f"/v1/vaults/{vault['id']}")) == vault
        renamed = ok(
            call("POST", f"/v1/vaults/{vault['id']}", {"name": None, "metadata": {"a": "b"}})
        )
        assert renamed["name"] is None and renamed["metadata"] == {"a": "b"}
        assert [v["id"] for v in ok(call("GET", "/v1/vaults"))["data"]] == [vault["id"]]
        assert ok(call("GET", "/v1/vaults?metadata[a]=b"))["data"][0]["id"] == vault["id"]
        assert ok(call("GET", "/v1/vaults?metadata[a]=zzz"))["data"] == []
        assert ok(call("GET", "/v1/vaults?status=archived"))["data"] == []
        deleted = ok(call("DELETE", f"/v1/vaults/{vault['id']}"))
        assert deleted["object"] == "vault.deleted"
        refused(call("GET", f"/v1/vaults/{vault['id']}"), 404, code="resource_not_found")

    def test_vault_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EBX_AGENTS_MAX_VAULTS", "1")
        reset_agent_runtime()
        ok(call("POST", "/v1/vaults", {}))
        refused(call("POST", "/v1/vaults", {}), 400, code="agents.limit_exceeded")

    def test_credential_crud_never_echoes_the_secret(self) -> None:
        vault = ok(call("POST", "/v1/vaults", {"name": "v"}))
        path = f"/v1/vaults/{vault['id']}/credentials"
        created = ok(call("POST", path, cred_body()))
        assert created["object"] == "vault.credential"
        assert created["vault_id"] == vault["id"]
        assert created["auth"] == {"type": "static_bearer", "mcp_server_url": MCP_URL}
        assert created["x_easy_sandbox"]["differences"] == ["memory_only", "secret_in_agent_env"]
        cid = created["id"]
        bodies = [
            created,
            ok(call("GET", f"{path}/{cid}")),
            ok(call("GET", path)),
            ok(call("POST", f"{path}/{cid}", {"metadata": {"m": "1"}})),
            ok(
                call(
                    "POST",
                    f"{path}/{cid}",
                    {"auth": {"type": "static_bearer", "token": CANARY + "2"}},
                )
            ),
            ok(call("DELETE", f"{path}/{cid}")),
        ]
        for body in bodies:
            blob = json.dumps(body)
            assert CANARY not in blob and "Bearer" not in blob
            for forbidden in ("token", "secret_value", "refresh_token", "access_token"):
                assert forbidden not in [k.lower() for k in walk_strings(body) if k == forbidden]
        refused(call("GET", f"{path}/{cid}"), 404)

    def test_oauth_access_token_only(self) -> None:
        vault = ok(call("POST", "/v1/vaults", {}))
        path = f"/v1/vaults/{vault['id']}/credentials"
        body = {
            "name": "oauth",
            "auth": {
                "type": "mcp_oauth",
                "access_token": CANARY,
                "mcp_server_url": MCP_URL,
                "expires_at": "2099-01-01T00:00:00Z",
            },
        }
        created = ok(call("POST", path, body))
        assert created["auth"]["type"] == "mcp_oauth"
        assert created["auth"]["refresh"] is None
        assert CANARY not in json.dumps(created)

    @pytest.mark.parametrize(
        ("auth", "param"),
        [
            (
                {
                    "type": "environment_variable",
                    "secret_name": "K",
                    "secret_value": CANARY,
                    "networking": {"type": "limited", "allowed_hosts": ["a.com"]},
                },
                "auth.type",
            ),
            (
                {
                    "type": "mcp_oauth",
                    "access_token": CANARY,
                    "mcp_server_url": MCP_URL,
                    "refresh": {
                        "client_id": "c",
                        "refresh_token": CANARY,
                        "token_endpoint": "https://evil.example/token",
                        "token_endpoint_auth": {"type": "none"},
                    },
                },
                "auth.refresh",
            ),
            (
                {
                    "type": "static_bearer",
                    "token": CANARY,
                    "mcp_server_url": MCP_URL,
                    "networking": {"type": "unrestricted"},
                },
                "auth.networking",
            ),
            (
                {
                    "type": "static_bearer",
                    "token": CANARY,
                    "mcp_server_url": MCP_URL,
                    "networking": {"type": "limited", "allowed_hosts": ["other.example.com"]},
                },
                "auth.networking.allowed_hosts",
            ),
            (
                {
                    "type": "static_bearer",
                    "token": CANARY,
                    "mcp_server_url": "http://mcp.example.com/m",
                },
                "auth.mcp_server_url",
            ),
            (
                {"type": "static_bearer", "token": CANARY, "mcp_server_url": "https://127.0.0.1/m"},
                "auth.mcp_server_url",
            ),
            (
                {"type": "static_bearer", "token": CANARY + "\nX: y", "mcp_server_url": MCP_URL},
                "auth.token",
            ),
        ],
    )
    def test_variant_refusals_never_quote_the_secret(
        self, auth: dict[str, Any], param: str
    ) -> None:
        vault = ok(call("POST", "/v1/vaults", {}))
        response = call(
            "POST", f"/v1/vaults/{vault['id']}/credentials", {"name": "n", "auth": auth}
        )
        refused(response, 400, param=param)
        assert CANARY not in json.dumps(response.body)

    def test_limited_to_own_host_is_accepted(self) -> None:
        vault = ok(call("POST", "/v1/vaults", {}))
        body = cred_body(networking={"type": "limited", "allowed_hosts": ["MCP.example.com"]})
        created = ok(call("POST", f"/v1/vaults/{vault['id']}/credentials", body))
        assert created["auth"]["networking"] == {
            "type": "limited",
            "allowed_hosts": ["mcp.example.com"],
        }

    def test_rotation_cannot_change_type_or_add_refresh(self) -> None:
        vault = ok(call("POST", "/v1/vaults", {}))
        path = f"/v1/vaults/{vault['id']}/credentials"
        cid = ok(call("POST", path, cred_body()))["id"]
        refused(
            call("POST", f"{path}/{cid}", {"auth": {"type": "mcp_oauth", "access_token": "x" * 8}}),
            400,
            param="auth.type",
        )

    def test_owner_binding(self) -> None:
        vault = ok(call("POST", "/v1/vaults", {"name": "alice"}, principal="alice"))
        path = f"/v1/vaults/{vault['id']}"
        refused(call("GET", path, principal="bob"), 404)
        refused(call("DELETE", path, principal="bob"), 404)
        refused(call("POST", f"{path}/credentials", cred_body(), principal="bob"), 404)
        assert ok(call("GET", "/v1/vaults", principal="bob"))["data"] == []
        refused(
            call(
                "POST",
                "/v1/agents/sessions",
                {"adapter": "codex", "vault_ids": [vault["id"]]},
                principal="bob",
            ),
            404,
            param="vault_ids[0]",
        )


class TestCredentialInjection:
    def _setup(
        self, ws: Path, adapter: str = "codex", token: str = CANARY
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        agent = ok(
            call(
                "POST", "/v1/agents", {"model": "gpt-5-codex", "adapter": adapter, "tools": [TOOL]}
            )
        )
        vault = ok(call("POST", "/v1/vaults", {"name": "v"}))
        cred = ok(call("POST", f"/v1/vaults/{vault['id']}/credentials", cred_body(token)))
        session = ok(
            call(
                "POST",
                "/v1/agents/sessions",
                {
                    "agent_id": agent["id"],
                    "vault_ids": [vault["id"]],
                    "environment": {"type": "self_hosted", "workspace_directory": str(ws)},
                },
            )
        )
        return agent, vault, cred | {"session": session}

    def test_codex_secret_travels_in_env_never_argv(
        self, ws: Path, install: Callable[..., Path]
    ) -> None:
        install("codex", _script(codex_lines(), pre=DUMP))
        agent, vault, extra = self._setup(ws)
        session = extra["session"]
        assert session["vault_ids"] == [vault["id"]]
        assert session["agent"]["tools"][0]["server_label"] == "docs"
        assert send(session["id"]).status == 202
        wait_idle(session["id"])
        argv = (ws / "argv.txt").read_text()
        assert CANARY not in argv
        assert "env_http_headers" in argv and "EBX_MCP_DOCS_AUTHORIZATION" in argv
        env_dump = (ws / "env.txt").read_text()
        assert f"EBX_MCP_DOCS_AUTHORIZATION=Bearer {CANARY}" in env_dump
        everything = json.dumps(
            [
                ok(call("GET", f"/v1/agents/sessions/{session['id']}")),
                ok(call("GET", f"/v1/agents/sessions/{session['id']}/items")),
                ok(call("GET", f"/v1/agents/sessions/{session['id']}/turns")),
                ok(call("GET", f"/v1/agents/{agent['id']}")),
            ]
        )
        assert CANARY not in everything
        stream = call("GET", f"/v1/agents/sessions/{session['id']}/events?after=0")
        assert CANARY not in sse_text(stream)

    def test_qwen_gets_a_placeholder_in_settings_and_the_value_in_env(
        self, ws: Path, install: Callable[..., Path]
    ) -> None:
        install("qwen", _script(qwen_lines(), pre="env > env.txt\n"))
        _, _, extra = self._setup(ws, adapter="qwen-code")
        session = extra["session"]
        send(session["id"])
        wait_idle(session["id"])
        settings = (ws / ".qwen" / "settings.json").read_text()
        assert CANARY not in settings
        assert "${EBX_MCP_DOCS_AUTHORIZATION}" in settings
        assert f"EBX_MCP_DOCS_AUTHORIZATION=Bearer {CANARY}" in (ws / "env.txt").read_text()

    def test_rotation_reaches_the_next_turn(self, ws: Path, install: Callable[..., Path]) -> None:
        install("codex", _script(codex_lines(), pre=DUMP))
        _, vault, extra = self._setup(ws)
        session = extra["session"]
        send(session["id"])
        wait_idle(session["id"])
        call(
            "POST",
            f"/v1/vaults/{vault['id']}/credentials/{extra['id']}",
            {"auth": {"type": "static_bearer", "token": "rotated-token-value"}},
        )
        send(session["id"], "again")
        deadline = time.time() + 15
        while time.time() < deadline and "rotated-token-value" not in (ws / "env.txt").read_text():
            time.sleep(0.05)
        assert "Bearer rotated-token-value" in (ws / "env.txt").read_text()

    def test_deleted_credential_fails_the_next_turn_explicitly(self, ws: Path) -> None:
        _, vault, extra = self._setup(ws)
        session = extra["session"]
        ok(call("DELETE", f"/v1/vaults/{vault['id']}/credentials/{extra['id']}"))
        error = refused(send(session["id"]), 400, code="agents.credential_unavailable")
        assert "docs" in error["message"]
        ok(call("DELETE", f"/v1/vaults/{vault['id']}"))
        refused(send(session["id"]), 400, code="agents.credential_unavailable")
        assert ok(call("GET", f"/v1/agents/sessions/{session['id']}/turns"))["data"] == []

    def test_expired_access_token_fails_explicitly(self, ws: Path) -> None:
        agent = ok(call("POST", "/v1/agents", {"model": "m", "adapter": "codex", "tools": [TOOL]}))
        vault = ok(call("POST", "/v1/vaults", {}))
        body = {
            "name": "o",
            "auth": {
                "type": "mcp_oauth",
                "access_token": CANARY,
                "mcp_server_url": MCP_URL,
                "expires_at": "2001-01-01T00:00:00Z",
            },
        }
        ok(call("POST", f"/v1/vaults/{vault['id']}/credentials", body))
        session = ok(
            call(
                "POST",
                "/v1/agents/sessions",
                {
                    "agent_id": agent["id"],
                    "vault_ids": [vault["id"]],
                    "environment": {"workspace_directory": str(ws)},
                },
            )
        )
        refused(send(session["id"]), 400, code="agents.credential_expired")

    def test_url_mismatch_means_no_injection_and_explicit_id_is_checked(
        self, ws: Path, install: Callable[..., Path]
    ) -> None:
        install("codex", _script(codex_lines(), pre=DUMP))
        agent = ok(call("POST", "/v1/agents", {"model": "m", "adapter": "codex", "tools": [TOOL]}))
        vault = ok(call("POST", "/v1/vaults", {}))
        other = ok(
            call(
                "POST",
                f"/v1/vaults/{vault['id']}/credentials",
                cred_body(url="https://other.example.com/mcp"),
            )
        )
        session = ok(
            call(
                "POST",
                "/v1/agents/sessions",
                {
                    "agent_id": agent["id"],
                    "vault_ids": [vault["id"]],
                    "environment": {"workspace_directory": str(ws)},
                },
            )
        )
        send(session["id"])
        wait_idle(session["id"])
        assert CANARY not in (ws / "env.txt").read_text()
        pinned = ok(
            call(
                "POST",
                "/v1/agents",
                {
                    "model": "m",
                    "adapter": "codex",
                    "tools": [{**TOOL, "credential_id": other["id"]}],
                },
            )
        )
        refused(
            call(
                "POST",
                "/v1/agents/sessions",
                {
                    "agent_id": pinned["id"],
                    "vault_ids": [vault["id"]],
                    "environment": {"workspace_directory": str(ws)},
                },
            ),
            400,
            code="agents.credential_mismatch",
        )

    def test_two_matching_credentials_are_ambiguous(self, ws: Path) -> None:
        agent = ok(call("POST", "/v1/agents", {"model": "m", "adapter": "codex", "tools": [TOOL]}))
        vault = ok(call("POST", "/v1/vaults", {}))
        for _ in range(2):
            ok(call("POST", f"/v1/vaults/{vault['id']}/credentials", cred_body()))
        refused(
            call(
                "POST",
                "/v1/agents/sessions",
                {
                    "agent_id": agent["id"],
                    "vault_ids": [vault["id"]],
                    "environment": {"workspace_directory": str(ws)},
                },
            ),
            400,
            code="agents.credential_ambiguous",
        )


# ---------------------------------------------------------------------- #
# A-18 session update, A-27..A-31 artifacts and traces
# ---------------------------------------------------------------------- #


class TestSessionUpdate:
    def test_metadata_only(self, ws: Path) -> None:
        session = new_session(ws)
        updated = ok(
            call("POST", f"/v1/agents/sessions/{session['id']}", {"metadata": {"team": "x"}})
        )
        assert updated["metadata"] == {"team": "x"}
        assert ok(call("GET", f"/v1/agents/sessions/{session['id']}"))["metadata"] == {"team": "x"}
        for key in ("agent", "vault_ids", "environment"):
            refused(call("POST", f"/v1/agents/sessions/{session['id']}", {key: {}}), 400, param=key)
        refused(
            call("POST", f"/v1/agents/sessions/{session['id']}", {"model": "x"}), 400, param="model"
        )
        refused(
            call("POST", f"/v1/agents/sessions/{session['id']}", {"metadata": {"k": 1}}),
            400,
            param="metadata.k",
        )

    def test_foreign_session_is_an_unknown_session(self, ws: Path) -> None:
        session = ok(
            call(
                "POST",
                "/v1/agents/sessions",
                {"adapter": "codex", "environment": {"workspace_directory": str(ws)}},
                principal="alice",
            )
        )
        unknown = call("GET", "/v1/agents/sessions/agsess_nope", principal="bob")
        foreign = call("GET", f"/v1/agents/sessions/{session['id']}", principal="bob")
        assert foreign.status == 404
        assert foreign.body["error"]["code"] == unknown.body["error"]["code"]
        assert foreign.body["error"]["message"].replace(session["id"], "X") == unknown.body[
            "error"
        ]["message"].replace("agsess_nope", "X")
        assert ok(call("GET", "/v1/agents/sessions", principal="bob"))["data"] == []
        refused(send(session["id"], principal="bob"), 404)
        refused(call("DELETE", f"/v1/agents/sessions/{session['id']}", principal="bob"), 404)
        for tail in ("artifacts", "traces", "subagents", "items", "turns"):
            refused(
                call("GET", f"/v1/agents/sessions/{session['id']}/{tail}", principal="bob"), 404
            )
        ok(call("DELETE", f"/v1/agents/sessions/{session['id']}", principal="alice"))


class TestArtifacts:
    def _run_codex(
        self,
        ws: Path,
        install: Callable[..., Path],
        *,
        lines: list[Any] | None = None,
        pre: str = "printf 'artifact-bytes' > out.txt\n",
    ) -> dict[str, Any]:
        change = {
            "type": "item.completed",
            "item": {
                "id": "f1",
                "type": "file_change",
                "status": "completed",
                "changes": [{"path": "out.txt", "kind": "add"}],
            },
        }
        install("codex", _script(lines or codex_lines("done", change), pre=pre))
        session = new_session(ws)
        send(session["id"])
        wait_idle(session["id"])
        return session

    def test_snapshot_of_reported_paths_is_immutable_and_delete_keeps_the_file(
        self, ws: Path, install: Callable[..., Path]
    ) -> None:
        session = self._run_codex(ws, install)
        base = f"/v1/agents/sessions/{session['id']}/artifacts"
        rows = ok(call("GET", base))["data"]
        assert len(rows) == 1
        art = rows[0]
        assert art["object"] == "agent.session.artifact"
        assert art["path"] == "/workspace/out.txt"
        assert art["size_bytes"] == 14
        assert art["session_id"] == session["id"]
        assert art["turn_id"].startswith("turn_")
        assert art["x_easy_sandbox"]["differences"] == ["snapshot_copy", "reported_paths_only"]
        assert str(ws) not in json.dumps(art)
        assert ok(call("GET", f"{base}/{art['id']}")) == art
        (ws / "out.txt").write_text("changed afterwards")
        content = call("GET", f"{base}/{art['id']}/content")
        assert isinstance(content, SSEResponse)
        assert content.headers["X-Content-Type-Options"] == "nosniff"
        assert content.headers["Content-Disposition"].startswith("attachment")
        assert content.headers["X-Easy-Sandbox-Local"] == "1"
        assert b"".join(content.event_iterator) == b"artifact-bytes"
        deleted = ok(call("DELETE", f"{base}/{art['id']}"))
        assert deleted["x_easy_sandbox"]["deleted_scope"] == "snapshot"
        assert deleted["object"] == "agent.session.artifact.deleted"
        assert (ws / "out.txt").read_text() == "changed afterwards"
        refused(call("GET", f"{base}/{art['id']}"), 404)
        refused(call("GET", f"{base}/{art['id']}/content"), 404)

    def test_unreported_files_are_never_published(
        self, ws: Path, install: Callable[..., Path]
    ) -> None:
        (ws / ".env").write_text("SECRET=1")
        session = self._run_codex(
            ws, install, lines=codex_lines("no change"), pre="printf 'x' > unreported.txt\n"
        )
        assert ok(call("GET", f"/v1/agents/sessions/{session['id']}/artifacts"))["data"] == []

    def test_symlink_and_escape_paths_are_not_snapshotted(
        self, ws: Path, tmp_path: Path, install: Callable[..., Path]
    ) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("host secret")
        change = {
            "type": "item.completed",
            "item": {
                "id": "f1",
                "type": "file_change",
                "status": "completed",
                "changes": [
                    {"path": "link.txt", "kind": "add"},
                    {"path": str(outside), "kind": "update"},
                    {"path": "../outside.txt", "kind": "update"},
                    {"path": ".git/config", "kind": "update"},
                ],
            },
        }
        session = self._run_codex(
            ws,
            install,
            lines=codex_lines("ok", change),
            pre=f"ln -s {outside} link.txt\nmkdir -p .git; echo x > .git/config\n",
        )
        assert ok(call("GET", f"/v1/agents/sessions/{session['id']}/artifacts"))["data"] == []

    def test_deleted_paths_are_not_snapshotted(
        self, ws: Path, install: Callable[..., Path]
    ) -> None:
        change = {
            "type": "item.completed",
            "item": {
                "id": "f1",
                "type": "file_change",
                "status": "completed",
                "changes": [{"path": "gone.txt", "kind": "delete"}],
            },
        }
        session = self._run_codex(ws, install, lines=codex_lines("ok", change), pre="")
        assert ok(call("GET", f"/v1/agents/sessions/{session['id']}/artifacts"))["data"] == []

    def test_qwen_write_file_tool_input_is_reported(
        self, ws: Path, install: Callable[..., Path]
    ) -> None:
        target = ws / "notes.md"
        lines = qwen_lines(
            "wrote",
            {
                "type": "assistant",
                "message": {
                    "id": "m0",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tu1",
                            "name": "write_file",
                            "input": {"file_path": str(target), "content": "hi"},
                        }
                    ],
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "tool_use_id": "tu1", "content": "ok"}]
                },
            },
        )
        install("qwen", _script(lines, pre="printf 'qwen-bytes' > notes.md\n"))
        session = new_session(ws, adapter="qwen-code")
        send(session["id"])
        wait_idle(session["id"])
        rows = ok(call("GET", f"/v1/agents/sessions/{session['id']}/artifacts"))["data"]
        assert [r["path"] for r in rows] == ["/workspace/notes.md"]
        content = call(
            "GET", f"/v1/agents/sessions/{session['id']}/artifacts/{rows[0]['id']}/content"
        )
        assert b"".join(content.event_iterator) == b"qwen-bytes"

    def test_failed_turn_publishes_nothing_and_env_filter(
        self, ws: Path, install: Callable[..., Path]
    ) -> None:
        session = self._run_codex(ws, install)
        base = f"/v1/agents/sessions/{session['id']}/artifacts"
        assert ok(call("GET", f"{base}?environment_id=env_other"))["data"] == []
        assert len(ok(call("GET", f"{base}?environment_id=env_easy_sandbox"))["data"]) == 1
        ok(call("DELETE", f"/v1/agents/sessions/{session['id']}"))
        refused(call("GET", base), 404)


class TestTraces:
    def test_empty_by_default_and_timing_only_when_enabled(
        self, ws: Path, monkeypatch: pytest.MonkeyPatch, install: Callable[..., Path]
    ) -> None:
        install(
            "codex",
            _script(
                codex_lines(
                    "ran",
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "c1",
                            "type": "command_execution",
                            "command": f"echo {CANARY}",
                            "status": "completed",
                            "exit_code": 0,
                            "aggregated_output": CANARY,
                        },
                    },
                )
            ),
        )
        session = new_session(ws)
        send(session["id"])
        wait_idle(session["id"])
        url = f"/v1/agents/sessions/{session['id']}/traces"
        assert ok(call("GET", url))["data"] == []
        monkeypatch.setenv("EBX_AGENTS_TRACES", "1")
        traces = ok(call("GET", url))["data"]
        assert len(traces) == 1
        trace = traces[0]
        assert trace["object"] == "agent.session.trace"
        assert trace["x_easy_sandbox"]["differences"] == ["trace_from_journal_timing_only"]
        assert CANARY not in json.dumps(trace) and "echo" not in json.dumps(trace)
        span = trace["otlp"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert int(span["endTimeUnixNano"]) >= int(span["startTimeUnixNano"])
        keys = {a["key"] for a in span["attributes"]}
        assert keys == {"turn.status", "turn.items"}


# ---------------------------------------------------------------------- #
# A-32..A-37 subagents
# ---------------------------------------------------------------------- #


def write_rollout(home: Path, thread: str, rows: list[Any]) -> Path:
    directory = home / "sessions" / "2026" / "10" / "12"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"rollout-2026-10-12T00-00-00-{thread}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _resp(ptype: str, **payload: Any) -> dict[str, Any]:
    return {"type": "response_item", "payload": {"type": ptype, **payload}}


CHILD_ROLLOUT = [
    {"type": "session_meta", "payload": {"id": "thr-child-0001"}},
    {"type": "turn_context", "payload": {"turn_id": "ct-1"}},
    _resp("message", role="user", content=[{"type": "input_text", "text": "child task"}]),
    _resp("function_call", name="shell", arguments='{"cmd":"ls"}', call_id="c1"),
    _resp("function_call_output", call_id="c1", output="file.txt"),
    _resp("message", role="assistant", content=[{"type": "output_text", "text": "child done"}]),
    {"type": "turn_context", "payload": {"turn_id": "ct-2"}},
    _resp("message", role="user", content=[{"type": "input_text", "text": f"second {CANARY}"}]),
    _resp("message", role="assistant", content=[{"type": "output_text", "text": "child two"}]),
]


class TestSubagents:
    def test_none_means_empty_and_unknown_ids_are_404(self, ws: Path) -> None:
        session = new_session(ws)
        assert ok(call("GET", f"/v1/agents/sessions/{session['id']}/subagents"))["data"] == []
        base = f"/v1/agents/sessions/{session['id']}/subagents/nope-123456"
        for tail in ("", "/items", "/turns", "/turns/t1", "/turns/t1/items"):
            refused(call("GET", base + tail), 404, code="resource_not_found")

    def test_codex_ids_from_exec_jsonl_and_child_rollout(
        self,
        ws: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        install: Callable[..., Path],
    ) -> None:
        home = tmp_path / "codex-home"
        monkeypatch.setenv("CODEX_HOME", str(home))
        write_rollout(home, "thr-child-0001", CHILD_ROLLOUT)
        write_rollout(home, "thr-unrelated-9", CHILD_ROLLOUT)
        collab = {
            "type": "item.completed",
            "item": {
                "id": "k1",
                "type": "collab_tool_call",
                "tool": "spawn_agent",
                "sender_thread_id": "thr-parent-0001",
                "receiver_thread_ids": ["thr-child-0001"],
                "prompt": "do the child task",
                "status": "completed",
                "agents_states": {"thr-child-0001": {"status": "running"}},
            },
        }
        install("codex", _script(codex_lines("parent", collab)))
        reset_agent_runtime()
        session = new_session(ws)
        send(session["id"])
        wait_idle(session["id"])
        base = f"/v1/agents/sessions/{session['id']}/subagents"
        listing = ok(call("GET", base))["data"]
        assert [s["id"] for s in listing] == ["thr-child-0001"]
        sub = listing[0]
        assert sub["object"] == "agent.session.subagent"
        assert sub["session_id"] == session["id"]
        assert sub["parent_agent_id"] == session["agent"]["id"]
        assert sub["status"] == "active"
        assert sub["instructions"] == [{"type": "input_text", "text": "do the child task"}]
        assert sub["x_easy_sandbox"]["differences"] == ["ids_from_cli_only"]
        assert ok(call("GET", f"{base}/thr-child-0001")) == sub
        refused(call("GET", f"{base}/thr-unrelated-9"), 404)
        turns = ok(call("GET", f"{base}/thr-child-0001/turns?order=asc"))["data"]
        assert [t["id"] for t in turns] == ["ct-1", "ct-2"]
        assert all(t["subagent_id"] == "thr-child-0001" for t in turns)
        assert "turns_from_rollout" in turns[0]["x_easy_sandbox"]["differences"]
        assert ok(call("GET", f"{base}/thr-child-0001/turns/ct-2"))["id"] == "ct-2"
        refused(call("GET", f"{base}/thr-child-0001/turns/ct-9"), 404)
        items = ok(call("GET", f"{base}/thr-child-0001/items?order=asc"))["data"]
        assert [i["type"] for i in items] == [
            "message",
            "tool_call",
            "message",
            "message",
            "message",
        ]
        assert items[1]["tool_name"] == "shell" and items[1]["output"] == "file.txt"
        assert items[0]["role"] == "user" and items[2]["content"][0]["text"] == "child done"
        in_turn = ok(call("GET", f"{base}/thr-child-0001/turns/ct-1/items?order=asc"))["data"]
        assert [i["id"] for i in in_turn] == [i["id"] for i in items[:3]]
        assert all(i["turn_id"] == "ct-1" for i in in_turn)
        parent_items = ok(call("GET", f"/v1/agents/sessions/{session['id']}/items"))["data"]
        assert all("child" not in json.dumps(i) for i in parent_items)

    def test_codex_id_only_in_the_session_rollout(
        self, ws: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home = tmp_path / "codex-home"
        monkeypatch.setenv("CODEX_HOME", str(home))
        write_rollout(
            home,
            "thr-parent-0001",
            [
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "collab_agent_spawn_end",
                        "receiver_thread_ids": ["thr-child-0001"],
                    },
                },
            ],
        )
        write_rollout(home, "thr-child-0001", CHILD_ROLLOUT)
        write_rollout(home, "thr-other-0002", CHILD_ROLLOUT)
        reset_agent_runtime()
        session = new_session(ws)
        send(session["id"])
        wait_idle(session["id"])
        listing = ok(call("GET", f"/v1/agents/sessions/{session['id']}/subagents"))["data"]
        assert [s["id"] for s in listing] == ["thr-child-0001"]

    def test_codex_rollout_ids_are_validated_before_touching_the_filesystem(
        self, ws: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home = tmp_path / "codex-home"
        monkeypatch.setenv("CODEX_HOME", str(home))
        write_rollout(
            home,
            "thr-parent-0001",
            [
                {
                    "type": "event_msg",
                    "payload": {"receiver_thread_ids": ["../../etc/passwd", "*"]},
                },
            ],
        )
        reset_agent_runtime()
        session = new_session(ws)
        send(session["id"])
        wait_idle(session["id"])
        assert ok(call("GET", f"/v1/agents/sessions/{session['id']}/subagents"))["data"] == []

    def test_qwen_parent_tool_use_id_streams(self, ws: Path, install: Callable[..., Path]) -> None:
        parent_use = {
            "type": "assistant",
            "message": {
                "id": "p1",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_agent1",
                        "name": "agent",
                        "input": {
                            "description": "researcher",
                            "prompt": "find things",
                            "subagent_type": "general",
                        },
                    }
                ],
            },
        }

        def child(role: str, content: Any) -> dict[str, Any]:
            return {
                "type": role,
                "parent_tool_use_id": "toolu_agent1",
                "message": {"id": f"c-{role}", "content": content},
            }

        lines = [
            {"type": "system", "subtype": "init", "session_id": "qs-1"},
            parent_use,
            child("user", [{"type": "text", "text": "find things"}]),
            child(
                "assistant",
                [{"type": "tool_use", "id": "toolu_c1", "name": "read_file", "input": {"p": "a"}}],
            ),
            child("user", [{"type": "tool_result", "tool_use_id": "toolu_c1", "content": "data"}]),
            child("assistant", [{"type": "text", "text": "found one"}]),
            child("user", [{"type": "text", "text": f"more {CANARY}"}]),
            child("assistant", [{"type": "text", "text": "found two"}]),
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_agent1", "content": "done"}
                    ]
                },
            },
            {
                "type": "assistant",
                "message": {"id": "p2", "content": [{"type": "text", "text": "parent final"}]},
            },
            {"type": "result", "subtype": "success", "is_error": False, "result": "parent final"},
        ]
        install("qwen", _script(lines))
        session = new_session(ws, adapter="qwen-code")
        send(session["id"])
        wait_idle(session["id"])
        base = f"/v1/agents/sessions/{session['id']}/subagents"
        listing = ok(call("GET", base))["data"]
        assert [s["id"] for s in listing] == ["toolu_agent1"]
        assert listing[0]["name"] == "researcher"
        assert listing[0]["status"] == "closed"
        turns = ok(call("GET", f"{base}/toolu_agent1/turns?order=asc"))["data"]
        assert len(turns) == 2
        assert all(t["status"] == "completed" for t in turns)
        assert "turns_grouped_from_parent_stream" in turns[0]["x_easy_sandbox"]["differences"]
        items = ok(call("GET", f"{base}/toolu_agent1/items?order=asc"))["data"]
        assert [i["type"] for i in items] == [
            "message",
            "tool_call",
            "message",
            "message",
            "message",
        ]
        assert items[1]["tool_name"] == "read_file" and items[1]["output"] == "data"
        assert items[1]["status"] == "completed"
        first_turn_items = ok(
            call("GET", f"{base}/toolu_agent1/turns/{turns[0]['id']}/items?order=asc")
        )["data"]
        assert len(first_turn_items) == 3
        assert (
            ok(call("GET", f"{base}/toolu_agent1/turns/{turns[1]['id']}"))["id"] == turns[1]["id"]
        )
        assert CANARY in json.dumps(items)
        parent = ok(call("GET", f"/v1/agents/sessions/{session['id']}/items?order=asc"))["data"]
        assert "read_file" not in json.dumps(parent) and "found one" not in json.dumps(parent)
        assert any("parent final" in json.dumps(i) for i in parent)


# ---------------------------------------------------------------------- #
# R-01..R-05, R-07, R-08 responses
# ---------------------------------------------------------------------- #


def create_response(**body: Any) -> dict[str, Any]:
    body.setdefault("model", "codex")
    body.setdefault("input", "hello")
    return ok(call("POST", "/v1/responses", body))


class TestResponses:
    def test_create_retrieve_input_items_delete(self) -> None:
        response = create_response(
            model="gpt-5-codex",
            adapter="codex",
            instructions="be terse",
            metadata={"k": "v"},
            input=[
                {"role": "developer", "content": "rules"},
                {"role": "user", "content": [{"type": "input_text", "text": "hello there"}]},
            ],
        )
        assert response["object"] == "response"
        assert response["id"].startswith("resp_")
        assert response["status"] == "completed"
        assert response["model"] == "gpt-5-codex"
        assert response["x_easy_sandbox"]["model_resolved"] is True
        assert response["x_easy_sandbox"]["compute"] == "local_process"
        assert response["metadata"] == {"k": "v"}
        assert response["tools"] == []
        assert response["usage"]["input_tokens"] == 3
        assert response["incomplete_details"] is None
        message = response["output"][0]
        assert message["type"] == "message" and message["role"] == "assistant"
        assert message["content"][0]["text"] == "codex-fake-ok"
        got = ok(call("GET", f"/v1/responses/{response['id']}"))
        assert got["id"] == response["id"] and got["output"] == response["output"]
        items = ok(call("GET", f"/v1/responses/{response['id']}/input_items?order=asc"))["data"]
        assert [i["role"] for i in items] == ["developer", "user"]
        assert items[1]["content"] == [{"type": "input_text", "text": "hello there"}]
        deleted = ok(call("DELETE", f"/v1/responses/{response['id']}"))
        assert deleted["deleted"] is True
        refused(call("GET", f"/v1/responses/{response['id']}"), 404, code="resource_not_found")
        refused(call("GET", f"/v1/responses/{response['id']}/input_items"), 404)
        refused(call("POST", f"/v1/responses/{response['id']}/cancel"), 404)
        assert ok(call("GET", "/v1/agents/sessions"))["data"] == []

    def test_model_alias_is_not_a_model_and_says_so(self) -> None:
        response = create_response(model="qwen")
        assert response["model"] == "qwen-code"
        assert response["x_easy_sandbox"]["model_resolved"] is False
        assert response["output"][0]["content"][0]["text"] == "qwen-fake-ok"

    def test_model_selects_a_stored_definition(self, ws: Path) -> None:
        agent = ok(
            call(
                "POST",
                "/v1/agents",
                {"model": "gpt-5-codex", "adapter": "codex", "instructions": "x"},
            )
        )
        response = create_response(model=agent["id"])
        assert response["model"] == "gpt-5-codex"
        assert response["status"] == "completed"

    def test_openai_ids_and_foreign_ids_are_404(self) -> None:
        mine = create_response()
        refused(call("GET", "/v1/responses/resp_68a1b2c3d4e5f60718293a4b5c6d7e8f9"), 404)
        refused(call("GET", f"/v1/responses/{mine['id']}", principal="bob"), 404)
        refused(call("DELETE", f"/v1/responses/{mine['id']}", principal="bob"), 404)
        refused(call("GET", f"/v1/responses/{mine['id']}/input_items", principal="bob"), 404)
        assert ok(call("GET", f"/v1/responses/{mine['id']}"))["id"] == mine["id"]

    @pytest.mark.parametrize(
        ("patch", "param"),
        [
            ({"tools": [{"type": "web_search"}]}, "tools[0].type"),
            ({"tools": [{"type": "function", "name": "f"}]}, "tools[0].type"),
            (
                {
                    "tools": [
                        {
                            "type": "mcp",
                            "server_label": "x",
                            "server_url": MCP_URL,
                            "allowed_tools": ["a"],
                        }
                    ]
                },
                "tools[0].allowed_tools",
            ),
            ({"conversation": "conv_1"}, "conversation"),
            ({"prompt": {"id": "p"}}, "prompt"),
            (
                {"text": {"format": {"type": "json_schema", "name": "x", "schema": {}}}},
                "text.format",
            ),
            ({"include": ["reasoning.encrypted_content"]}, "include"),
            ({"service_tier": "priority"}, "service_tier"),
            ({"tool_choice": "required"}, "tool_choice"),
            ({"unknown_field": 1}, "unknown_field"),
            (
                {
                    "input": [
                        {"role": "user", "content": [{"type": "input_image", "image_url": "x"}]}
                    ]
                },
                "input[0].content[0].type",
            ),
            (
                {"input": [{"role": "user", "content": [{"type": "input_file", "file_id": "f"}]}]},
                "input[0].content[0].type",
            ),
            ({"input": [{"role": "assistant", "content": "x"}]}, "input[0].role"),
            (
                {"input": [{"type": "function_call_output", "call_id": "c", "output": "x"}]},
                "input[0].type",
            ),
            ({"input": None}, "input"),
            ({"background": True, "store": False}, "background"),
            ({"previous_response_id": "resp_missing"}, "previous_response_id"),
            ({"metadata": {"k": 1}}, "metadata.k"),
        ],
    )
    def test_variant_refusals_are_400(self, patch: dict[str, Any], param: str) -> None:
        body = {"model": "codex", "input": "hi", **patch}
        response = call("POST", "/v1/responses", body)
        status = 404 if param == "previous_response_id" else 400
        refused(response, status, param=param)

    def test_ignored_sampling_params_are_listed_in_a_header(self) -> None:
        response = call(
            "POST",
            "/v1/responses",
            {
                "model": "codex",
                "input": "x",
                "temperature": 0.2,
                "top_p": 0.9,
                "max_output_tokens": 5,
            },
        )
        assert response.status == 200
        header = response.headers["X-Easy-Sandbox-Ignored-Params"]
        assert set(header.split(",")) == {"temperature", "top_p", "max_output_tokens"}

    def test_adapter_required_without_default(self) -> None:
        refused(
            call("POST", "/v1/responses", {"model": "gpt-5", "input": "x"}),
            400,
            code="agents.adapter_required",
        )

    def test_previous_response_continues_the_cli_session_only_from_the_latest(
        self, install: Callable[..., Path], tmp_path: Path
    ) -> None:
        install("codex", _script(codex_lines(), pre=DUMP))
        first = create_response(adapter="codex")
        second = create_response(adapter="codex", previous_response_id=first["id"])
        assert second["previous_response_id"] == first["id"]
        argv = (tmp_path / "responses-ws" / "argv.txt").read_text().splitlines()
        assert argv[:2] == ["exec", "resume"] and argv[2] == "thr-parent-0001"
        refused(
            call(
                "POST",
                "/v1/responses",
                {"model": "codex", "input": "x", "previous_response_id": first["id"]},
            ),
            400,
            param="previous_response_id",
            code="agents.previous_response_not_latest",
        )
        ok(call("DELETE", f"/v1/responses/{second['id']}"))
        assert ok(call("GET", f"/v1/responses/{first['id']}"))["status"] == "completed"

    def test_native_tools_are_never_shaped_as_hosted_tools(
        self, install: Callable[..., Path]
    ) -> None:
        extra = [
            {
                "type": "item.completed",
                "item": {
                    "id": "w1",
                    "type": "web_search",
                    "query": "q",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "c1",
                    "type": "command_execution",
                    "command": "ls",
                    "status": "completed",
                    "exit_code": 0,
                    "aggregated_output": "files",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "t1",
                    "type": "mcp_tool_call",
                    "server": "docs",
                    "tool": "lookup",
                    "arguments": {"a": 1},
                    "status": "completed",
                    "result": {"ok": True},
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "f1",
                    "type": "file_change",
                    "status": "completed",
                    "changes": [{"path": "a.txt", "kind": "add"}],
                },
            },
        ]
        install("codex", _script(codex_lines("all", *extra)))
        output = create_response(adapter="codex")["output"]
        kinds = [o["type"] for o in output]
        assert kinds.count("command_execution") == 1
        assert kinds.count("mcp_call") == 1
        assert kinds.count("tool_call") == 2
        assert "web_search_call" not in kinds and "function_call" not in kinds
        assert "local_shell_call" not in kinds and "code_interpreter_call" not in kinds
        names = {o.get("tool_name") for o in output if o["type"] == "tool_call"}
        assert names == {"web_search", "file_change"}
        mcp = next(o for o in output if o["type"] == "mcp_call")
        assert mcp["server_label"] == "docs" and mcp["name"] == "lookup"
        for item in output:
            if item["type"] != "message":
                assert item["x_easy_sandbox"]["local"] is True

    def test_failed_turn_reports_failed_not_completed(self, install: Callable[..., Path]) -> None:
        install("codex", _script([{"type": "thread.started", "thread_id": "t"}], exit_code=3))
        response = create_response(adapter="codex")
        assert response["status"] == "failed"
        assert response["error"]["code"] == "server_error"
        assert response["completed_at"] is None

    def test_unknown_usage_is_null(self, install: Callable[..., Path]) -> None:
        install(
            "codex",
            _script(
                [
                    {
                        "type": "item.completed",
                        "item": {"id": "m", "type": "agent_message", "text": "hi"},
                    },
                    {"type": "turn.completed"},
                ]
            ),
        )
        assert create_response(adapter="codex")["usage"] is None

    def test_mcp_tool_secrets_are_write_only(
        self, install: Callable[..., Path], tmp_path: Path
    ) -> None:
        install("codex", _script(codex_lines(), pre=DUMP))
        tool = {
            "type": "mcp",
            "server_label": "docs",
            "server_url": MCP_URL,
            "headers": {"X-Api-Key": CANARY},
            "authorization": CANARY + "-oauth",
        }
        body = {"model": "codex", "input": "x", "tools": [tool]}
        response = call("POST", "/v1/responses", body)
        data = ok(response)
        assert data["tools"] == [{"type": "mcp", "server_label": "docs", "server_url": MCP_URL}]
        assert CANARY not in json.dumps(data)
        ws = tmp_path / "responses-ws"
        assert CANARY not in (ws / "argv.txt").read_text()
        env_dump = (ws / "env.txt").read_text()
        assert f"Bearer {CANARY}-oauth" in env_dump
        assert CANARY not in json.dumps(ok(call("GET", f"/v1/responses/{data['id']}")))
        items = ok(call("GET", f"/v1/responses/{data['id']}/input_items"))
        assert CANARY not in json.dumps(items)

    def test_store_false_is_not_retrievable(self) -> None:
        response = create_response(store=False)
        assert response["store"] is False
        deadline = time.time() + 5
        while time.time() < deadline:
            if call("GET", f"/v1/responses/{response['id']}").status == 404:
                break
            time.sleep(0.05)
        refused(call("GET", f"/v1/responses/{response['id']}"), 404)
        assert get_agent_runtime().list_sessions() == []

    def test_idempotency_key_replays_the_same_response(self) -> None:
        body = {"model": "codex", "input": "once", "adapter": "codex"}
        headers = {"Idempotency-Key": "key-1"}
        first = ok(call("POST", "/v1/responses", body, headers=headers))
        second = ok(call("POST", "/v1/responses", body, headers=headers))
        assert first["id"] == second["id"]
        assert len(ok(call("GET", "/v1/agents/sessions"))["data"]) == 0
        mismatch = call("POST", "/v1/responses", {**body, "input": "other"}, headers=headers)
        refused(mismatch, 409, code="idempotency.mismatch")

    def test_background_then_cancel(self, install: Callable[..., Path]) -> None:
        install("codex", "#!/bin/sh\ncat >/dev/null\nsleep 30\n")
        response = create_response(adapter="codex", background=True)
        assert response["background"] is True
        assert response["status"] in ("queued", "in_progress")
        assert ok(call("GET", f"/v1/responses/{response['id']}"))["status"] in (
            "queued",
            "in_progress",
        )
        cancelled = ok(call("POST", f"/v1/responses/{response['id']}/cancel"))
        assert cancelled["status"] == "cancelled"
        refused(
            call("POST", f"/v1/responses/{response['id']}/cancel"),
            400,
            code="agents.not_cancellable",
        )

    def test_cancel_of_a_finished_response_is_400_not_409(self) -> None:
        response = create_response()
        error = refused(
            call("POST", f"/v1/responses/{response['id']}/cancel"),
            400,
            code="agents.not_cancellable",
        )
        assert "completed" in error["message"]

    def test_stream_replays_the_turn_with_official_event_names(self) -> None:
        stream = call("POST", "/v1/responses", {"model": "codex", "input": "s", "stream": True})
        assert isinstance(stream, SSEResponse)
        assert stream.headers["X-Easy-Sandbox-Local"] == "1"
        events = sse_events(stream)
        types_ = [e["type"] for e in events]
        assert types_[:2] == ["response.created", "response.in_progress"]
        assert "response.output_text.delta" in types_
        assert types_[-1] == "response.completed"
        assert [e["sequence_number"] for e in events] == list(range(len(events)))
        delta = next(e for e in events if e["type"] == "response.output_text.delta")
        assert delta["delta"] == "codex-fake-ok"
        final = events[-1]["response"]
        assert final["status"] == "completed" and final["usage"]["input_tokens"] == 3
        assert events[0]["response"]["status"] == "in_progress"
        assert events[0]["response"]["output"] == []
        assert (
            "stream_replayed_after_turn" in events[0]["response"]["x_easy_sandbox"]["differences"]
        )
        assert "stream_replayed_after_turn" in final["x_easy_sandbox"]["differences"]
        rid = final["id"]
        replay = sse_events(call("GET", f"/v1/responses/{rid}?stream=true&starting_after=3"))
        assert replay[0]["sequence_number"] == 4
        assert replay[-1]["type"] == "response.completed"
        refused(
            call("GET", f"/v1/responses/{rid}?stream=true&starting_after=x"),
            400,
            param="starting_after",
        )

    def test_socket_engine_create_and_queued_steer(self) -> None:
        request = ServerRequest(method="GET", path="/v1/responses")
        engine = ResponsesSocket(request)
        events = engine.handle({"type": "response.create", "model": "codex", "input": "a"})
        assert (
            events[0]["type"] == "response.created" and events[-1]["type"] == "response.completed"
        )
        first = events[-1]["response"]
        steered = engine.handle(
            {
                "type": "response.steer",
                "model": "codex",
                "input": "b",
                "previous_response_id": first["id"],
            }
        )
        final = steered[-1]["response"]
        assert final["previous_response_id"] == first["id"]
        assert "queued_steer" in final["x_easy_sandbox"]["differences"]
        bad = engine.handle(
            {
                "type": "response.create",
                "model": "codex",
                "input": "x",
                "tools": [{"type": "web_search"}],
            }
        )
        assert bad[0]["type"] == "error"

    def test_connect_without_upgrade_is_an_explicit_400(self) -> None:
        refused(call("GET", "/v1/responses"), 400, code="agents.websocket_upgrade_required")


class TestCompact:
    def test_qwen_compress_summary_is_labeled(self, install: Callable[..., Path]) -> None:
        install("qwen", _script(qwen_lines('{"originalTokenCount": 900, "newTokenCount": 120}')))
        first = create_response(model="qwen")
        compacted = ok(
            call(
                "POST",
                "/v1/responses/compact",
                {"model": "qwen", "previous_response_id": first["id"]},
            )
        )
        assert compacted["object"] == "response.compaction"
        assert compacted["id"].startswith("resp_cmp_")
        assert compacted["output"][0]["type"] == "message"
        label_ = compacted["x_easy_sandbox"]
        assert "summary_not_encrypted_compaction" in label_["differences"]
        assert label_["original_token_count"] == 900 and label_["new_token_count"] == 120
        assert ok(call("GET", f"/v1/responses/{first['id']}"))["id"] == first["id"]

    def test_codex_is_400_until_it_emits_a_compaction_item(self) -> None:
        first = create_response(adapter="codex")
        refused(
            call(
                "POST",
                "/v1/responses/compact",
                {"model": "codex", "previous_response_id": first["id"]},
            ),
            400,
            code="agents.compact_unsupported",
        )

    def test_previous_response_is_required(self) -> None:
        refused(
            call("POST", "/v1/responses/compact", {"model": "qwen"}),
            400,
            param="previous_response_id",
        )
        refused(
            call(
                "POST",
                "/v1/responses/compact",
                {"model": "qwen", "previous_response_id": "resp_nope"},
            ),
            404,
        )


# ---------------------------------------------------------------------- #
# O-01, O-02 models; O-06..O-14 webhooks
# ---------------------------------------------------------------------- #


class TestModels:
    def test_list_and_retrieve_are_local_and_side_effect_free(self) -> None:
        agent = ok(call("POST", "/v1/agents", {"model": "gpt-5-codex", "adapter": "codex"}))
        listing = ok(call("GET", "/v1/models"))
        assert listing["object"] == "list"
        by_id = {m["id"]: m for m in listing["data"]}
        assert set(by_id) == {agent["id"], "codex", "qwen-code"}
        for model in listing["data"]:
            assert model["object"] == "model" and model["owned_by"] == "easy-sandbox-local"
            assert model["x_easy_sandbox"]["compute"] == "none"
        assert by_id["codex"]["x_easy_sandbox"] == {
            "local": True,
            "compute": "none",
            "differences": [],
            "kind": "adapter",
            "installed": True,
        }
        assert by_id[agent["id"]]["x_easy_sandbox"]["kind"] == "agent_definition"
        assert ok(call("GET", "/v1/models/codex"))["id"] == "codex"
        assert "gpt-4o" not in by_id
        error = refused(call("GET", "/v1/models/gpt-4o"), 404, code="model_not_found")
        assert error["type"] == "not_found_error"
        assert get_agent_runtime().store.list() == []
        assert all(
            m["id"] != agent["id"] for m in ok(call("GET", "/v1/models", principal="bob"))["data"]
        )

    def test_adapter_not_on_path_is_listed_as_not_installed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setenv("PATH", str(empty))
        reset_agent_runtime()
        by_id = {m["id"]: m for m in ok(call("GET", "/v1/models"))["data"]}
        assert by_id["codex"]["x_easy_sandbox"]["installed"] is False


class _Receiver:
    def __init__(self) -> None:
        self.events: list[tuple[dict[str, str], bytes]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                outer.events.append(
                    ({k.lower(): v for k, v in self.headers.items()}, self.rfile.read(length))
                )
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args: Any) -> None:
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/hook"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()


@pytest.fixture
def receiver(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("EBX_AGENTS_ALLOW_PRIVATE_URLS", "1")
    monkeypatch.setenv("EBX_AGENTS_WEBHOOK_ALLOW_HTTP", "1")
    rec = _Receiver()
    yield rec
    rec.close()


def verify(secret: str, headers: dict[str, str], payload: bytes) -> bool:
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{headers['webhook-id']}.{headers['webhook-timestamp']}.".encode() + payload
    expected = "v1," + base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, headers["webhook-signature"])


class TestWebhooks:
    def test_endpoint_crud_secret_shown_once(self, receiver: _Receiver) -> None:
        created = ok(
            call(
                "POST",
                "/v1/webhook_endpoints",
                {"url": receiver.url, "event_types": ["agent.session.idle"], "name": "w"},
            )
        )
        secret = created["signing_secret"]
        assert secret.startswith("whsec_") and created["object"] == "webhook_endpoint"
        assert created["signing_secret_hint"] is None
        wid = created["id"]
        for body in (
            ok(call("GET", f"/v1/webhook_endpoints/{wid}")),
            ok(call("GET", "/v1/webhook_endpoints")),
        ):
            assert secret not in json.dumps(body) and '"signing_secret"' not in json.dumps(body)
        updated = ok(
            call(
                "POST",
                f"/v1/webhook_endpoints/{wid}",
                {"event_types": ["agent.session.idle", "agent.session.failed"], "name": "n"},
            )
        )
        assert updated["name"] == "n" and len(updated["event_types"]) == 2
        rotated = ok(call("POST", f"/v1/webhook_endpoints/{wid}/rotate_secret", {}))
        assert rotated["signing_secret"] != secret
        refused(
            call(
                "POST",
                f"/v1/webhook_endpoints/{wid}/rotate_secret",
                {"keep_old_secret_active_for_24_hours": True},
            ),
            400,
            param="keep_old_secret_active_for_24_hours",
        )
        refused(call("GET", f"/v1/webhook_endpoints/{wid}", principal="bob"), 404)
        deleted = ok(call("DELETE", f"/v1/webhook_endpoints/{wid}"))
        assert deleted["object"] == "webhook_endpoint.deleted"
        refused(call("GET", f"/v1/webhook_endpoints/{wid}"), 404)

    def test_event_types_are_those_actually_sent(self) -> None:
        listing = ok(call("GET", "/v1/webhook_event_types"))
        assert listing["object"] == "list"
        assert "agent.session.action_required" not in listing["data"]
        assert "agent.session.idle" in listing["data"]
        refused(
            call(
                "POST",
                "/v1/webhook_endpoints",
                {"url": "https://example.com/h", "event_types": ["agent.session.action_required"]},
            ),
            400,
            param="event_types",
        )

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/h",
            "https://127.0.0.1/h",
            "https://user:pw@example.com/h",
            "https://example.com/h?token=1",
            "ftp://example.com/h",
        ],
    )
    def test_urls_are_admitted_strictly(self, url: str) -> None:
        refused(
            call(
                "POST", "/v1/webhook_endpoints", {"url": url, "event_types": ["agent.session.idle"]}
            ),
            400,
            param="url",
        )

    def test_test_event_is_signed_and_verifiable(self, receiver: _Receiver) -> None:
        created = ok(
            call(
                "POST",
                "/v1/webhook_endpoints",
                {"url": receiver.url, "event_types": ["agent.session.idle"]},
            )
        )
        result = ok(
            call(
                "POST",
                f"/v1/webhook_endpoints/{created['id']}/test",
                {"event_type": "agent.session.idle"},
            )
        )
        assert result["status_code"] == 204 and result["success"] is True
        assert result["webhook_endpoint_id"] == created["id"]
        headers, payload = receiver.events[0]
        assert verify(created["signing_secret"], headers, payload)
        event = json.loads(payload)
        assert event["type"] == "agent.session.idle" and event["object"] == "event"
        refused(
            call(
                "POST",
                f"/v1/webhook_endpoints/{created['id']}/test",
                {"event_type": "nope"},
            ),
            400,
            param="event_type",
        )

    def test_unreachable_receiver_is_400_not_a_fake_success(self, receiver: _Receiver) -> None:
        created = ok(
            call(
                "POST",
                "/v1/webhook_endpoints",
                {"url": "http://127.0.0.1:9/hook", "event_types": ["agent.session.idle"]},
            )
        )
        refused(
            call(
                "POST",
                f"/v1/webhook_endpoints/{created['id']}/test",
                {"event_type": "agent.session.idle"},
            ),
            400,
            code="agents.webhook_delivery_failed",
        )

    def test_session_lifecycle_events_are_delivered(self, ws: Path, receiver: _Receiver) -> None:
        created = ok(
            call(
                "POST",
                "/v1/webhook_endpoints",
                {
                    "url": receiver.url,
                    "event_types": [
                        "agent.session.created",
                        "agent.session.in_progress",
                        "agent.session.idle",
                    ],
                },
            )
        )
        session = new_session(ws)
        send(session["id"])
        wait_idle(session["id"])
        deadline = time.time() + 10
        while time.time() < deadline and len(receiver.events) < 3:
            time.sleep(0.05)
        seen = {json.loads(p)["type"] for _, p in receiver.events}
        assert seen == {
            "agent.session.created",
            "agent.session.in_progress",
            "agent.session.idle",
        }
        for headers, payload in receiver.events:
            assert verify(created["signing_secret"], headers, payload)
            assert json.loads(payload)["data"]["id"] == session["id"]

    def test_other_principals_get_no_events(self, ws: Path, receiver: _Receiver) -> None:
        ok(
            call(
                "POST",
                "/v1/webhook_endpoints",
                {"url": receiver.url, "event_types": ["agent.session.created"]},
                principal="alice",
            )
        )
        new_session(ws)
        time.sleep(0.3)
        assert receiver.events == []


# ---------------------------------------------------------------------- #
# Live HTTP sweep
# ---------------------------------------------------------------------- #


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _serve(port: int, *, enable: bool = True) -> ThreadingHTTPServer:
    if enable:
        default_table().enable_group(CapabilityGroup.AGENTS)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), SandboxRequestHandler)
    httpd.auth_token = None  # type: ignore[attr-defined]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.05)
    return httpd


def _http(
    port: int, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None
) -> tuple[int, Any, dict[str, str]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    payload = json.dumps(body).encode() if body is not None else None
    conn.request(
        method, path, body=payload, headers={"Content-Type": "application/json", **(headers or {})}
    )
    resp = conn.getresponse()
    raw = resp.read()
    out_headers = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    return (
        resp.status,
        (json.loads(raw) if raw and "json" in out_headers.get("content-type", "") else raw),
        out_headers,
    )


class TestOverHttp:
    def test_new_routes_over_the_wire(self, ws: Path, install: Callable[..., Path]) -> None:
        install(
            "codex",
            _script(
                codex_lines(
                    "artifact done",
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "f1",
                            "type": "file_change",
                            "status": "completed",
                            "changes": [{"path": "out.txt", "kind": "add"}],
                        },
                    },
                ),
                pre="printf 'wire-bytes' > out.txt\n",
            ),
        )
        port = _free_port()
        httpd = _serve(port)
        try:
            status, agent, headers = _http(
                port, "POST", "/v1/agents", {"model": "m", "adapter": "codex"}
            )
            assert status == 200 and headers["x-easy-sandbox-local"] == "1"
            status, session, _ = _http(
                port,
                "POST",
                "/v1/agents/sessions",
                {
                    "agent_id": agent["id"],
                    "environment": {"type": "self_hosted", "workspace_directory": str(ws)},
                },
            )
            assert status == 200, session
            status, raw, _ = _http(
                port,
                "POST",
                f"/v1/agents/sessions/{session['id']}/events",
                {"events": [{"type": "agent.session.input.message", "input": "go"}]},
            )
            assert status == 202 and raw == b""
            wait_idle(session["id"])
            status, listing, _ = _http(
                port, "GET", f"/v1/agents/sessions/{session['id']}/artifacts"
            )
            assert status == 200 and len(listing["data"]) == 1
            art = listing["data"][0]
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request(
                "GET", f"/v1/agents/sessions/{session['id']}/artifacts/{art['id']}/content"
            )
            resp = conn.getresponse()
            assert resp.status == 200
            assert resp.read() == b"wire-bytes"
            assert resp.getheader("X-Content-Type-Options") == "nosniff"
            assert resp.getheader("X-Easy-Sandbox-Local") == "1"
            conn.close()
            status, body, headers = _http(port, "GET", "/v1/vaults/vlt_nope")
            assert status == 404 and headers["x-should-retry"] == "false"
            assert body["error"]["type"] == "not_found_error"
            status, response, headers = _http(
                port, "POST", "/v1/responses", {"model": "codex", "input": "hi", "adapter": "codex"}
            )
            assert status == 200 and response["object"] == "response"
            assert headers["x-easy-sandbox-local"] == "1"
        finally:
            httpd.shutdown()

    def test_bearer_auth_still_guards_new_routes(self) -> None:
        default_table().enable_group(CapabilityGroup.AGENTS)
        port = _free_port()
        httpd = ThreadingHTTPServer(("127.0.0.1", port), SandboxRequestHandler)
        httpd.auth_token = "tok"  # type: ignore[attr-defined]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            assert _http(port, "GET", "/v1/vaults")[0] == 401
            status, _, _ = _http(port, "GET", "/v1/vaults", headers={"Authorization": "Bearer tok"})
            assert status == 200
        finally:
            httpd.shutdown()
