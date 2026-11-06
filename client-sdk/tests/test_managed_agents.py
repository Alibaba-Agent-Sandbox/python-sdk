"""Managed business behavior over real HTTP/files/subprocesses; no cloud/model claims."""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from agent_sandbox.managed_agents import ManagedConfig, ManagedError, ManagedService, ManagedStore
from agent_sandbox.managed_agents.dispatch import (
    ManagedDispatcher,
    sign_invocation,
    verify_invocation,
)
from agent_sandbox.managed_agents.http import TokenAuthenticator, make_server
from agent_sandbox.managed_agents.worker import ManagedWorker

# isort: split
from agent_sandbox.server.agents.runtime import AgentRuntime
from agent_sandbox.server.managed import ManagedBridge, make_bridge_server


class LocalBackend:
    """Real private HTTP bridge and CLI fixture, with one isolated directory per Sandbox."""

    def __init__(self, root: Path, binary: Path) -> None:
        self.root, self.binary = root, binary
        self.resources: dict[str, tuple[Any, Any, Any]] = {}
        self.created = 0
        self.block_turns = False

    async def create(self, session: dict[str, Any], token: str, on_created: Any) -> dict[str, Any]:
        self.created += 1
        directory = self.root / session["id"]
        workspace = directory / "workspace"
        logical = session["_settings"]["workspace"]

        class TestBridge(ManagedBridge):
            def submit(self, body: dict[str, Any]) -> dict[str, Any]:
                body = copy.deepcopy(body)
                for file in body["files"]:
                    file["path"] = str(workspace) + file["path"][len(logical) :]
                return super().submit(body)

        environment = {
            "PATH": str(self.binary) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(directory),
            "ABX_AGENTS_ALLOW_COMMAND": "0",
        }
        runtime = AgentRuntime(
            persist=False,
            environ=environment,
            max_concurrent_turns=1,
            kill_grace_s=0.1,
            term_grace_s=0.1,
        )
        if self.block_turns:
            runtime._slots.acquire()
        bridge = TestBridge(str(directory / "journal"), str(workspace), runtime=runtime)
        server = make_bridge_server(bridge, token, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        resource = {
            "sandbox_id": session["id"],
            "ownership": "owned",
            "token": token,
            "headers": {},
            "url": f"http://127.0.0.1:{server.server_port}",
        }
        self.resources[session["id"]] = bridge, server, thread
        on_created(resource)
        return resource

    async def kill(self, resource: dict[str, Any]) -> bool:
        entry = self.resources.pop(resource["sandbox_id"], None)
        if entry:
            bridge, server, thread = entry
            for session in bridge.runtime.list_sessions():
                bridge.runtime.delete_session(session.id)
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        return resource["sandbox_id"] not in self.resources


@pytest.fixture
def components(tmp_path: Path, request: Any) -> Any:
    binary = tmp_path / "bin"
    binary.mkdir()
    script = binary / "qwen"
    script.write_text(
        f"#!{sys.executable}\n"
        + """
import json,pathlib,subprocess,sys,time
if '--version' in sys.argv:
 print('qwen-fixture-1');sys.exit(0)
print(json.dumps({'type':'system','subtype':'init','session_id':'native-fixture-thread'}),flush=True)
if 'slow' in sys.argv[1]:time.sleep(15)
if 'tool-' in sys.argv[1]:
 print(json.dumps({'type':'assistant','message':{'id':'tool-message','content':[
  {'type':'tool_use','id':'sleep-tool','name':'Bash','input':{'command':'sleep'}}]}}),flush=True)
 subprocess.run([sys.executable,'-c','import time;time.sleep(15)'
  if 'tool-long' in sys.argv[1] else 'import time;time.sleep(.05)'],check=True)
 print(json.dumps({'type':'user','message':{'content':[
  {'type':'tool_result','tool_use_id':'sleep-tool','content':'done'}]}}),flush=True)
 time.sleep(1.2)
root=pathlib.Path.cwd();out=root/'outputs';out.mkdir(exist_ok=True)
counter=root/'counter'
n=int(counter.read_text())+1 if counter.exists() else 1;counter.write_text(str(n))
source=root/'input'/'sales.csv'
text=source.read_text() if source.exists() else 'no input'
(out/'result.txt').write_text(str(n)+'|'+text)
print(json.dumps({'type':'assistant','message':{'id':'message-'+str(n),
 'content':[{'type':'text','text':'completed '+str(n)}]}}),flush=True)
print(json.dumps({'type':'result','subtype':'success','is_error':False,
 'result':'completed '+str(n)}),flush=True)
"""
    )
    script.chmod(0o755)
    config = ManagedConfig.from_dict(
        {
            "revision": "revision-a",
            "template": "fixture-template",
            "models": {"fixture-model": "qwen-code"},
            "modelEnvAllowlist": ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"],
            "sessions": {"maxLifetimeSeconds": 60, "idleTimeoutSeconds": 30},
            "limits": {"maxRunSeconds": 20, "maxToolSeconds": 5},
        }
    )
    postgres = None
    if getattr(request, "param", "sqlite") == "postgres":
        pgserver = pytest.importorskip("pgserver", reason="real PostgreSQL component extra")
        postgres = pgserver.get_server(tmp_path / "postgres", cleanup_mode="delete")
        url = postgres.get_uri()
    else:
        url = "sqlite:///" + str(tmp_path / "state.db")
    service = ManagedService(ManagedStore(url, local=True), config)
    backend = LocalBackend(tmp_path / "sandboxes", binary)
    worker = ManagedWorker(service, backend, poll_seconds=0.01)
    dispatcher = ManagedDispatcher(worker)
    yield service, backend, worker, dispatcher
    for sid in list(backend.resources):
        asyncio.run(backend.kill({"sandbox_id": sid}))
    if postgres:
        postgres.cleanup()


def create(service: ManagedService, text: str | None = None, key: str = "") -> dict[str, Any]:
    body: dict[str, Any] = {"agent": {"model": "fixture-model"}}
    if text is not None:
        body["input"] = text
    return service.handle("owner", "POST", "/v1/agents/sessions", body, key=key)[1]


def test_create_replay_busy_queue_and_owner_boundaries(components: Any) -> None:
    service, backend, _, _ = components
    session = create(service, "first", "initial")
    assert create(service, "first", "initial")["id"] == session["id"]
    assert backend.created == 0
    with pytest.raises(ManagedError, match="another request"):
        create(service, "different", "initial")
    with pytest.raises(ManagedError) as busy:
        service.handle(
            "owner", "POST", f"/v1/agents/sessions/{session['id']}/events", {"input": "next"}
        )
    assert busy.value.status == 409 and busy.value.code == "active_turn_not_steerable"
    status, queued, _ = service.handle(
        "owner",
        "POST",
        f"/v1/agent-sandbox/sessions/{session['id']}/submissions",
        {"input": "later"},
        key="later",
    )
    assert status == 202 and queued["turn_id"] is None
    op = service.handle(
        "owner",
        "POST",
        f"/v1/agent-sandbox/sessions/{session['id']}/submissions/{queued['id']}/cancel",
    )[1]
    assert op["result"]["stop_confirmed"] is True
    with pytest.raises(ManagedError) as foreign:
        service.handle("foreign", "GET", f"/v1/agents/sessions/{session['id']}")
    assert foreign.value.status == 404


@pytest.mark.asyncio
async def test_real_bridge_two_turns_files_artifacts_close_and_delete(components: Any) -> None:
    service, backend, worker, dispatcher = components
    source = service.upload_file("owner", "sales.csv", "user_data", b"month,amount\nJan,3\n")
    status, session, _ = service.handle(
        "owner",
        "POST",
        "/v1/agents/sessions",
        {
            "agent": {"model": "fixture-model"},
            "input": "summarize the CSV",
            "x_agent_sandbox": {
                "input_files": [{"file_id": source["id"], "path": "/workspace/input/sales.csv"}]
            },
        },
    )
    assert status == 201
    sid = session["id"]
    assert await worker.run(sid)
    turns = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns")[1]["data"]
    assert len(turns) == 1 and turns[0]["status"] == "completed"
    turn = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns/{turns[0]['id']}")[1]
    assert turn["object"] == "agent.session.turn"
    items = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns/{turn['id']}/items")[
        1
    ]["data"]
    assert items[0]["content"][0]["text"] == "completed 1"
    artifacts = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/artifacts")[1]["data"]
    original = artifacts[0]["id"]
    content = service.handle(
        "owner", "GET", f"/v1/agents/sessions/{sid}/artifacts/{original}/content"
    )[1]
    assert content == b"1|month,amount\nJan,3\n"
    service.handle(
        "owner", "POST", f"/v1/agents/sessions/{sid}/events", {"input": "continue"}, key="second"
    )
    assert await worker.run(sid)
    assert backend.created == 1
    assert service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/items")[1]["data"]
    env = service.handle("owner", "GET", f"/v1/agents/environments/{session['environment']['id']}")[
        1
    ]
    assert env["x_agent_sandbox"]["lifecycle"] == "ready"
    closed = service.handle("owner", "POST", f"/v1/agent-sandbox/sessions/{sid}/close")[1]
    assert await worker.run(sid)
    assert not backend.resources
    assert service.handle("owner", "GET", f"/v1/agent-sandbox/operations/{closed['id']}")[1][
        "result"
    ]["compute_released"]
    assert (
        service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/artifacts/{original}/content")[1]
        == content
    )
    assert dispatcher.status()["activeSessions"] == 0
    assert service.handle("owner", "DELETE", f"/v1/agents/sessions/{sid}")[0] == 200
    for tail in ("", "/items", "/artifacts", f"/artifacts/{original}/content"):
        with pytest.raises(ManagedError) as gone:
            service.handle("owner", "GET", f"/v1/agents/sessions/{sid}" + tail)
        assert gone.value.status == 404


def test_raw_sdk_pagination_and_cross_owner_cursor(components: Any) -> None:
    service = components[0]
    for i in range(3):
        service.handle("owner", "POST", "/v1/agents", {"model": "fixture-model", "name": str(i)})
    first = service.handle("owner", "GET", "/v1/agents", query={"limit": "1"})[1]
    second = service.handle(
        "owner", "GET", "/v1/agents", query={"limit": "1", "after": first["last_id"]}
    )[1]
    assert first["data"][0]["id"] != second["data"][0]["id"]
    with pytest.raises(ManagedError):
        service.handle(
            "foreign", "GET", "/v1/agents", query={"after": first["x_agent_sandbox"]["next_cursor"]}
        )


@pytest.mark.parametrize(
    "body",
    [
        {"limits": {"unknown": 1}},
        {"sessions": {"guestRestartPolicy": "replay"}},
        {"limits": {"maxToolSeconds": 601}},
        {"port": True},
        {"models": {"bad": "missing"}},
    ],
)
def test_compiled_configuration_rejects_unknown_or_invalid_budgets(body: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        ManagedConfig.from_dict(
            {"revision": "r", "template": "t", "models": {"m": "qwen-code"}, **body}
        )


def test_metadata_queries_do_not_load_binary_and_deleted_bytes_still_count(components: Any) -> None:
    service = components[0]
    file = service.upload_file("owner", "x", "user_data", b"binary canary")
    with service.store.transaction() as tx:
        rows = tx.list("file", "owner")
        assert "_data" not in rows[0] and rows[0]["_has_blob"] is True
        raw = tx.execute("SELECT body FROM managed_objects WHERE id=?", (file["id"],)).fetchone()[
            "body"
        ]
        assert base64.b64encode(b"binary canary").decode() not in raw
    service.handle("owner", "DELETE", "/v1/files/" + file["id"])
    with service.store.transaction() as tx:
        assert tx.get(file["id"], "owner", deleted=True)["_has_blob"]


@pytest.mark.asyncio
async def test_drain_counts_idle_logical_sessions_and_unknown_revisions(components: Any) -> None:
    service, _, _, dispatcher = components
    session = create(service)
    assert dispatcher.status()["activeSessions"] == 1
    assert not dispatcher.worker.due(revisions={"other-revision"})
    response = await dispatcher.invoke({"operation": "drain", "applicationId": "agents-api"})
    assert response["activeSessions"] == 0 and response["pendingCleanup"] == 0
    assert (
        service.handle("owner", "GET", f"/v1/agents/sessions/{session['id']}")[1][
            "x_agent_sandbox"
        ]["lifecycle"]
        == "closed"
    )
    with pytest.raises(ManagedError) as rejected:
        create(service)
    assert rejected.value.code == "application_draining"


def test_auth_expiry_and_role_body_signature() -> None:
    key = "b" * 40
    doc = {
        "tokens": [
            {
                "sha256": hashlib.sha256(key.encode()).hexdigest(),
                "owner": "owner",
                "scopes": ["agents:read"],
                "expiresAt": time.time() + 60,
            }
        ]
    }
    auth = TokenAuthenticator(doc)
    assert auth.authenticate(key, False) == "owner"
    with pytest.raises(ManagedError) as denied:
        auth.authenticate(key, True)
    assert denied.value.status == 403
    doc["tokens"][0]["expiresAt"] = time.time() - 1
    with pytest.raises(ManagedError) as expired:
        auth.authenticate(key, False)
    assert expired.value.status == 401
    envelope = sign_invocation({"limit": 1}, "i" * 40, "dispatcher")
    assert verify_invocation(envelope, "i" * 40, "dispatcher") == {"limit": 1}
    with pytest.raises(ManagedError):
        verify_invocation(envelope, "i" * 40, "worker")


def test_real_http_multipart_and_safe_errors(components: Any) -> None:
    service = components[0]
    token = "b" * 40
    auth = TokenAuthenticator(
        {
            "tokens": [
                {
                    "sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "owner": "owner",
                    "scopes": ["agents:read", "agents:write"],
                }
            ]
        }
    )
    server = make_server(service, auth, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}",
            headers={"Authorization": "Bearer " + token},
            trust_env=False,
        ) as client:
            assert client.get("/healthz").json()["status"] == "ok"
            response = client.post(
                "/v1/files",
                data={"purpose": "user_data"},
                files={"file": ("sales.csv", b"x,y\n1,2\n")},
            )
            assert response.status_code == 200
            file = response.json()
            assert client.get("/v1/files/" + file["id"] + "/content").content == b"x,y\n1,2\n"
            result = client.post("/v1/agents/sessions", json={"agent": {"model": "fixture-model"}})
            assert result.status_code == 201 and "Location" in result.headers
            sid = result.json()["id"]
            accepted = client.post(
                f"/v1/agents/sessions/{sid}/events",
                json={"input": "hello"},
                headers={"Idempotency-Key": "message-1"},
            )
            assert accepted.status_code == 202 and not accepted.content
            assert client.get(accepted.headers["Location"]).json()["turn_id"] is None
            forbidden = client.post("/invoke", json={"token": "private-value"})
            assert forbidden.status_code == 404 and "private-value" not in forbidden.text
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("components", ["sqlite", "postgres"], indirect=True)
@pytest.mark.parametrize("mode", ["dispatcher", "worker"])
def test_private_fc_octet_stream_keeps_json_and_role_boundaries(components: Any, mode: str) -> None:
    service, backend, _, dispatcher = components
    sid = create(service)["id"]
    token = "test-internal-token-" * 3
    payload = (
        {"operation": "status", "applicationId": service.config.application_id}
        if mode == "dispatcher"
        else {"sessionId": sid}
    )
    envelope = sign_invocation(payload, token, mode)
    server = make_server(
        service, None, mode=mode, dispatcher=dispatcher, internal_token=token, port=0
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False
        ) as client:
            for media_type in (
                "application/json",
                "application/octet-stream",
                "Application/Octet-Stream; charset=utf-8",
            ):
                response = client.post(
                    "/invoke", content=json.dumps(envelope), headers={"Content-Type": media_type}
                )
                assert response.status_code == 200
                if mode == "dispatcher":
                    assert response.json()["activeSessions"] == 1
                else:
                    assert response.json() == {"claimed": False}
            octet = {"Content-Type": "application/octet-stream"}
            invalid = {**envelope, "signature": "0" * 64}
            assert (
                client.post("/invoke", content=json.dumps(invalid), headers=octet).status_code
                == 401
            )
            other_role = "worker" if mode == "dispatcher" else "dispatcher"
            wrong_role = sign_invocation(payload, token, other_role)
            assert (
                client.post("/invoke", content=json.dumps(wrong_role), headers=octet).status_code
                == 401
            )
            for raw in (b"{", b"[]", b'{"value":NaN}'):
                response = client.post("/invoke", content=raw, headers=octet)
                assert response.status_code == 400
                assert response.json()["error"]["code"] == "invalid_json"
            assert client.post("/invoke/other", content=b"{}", headers=octet).status_code == 404
            assert client.get("/invoke", headers=octet).status_code == 404
            assert (
                client.post(
                    "/invoke", content=json.dumps(envelope), headers={"Content-Type": "text/plain"}
                ).status_code
                == 415
            )
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=3) as connection:
            size = service.config.storage["maxFileBytes"] + 16385
            connection.sendall(
                (
                    "POST /invoke HTTP/1.1\r\nHost: localhost\r\n"
                    "Content-Type: application/octet-stream\r\n"
                    f"Content-Length: {size}\r\nConnection: close\r\n\r\n"
                ).encode()
            )
            assert connection.makefile("rb").readline().startswith(b"HTTP/1.1 413 ")
        assert backend.created == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("components", ["sqlite", "postgres"], indirect=True)
@pytest.mark.parametrize("operation", ["status", "drain"])
def test_empty_private_revision_rejects_without_state_changes(
    components: Any, operation: str
) -> None:
    service, backend, _, dispatcher = components
    sid = create(service)["id"]
    token = "test-private-control-token-" * 3

    def snapshot() -> dict[str, Any]:
        queries = {
            "control": "SELECT * FROM managed_control WHERE application=? ORDER BY 1,2",
            "objects": "SELECT * FROM managed_objects WHERE application=? ORDER BY 1,2",
            "events": "SELECT * FROM managed_events WHERE application=? ORDER BY 1,2,3",
            "idempotency": "SELECT * FROM managed_idempotency WHERE application=? ORDER BY 1,2,3",
            "meta": "SELECT * FROM managed_meta WHERE application=? ORDER BY 1,2",
        }
        with service.store.transaction() as tx:
            return {
                label: [dict(row) for row in tx.execute(query, (tx.application,)).fetchall()]
                for label, query in queries.items()
            }

    before = snapshot()
    assert dispatcher.status()["activeSessions"] == 1
    server = make_server(
        service, None, mode="dispatcher", dispatcher=dispatcher, internal_token=token, port=0
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False
        ) as client:
            payload = {
                "operation": operation,
                "applicationId": service.config.application_id,
                "revision": "",
            }
            invalid = client.post(
                "/invoke",
                content=json.dumps(sign_invocation(payload, token, "dispatcher")),
                headers={"Content-Type": "application/octet-stream"},
            )
            assert invalid.status_code == 400
            assert invalid.json()["error"]["code"] == "invalid_invocation"
            assert snapshot() == before
            assert dispatcher.status()["activeSessions"] == 1
            assert dispatcher.status()["draining"] is False
            assert backend.created == 0
            scoped = client.post(
                "/invoke",
                json=sign_invocation(
                    {**payload, "operation": "status", "revision": service.config.revision},
                    token,
                    "dispatcher",
                ),
            )
            assert scoped.status_code == 200 and scoped.json()["activeSessions"] == 1
            drained = client.post(
                "/invoke",
                json=sign_invocation(
                    {"operation": "drain", "applicationId": service.config.application_id},
                    token,
                    "dispatcher",
                ),
            )
            assert drained.status_code == 200
            assert drained.json()["draining"] is True
            for field in ("activeSessions", "pendingCleanup", "uncertainResources"):
                assert drained.json()[field] == 0
            session = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}")[1]
            assert session["x_agent_sandbox"]["lifecycle"] == "closed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_gateway_still_requires_json_for_octet_stream_envelopes(components: Any) -> None:
    service = components[0]
    token = "test-business-token-" * 3
    auth = TokenAuthenticator(
        {
            "tokens": [
                {
                    "sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "owner": "owner",
                    "scopes": ["agents:read", "agents:write"],
                }
            ]
        }
    )
    server = make_server(service, auth, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}",
            headers={"Authorization": "Bearer " + token},
            trust_env=False,
        ) as client:
            envelope = sign_invocation(
                {"operation": "status"}, "test-private-token-" * 3, "dispatcher"
            )
            response = client.post(
                "/v1/agents/sessions",
                content=json.dumps(envelope),
                headers={"Content-Type": "application/octet-stream"},
            )
            assert response.status_code == 415
            assert response.json()["error"]["code"] == "unsupported_media_type"
            assert client.post("/invoke", json=envelope).status_code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.asyncio
async def test_active_cancel_exact_target_replays_without_cancelling_next_turn(
    components: Any,
) -> None:
    service, backend, worker, _ = components
    sid = create(service, "slow")["id"]
    running = asyncio.create_task(worker.run(sid))
    for _ in range(200):
        await asyncio.sleep(0.02)
        turns = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns")[1]["data"]
        if turns:
            break
    assert turns and turns[0]["status"] == "in_progress"
    body = {"events": [{"type": "agent.session.input.cancel"}]}
    original = service.handle(
        "owner", "POST", f"/v1/agents/sessions/{sid}/events", body, key="stop-a"
    )
    assert await running
    operation = service.handle(
        "owner",
        "GET",
        "/v1/agent-sandbox/operations/" + original[2]["X-Agent-Sandbox-Operation-Id"],
    )[1]
    assert operation["result"]["stop_confirmed"] is True
    assert backend.created == 1 and backend.resources
    service.handle("owner", "POST", f"/v1/agents/sessions/{sid}/events", {"input": "continue"})
    # A new process sees the same durable cancel target, even after A completed.
    reloaded = ManagedService(ManagedStore(service.store.url, local=True), service.config)
    replay = reloaded.handle(
        "owner", "POST", f"/v1/agents/sessions/{sid}/events", body, key="stop-a"
    )
    assert replay == original
    with reloaded.store.transaction() as tx:
        pending = [r for r in tx.list("submission", parent=sid) if r["status"] == "queued"]
        assert len(pending) == 1 and not pending[0]["_cancel"]
    assert await worker.run(sid)
    assert backend.created == 1


@pytest.mark.asyncio
async def test_cancel_during_create_never_sends_input(components: Any) -> None:
    service, backend, worker, _ = components
    sid = create(service, "first")["id"]
    original_create = backend.create

    async def cancelling_create(
        session: dict[str, Any], token: str, created: Any
    ) -> dict[str, Any]:
        resource = await original_create(session, token, created)
        with service.store.transaction() as tx:
            sub = tx.list("submission", parent=sid)[0]
            service._cancel(tx, tx.get(sid), sub)
        return resource

    backend.create = cancelling_create
    assert await worker.run(sid)
    bridge = backend.resources[sid][0]
    assert not bridge.runtime.get_session(bridge._session_record()["session_id"]).turns
    with service.store.transaction() as tx:
        sub = tx.list("submission", parent=sid)[0]
        assert sub["status"] == "cancelled" and not sub.get("_sent")


def test_real_detached_child_survives_leader_but_process_domain_stops_it(tmp_path: Path) -> None:
    import secrets
    import subprocess

    from agent_sandbox.server.managed_process import ProcessDomain

    scope = secrets.token_hex(20)
    domain = ProcessDomain(scope)
    output = tmp_path / "ticks"
    # Use a real detached executable rather than treating leader exit as evidence.
    child_script = tmp_path / "child.py"
    child_script.write_text(
        "import pathlib,sys,time\np=pathlib.Path(sys.argv[1])\n"
        "while True:\n p.write_text(str(time.time())); time.sleep(.02)\n"
    )
    leader = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import subprocess,sys; p=subprocess.Popen(sys.argv[1:],start_new_session=True,"
            "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);print(p.pid)",
            sys.executable,
            str(child_script),
            str(output),
        ],
        env={**os.environ, "ABX_MANAGED_TURN_SCOPE": scope},
        stdout=subprocess.PIPE,
    )
    child_pid = int(leader.communicate(timeout=5)[0])
    try:
        assert leader.returncode == 0
        for _ in range(100):
            if output.exists():
                break
            time.sleep(0.02)
        before = output.read_text()
        time.sleep(0.08)
        assert output.read_text() != before  # escaped child remains active after leader exit
        domain.quiesce()  # unknown concurrent host processes may conservatively refuse reuse
        stopped = output.read_text()
        time.sleep(0.08)
        assert output.read_text() == stopped
    finally:
        import contextlib
        import signal

        with contextlib.suppress(ProcessLookupError):
            os.kill(child_pid, signal.SIGKILL)


def test_output_snapshot_rejects_ancestor_swapped_to_symlink(
    tmp_path: Path, monkeypatch: Any
) -> None:
    workspace = tmp_path / "workspace"
    nested = workspace / "outputs" / "nested"
    nested.mkdir(parents=True)
    (nested / "report.txt").write_text("owned")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "report.txt").write_text("private outside")
    bridge = ManagedBridge(str(tmp_path / "journal"), str(workspace))
    original_open = os.open

    def swapping_open(path: Any, *args: Any, **kwargs: Any) -> Any:
        if path == "nested" and kwargs.get("dir_fd") is not None:
            nested.rename(workspace / "saved")
            nested.symlink_to(outside, target_is_directory=True)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", swapping_open)
    artifacts, errors = bridge._snapshots()
    assert artifacts == [] and errors


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt,expected", [("tool-long", "failed"), ("tool-done", "completed")])
async def test_observed_real_tool_wall_deadline(
    components: Any, prompt: str, expected: str
) -> None:
    service, backend, worker, _ = components
    service.config.limits["maxToolSeconds"] = 1
    sid = create(service, prompt)["id"]
    assert await worker.run(sid)
    turn = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns")[1]["data"][0]
    assert turn["status"] == expected
    if expected == "failed":
        assert turn["error"]["code"] == "tool_deadline_exceeded"
    with service.store.transaction() as tx:
        current = tx.get(sid)
        # Dedicated cooperative domains may be reused; unknown concurrent host
        # processes require provider destruction before stop can be confirmed.
        assert backend.resources or current.get("_cleanup_confirmed") is True


@pytest.mark.asyncio
async def test_preparation_heartbeat_prevents_second_create_after_original_lease(
    components: Any,
) -> None:
    service, backend, _, _ = components
    lease_seconds = 2
    worker = ManagedWorker(service, backend, poll_seconds=0.01, lease_seconds=lease_seconds)
    sid = create(service, "first")["id"]
    original_create = backend.create
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_create(session: dict[str, Any], token: str, created: Any) -> dict[str, Any]:
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=15)
        return await original_create(session, token, created)

    backend.create = slow_create
    first = asyncio.create_task(worker.run(sid))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        await asyncio.sleep(lease_seconds + 0.2)
        assert await asyncio.wait_for(worker.run(sid), timeout=5) is False
        assert worker.due() == []
    finally:
        release.set()
        completed = await asyncio.wait_for(first, timeout=15)
    assert completed
    assert backend.created == 1
    with service.store.transaction() as tx:
        assert tx.get(sid)["x_agent_sandbox"]["lifecycle"] == "ready"


@pytest.mark.asyncio
@pytest.mark.parametrize("components", ["sqlite", "postgres"], indirect=True)
async def test_all_39_http_operations_against_frozen_inventory(components: Any) -> None:
    from agent_sandbox.managed_agents.service import OPERATIONS

    service, backend, worker, _ = components
    inventory = json.loads((Path(__file__).parent / "fixtures" / "managed_api_v1.json").read_text())
    definitions = {item["operation_id"]: item for item in inventory["operations"]}
    assert {(o["method"], o["path"]) for o in definitions.values()} == set(OPERATIONS)
    token = "inventory-test-business-token"
    auth = TokenAuthenticator(
        {
            "tokens": [
                {
                    "sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "owner": "owner",
                    "scopes": ["agents:read", "agents:write"],
                }
            ]
        }
    )
    server = make_server(service, auth, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    values = {"model_id": "fixture-model"}
    observed: set[str] = set()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}",
            headers={"Authorization": "Bearer " + token},
            trust_env=False,
        ) as client:

            def call(name: str, body: Any = None, **kwargs: Any) -> Any:
                definition = definitions[name]
                path = definition["path"].format(**values)
                response = client.request(definition["method"], path, json=body, **kwargs)
                assert response.status_code in definition["success_codes"], (name, response.text)
                observed.add(name)
                return (
                    response.json()
                    if response.content and "json" in response.headers.get("content-type", "")
                    else response
                )

            call("health_get")
            call("capabilities_get")
            call("models_list")
            call("models_get")
            call("runtimes_list")
            agent = call("agents_create", {"model": "fixture-model", "instructions": "Be precise"})
            values["agent_id"] = agent["id"]
            call("agents_list")
            call("agents_get")
            call("agents_update", {"name": "Reusable agent"})
            uploaded = call(
                "files_create",
                data={"purpose": "user_data"},
                files={"file": ("sales.csv", b"x,y\n1,2\n")},
            )
            values["file_id"] = uploaded["id"]
            call("files_list")
            call("files_get")
            call("files_content")
            session = call("sessions_create", {"agent_id": agent["id"]})
            values["session_id"] = session["id"]
            values["environment_id"] = session["environment"]["id"]
            call("sessions_list")
            call("sessions_get")
            call("sessions_update", {"metadata": {"label": "inventory"}})
            call("environments_list")
            call("environments_get")
            call(
                "session_events_create",
                {"input": "generate report"},
                headers={"Idempotency-Key": "first"},
            )
            assert await worker.run(session["id"])
            turns = call("turns_list")["data"]
            values["turn_id"] = turns[0]["id"]
            call("turns_get")
            call("turn_items_list")
            call("session_items_list")
            artifacts = call("artifacts_list")["data"]
            values["artifact_id"] = artifacts[0]["id"]
            call("artifacts_get")
            call("artifacts_content")
            assert client.get("/v1/agents/environments/" + values["artifact_id"]).status_code == 404
            assert (
                client.get(
                    f"/v1/agent-sandbox/sessions/{session['id']}/submissions/{values['turn_id']}"
                ).status_code
                == 404
            )
            with client.stream(
                "GET", f"/v1/agents/sessions/{session['id']}/events?after=0"
            ) as stream:
                assert stream.status_code == 200
                assert any(line.startswith("data:") for line in stream.iter_lines())
                observed.add("session_events_stream")
            queued = call(
                "submissions_enqueue", {"input": "queued"}, headers={"Idempotency-Key": "queued"}
            )
            values["submission_id"] = queued["id"]
            call("submissions_list")
            call("submissions_get")
            call("submissions_cancel")
            call("turns_cancel")
            operation = call("sessions_close")
            values["operation_id"] = operation["id"]
            assert await worker.run(session["id"])
            assert call("operations_get")["result"]["compute_released"]
            call("artifacts_delete")
            call("files_delete")
            call("agents_delete")
            call("sessions_delete")
            assert observed == set(definitions)
            # Every protected route authenticates before parsing or touching resources.
            for name, definition in definitions.items():
                path = definition["path"].format(**values)
                if name == "health_get":
                    assert client.get("/healthz/missing").status_code == 404
                else:
                    response = client.request(
                        definition["method"], path, headers={"Authorization": "Bearer invalid"}
                    )
                    assert response.status_code == 401, (name, response.text)
            assert client.get("/v1/agents/sessions/" + session["id"]).status_code == 404
            assert (
                client.post(
                    "/v1/agents",
                    json={
                        "model": "fixture-model",
                        "tools": [{"type": "function", "name": "shell"}],
                    },
                ).status_code
                == 400
            )
            assert not backend.resources
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.asyncio
@pytest.mark.parametrize("components", ["sqlite", "postgres"], indirect=True)
async def test_retention_gc_keeps_pending_files_and_uncertain_resources(components: Any) -> None:
    from agent_sandbox.managed_agents.store import new_object

    service, _, worker, dispatcher = components
    uploaded = service.upload_file("owner", "input.txt", "user_data", b"pending input")
    session = service.handle(
        "owner",
        "POST",
        "/v1/agents/sessions",
        {
            "agent": {"model": "fixture-model"},
            "input": "later",
            "x_agent_sandbox": {
                "input_files": [{"file_id": uploaded["id"], "path": "/workspace/input/input.txt"}]
            },
        },
    )[1]
    sid = session["id"]
    with service.store.transaction() as tx:
        file = tx.get(uploaded["id"])
        file["expires_at"] = time.time() - 1
        tx.put(file)
        service.collect(tx, limit=1)
        assert tx.get(uploaded["id"], with_data=True)["_data"]
        sub = tx.list("submission", parent=sid)[0]
        service._cancel(tx, tx.get(sid), sub)
        service.collect(tx, limit=1)
        assert not tx.get(uploaded["id"]).get("_has_blob")
    service.handle("owner", "POST", f"/v1/agent-sandbox/sessions/{sid}/close")
    assert await worker.run(sid)
    with service.store.transaction() as tx:
        closed = tx.get(sid)
        closed["_retain_until"] = time.time() - 1
        tx.put(closed)
        for _i in range(5):
            tx.put(
                new_object(
                    "artifact",
                    "owner",
                    parent=sid,
                    bytes=1,
                    _data="eA==",
                    expires_at=time.time() + 10,
                )
            )
        uncertain = new_object(
            "session",
            "owner",
            status="failed",
            x_agent_sandbox={"lifecycle": "requires_reconcile"},
            _creation_started=True,
            _revision=service.config.revision,
            _retain_until=time.time() - 1,
            _cleanup_confirmed=False,
        )
        tx.put(uncertain)
    for _ in range(20):
        with service.store.transaction() as tx:
            service.collect(tx, limit=1)
    with service.store.transaction() as tx:
        assert tx.get(sid, deleted=True).get("_collected")
        assert tx.get(uncertain["id"], deleted=True)["_creation_started"]
        assert not tx.events(sid, 0)
    assert dispatcher.status()["uncertainResources"] == 1
    with pytest.raises(ManagedError) as expired:
        service.handle("owner", "GET", f"/v1/agents/sessions/{sid}")
    assert expired.value.status == 410


def test_closed_tombstone_history_does_not_block_dispatch_or_admission(components: Any) -> None:
    from agent_sandbox.managed_agents.store import new_object

    service, _, worker, dispatcher = components
    with service.store.transaction() as tx:
        for _ in range(10002):
            tx.put(
                new_object(
                    "session",
                    "historical",
                    _deleted=True,
                    _cleanup_confirmed=True,
                    _revision=service.config.revision,
                    x_agent_sandbox={"lifecycle": "closed"},
                )
            )
    assert worker.due() == []
    assert dispatcher.status()["activeSessions"] == 0
    assert create(service)["id"]


def test_partial_body_times_out_and_other_connections_remain_usable(components: Any) -> None:
    import socket

    service = components[0]
    token = "partial-body-test-key"
    auth = TokenAuthenticator(
        {
            "tokens": [
                {
                    "sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "owner": "owner",
                    "scopes": ["agents:write", "agents:read"],
                }
            ]
        }
    )
    server = make_server(service, auth, port=0, read_timeout=0.15, max_connections=2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=2) as client:
            client.sendall(
                (
                    f"POST /v1/agents HTTP/1.1\r\nHost: localhost\r\n"
                    f"Authorization: Bearer {token}\r\nContent-Length: 100\r\n\r\n{{"
                ).encode()
            )
            assert client.recv(100) == b""
        assert (
            httpx.get(f"http://127.0.0.1:{server.server_port}/healthz", trust_env=False).status_code
            == 200
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.asyncio
async def test_lost_submit_response_inspects_original_receipt_without_replay(
    components: Any, monkeypatch: Any
) -> None:
    import agent_sandbox.managed_agents.worker as implementation
    from agent_sandbox.managed_agents.backend import bridge_request

    service, backend, worker, _ = components
    sid = create(service, "one effect")["id"]
    submits = 0

    async def lost_response(
        resource: Any, method: str, path: str, body: Any = None, **options: Any
    ) -> Any:
        nonlocal submits
        result = await bridge_request(resource, method, path, body, **options)
        if method == "POST" and path == "/managed/submissions":
            submits += 1
            raise ManagedError(503, "connection_lost", "response was lost after acceptance")
        return result

    monkeypatch.setattr(implementation, "bridge_request", lost_response)
    assert await worker.run(sid)
    assert submits == 1
    assert (backend.root / sid / "workspace" / "counter").read_text() == "1"


def test_deep_artifact_tree_reports_partial_and_preserves_valid_sibling(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "outputs" / "a" / "1" / "2" / "3" / "4" / "5" / "6" / "7" / "8" / "9").mkdir(
        parents=True
    )
    (workspace / "outputs" / "z").mkdir()
    (workspace / "outputs" / "z" / "expected.txt").write_text("expected")
    bridge = ManagedBridge(str(tmp_path / "journal"), str(workspace))
    artifacts, errors = bridge._snapshots()
    assert [a["path"] for a in artifacts] == ["outputs/z/expected.txt"]
    assert any(e["code"] == "artifact_depth_limit" for e in errors)


@pytest.mark.asyncio
async def test_small_output_budget_reaches_real_cli_and_bounds_public_items(
    components: Any,
) -> None:
    service, _, worker, _ = components
    service.config.limits["maxOutputBytes"] = 16
    sid = create(service, "output")["id"]
    assert await worker.run(sid)
    turns = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns")[1]["data"]
    assert turns[0]["status"] == "failed"
    assert service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/items")[1]["data"] == []
    with service.store.transaction() as tx:
        submission = tx.list("submission", parent=sid)[0]
        assert not submission.get("_native_seen")


@pytest.mark.asyncio
async def test_uncertain_session_never_executes_queued_successor(components: Any) -> None:
    service, backend, worker, _ = components
    sid = create(service, "first")["id"]
    queued = service.handle(
        "owner",
        "POST",
        f"/v1/agent-sandbox/sessions/{sid}/submissions",
        {"input": "must not execute"},
        key="next",
    )[1]
    with service.store.transaction() as tx:
        first = tx.list("submission", parent=sid)[0]
    worker._uncertain(sid, first["id"], None, "injected_setup_failure")
    operation = service.handle(
        "owner", "POST", f"/v1/agent-sandbox/sessions/{sid}/submissions/{first['id']}/cancel"
    )[1]
    assert operation["status"] == "requires_reconcile"
    assert operation["result"]["stop_confirmed"] is False
    assert await worker.run(sid) is False
    assert backend.created == 0 and not (backend.root / sid / "workspace" / "counter").exists()
    assert (
        service.handle(
            "owner", "GET", f"/v1/agent-sandbox/sessions/{sid}/submissions/{queued['id']}"
        )[1]["status"]
        == "queued"
    )


def test_private_bridge_preserves_provider_header_and_authenticates_bearer(tmp_path: Path) -> None:
    bridge = ManagedBridge(str(tmp_path / "journal"), str(tmp_path / "workspace"))
    token = "test-application-" + "a" * 32
    server = make_bridge_server(bridge, token, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False
        ) as client:
            assert (
                client.get(
                    "/capabilities",
                    headers={
                        "X-Access-Token": "platform-test-token",
                        "Authorization": "Bearer " + token,
                    },
                ).status_code
                == 200
            )
            assert (
                client.get(
                    "/capabilities",
                    headers={
                        "X-Access-Token": "platform-test-token",
                        "Authorization": "Bearer wrong-test-token",
                    },
                ).status_code
                == 401
            )
            assert client.get("/capabilities", headers={"Authorization": token}).status_code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("components", ["sqlite", "postgres"], indirect=True)
def test_pinned_state_identity_rejects_empty_store_before_initialization(
    components: Any, tmp_path: Path
) -> None:
    from urllib.parse import urlsplit

    service = components[0]
    original = service.store
    identity = original.state_instance_id
    reopened = ManagedStore(
        original.url, original.application, local=True, expected_state_id=identity
    )
    assert reopened.state_instance_id == identity
    with pytest.raises(ValueError, match="identity"):
        ManagedStore(original.url, original.application, local=True, expected_state_id="0" * 32)
    if original.sqlite:
        import sqlite3

        empty_url = "sqlite:///" + str(tmp_path / "empty.db")
        with pytest.raises(ValueError, match="absent"):
            ManagedStore(empty_url, original.application, local=True, expected_state_id=identity)
        assert not (tmp_path / "empty.db").exists()
        with sqlite3.connect(tmp_path / "empty.db") as db:
            assert not db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    else:
        import psycopg

        with psycopg.connect(original.url, autocommit=True) as db:
            db.execute("CREATE DATABASE managed_empty_state")
        empty_url = urlsplit(original.url)._replace(path="/managed_empty_state").geturl()
        with pytest.raises(ValueError, match="absent"):
            ManagedStore(empty_url, original.application, expected_state_id=identity)
        with psycopg.connect(empty_url) as db:
            assert db.execute("SELECT to_regclass('managed_identity')").fetchone()[0] is None
    if original.sqlite:
        database_path = Path(original.url[len("sqlite:///") :])
        database_path.rename(tmp_path / "retained-state.db")
    else:
        maintenance = urlsplit(original.url)._replace(path="/template1").geturl()
        with psycopg.connect(maintenance, autocommit=True) as db:
            db.execute("ALTER DATABASE postgres RENAME TO managed_retained_state")
            db.execute("CREATE DATABASE postgres")
    replacement = ManagedStore(original.url, original.application, local=True)
    assert replacement.state_instance_id != identity
    with pytest.raises(ManagedError) as changed, original.transaction():
        pass
    assert changed.value.code == "state_identity_changed"


def test_database_ca_is_bounded_private_and_removed() -> None:
    import ssl
    import stat

    from agent_sandbox.managed_agents.__main__ import database_ca_file

    certificate = ssl.DER_cert_to_PEM_cert(
        ssl.create_default_context().get_ca_certs(binary_form=True)[0]
    )
    with database_ca_file(certificate) as path:
        assert path is not None and Path(path).read_text() == certificate
        assert stat.S_IMODE(Path(path).stat().st_mode) == 0o600
        retained = Path(path)
    assert not retained.exists()
    for invalid in (
        "not a certificate",
        "x" * 65537,
        certificate * 9,
        certificate + "unexpected text",
    ):
        with pytest.raises(ValueError), database_ca_file(invalid):
            pass


@pytest.mark.parametrize("components", ["postgres"], indirect=True)
def test_database_ca_preserves_libpq_verification_on_all_connections(
    components: Any, monkeypatch: Any
) -> None:
    import ssl
    from urllib.parse import parse_qsl, urlencode, urlsplit

    import psycopg

    from agent_sandbox.managed_agents.__main__ import database_ca_file

    service = components[0]
    certificate = ssl.DER_cert_to_PEM_cert(
        ssl.create_default_context().get_ca_certs(binary_form=True)[0]
    )
    original_connect = psycopg.connect
    connections = []
    with database_ca_file(certificate) as path:

        def connect(url: str, **options: Any) -> Any:
            assert options["sslrootcert"] == path
            connections.append(options)
            return original_connect(url, **options)

        monkeypatch.setattr(psycopg, "connect", connect)
        parsed = urlsplit(service.store.url)
        url = parsed._replace(
            query=urlencode([*parse_qsl(parsed.query), ("sslmode", "verify-full")])
        ).geturl()
        store = ManagedStore(
            url,
            service.store.application,
            expected_state_id=service.store.state_instance_id,
            database_ca_file=path,
        )
        with store.transaction() as tx:
            assert tx.execute("SELECT 1 AS value").fetchone()["value"] == 1
        with store.session_gate("example-session"):
            pass
        assert len(connections) == 3 and all(c["sslrootcert"] == path for c in connections)
        assert dict(parse_qsl(urlsplit(store.url).query))["sslmode"] == "verify-full"


@pytest.mark.asyncio
async def test_guest_queue_is_not_a_public_turn_before_real_execution(components: Any) -> None:
    service, backend, worker, _ = components
    backend.block_turns = True
    sid = create(service, "held before native execution")["id"]
    running = asyncio.create_task(worker.run(sid))
    runtime = None
    try:
        for _ in range(200):
            await asyncio.sleep(0.01)
            if sid in backend.resources:
                runtime = backend.resources[sid][0].runtime
                sessions = runtime.list_sessions()
                if sessions and sessions[0].turns:
                    break
        assert runtime is not None and sessions[0].turns[0].status == "queued"
        await asyncio.sleep(0.05)
        assert service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns")[1]["data"] == []
        assert not any(
            e["type"] == "agent.session.turn.created" for e in service.events("owner", sid, "0")
        )
    finally:
        if runtime is not None:
            runtime._slots.release()
    assert await running
    events = service.events("owner", sid, "0")
    assert sum(e["type"] == "agent.session.turn.created" for e in events) == 1
    assert all(e.get("turn_id") for e in events if e["type"] == "agent.session.turn.created")


@pytest.mark.asyncio
async def test_http_attachment_total_budget_is_atomic_and_exact_limit_executes(
    components: Any,
) -> None:
    service, _, worker, _ = components
    token = "test-attachment-budget-token"
    auth = TokenAuthenticator(
        {
            "tokens": [
                {
                    "sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "owner": "owner",
                    "scopes": ["agents:read", "agents:write"],
                }
            ]
        }
    )
    server = make_server(service, auth, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}",
            headers={"Authorization": "Bearer " + token},
            trust_env=False,
            timeout=30,
        ) as client:

            def upload(size: int, fill: bytes) -> str:
                response = client.post(
                    "/v1/files",
                    data={"purpose": "user_data"},
                    files={"file": ("input.bin", fill * size)},
                )
                assert response.status_code == 200
                return response.json()["id"]

            first = upload(6 * 1048576, b"a")
            second = upload(6 * 1048576, b"b")

            def body(ids: list[str]) -> dict[str, Any]:
                return {
                    "agent": {"model": "fixture-model"},
                    "input": "consume accepted inputs",
                    "x_agent_sandbox": {
                        "input_files": [
                            {"file_id": file, "path": f"/workspace/input/{i}.bin"}
                            for i, file in enumerate(ids)
                        ]
                    },
                }

            for ids in ([first, second], [first, first]):
                response = client.post("/v1/agents/sessions", json=body(ids))
                assert (
                    response.status_code == 413
                    and response.json()["error"]["code"] == "input_files_too_large"
                )
            assert client.get("/v1/agents/sessions").json()["data"] == []
            with service.store.transaction() as tx:
                assert tx.list("submission") == [] and tx.list("environment") == []
                assert (
                    tx.execute("SELECT COUNT(*) AS total FROM managed_events").fetchone()["total"]
                    == 0
                )
            exact = [upload(5 * 1048576, b"c"), upload(5 * 1048576, b"d")]
            response = client.post("/v1/agents/sessions", json=body(exact))
            assert response.status_code == 201
            sid = response.json()["id"]
            assert await worker.run(sid)
            assert (
                client.get(f"/v1/agents/sessions/{sid}/turns").json()["data"][0]["status"]
                == "completed"
            )
            assert (
                client.get("/v1/agent-sandbox/capabilities").json()["limits"][
                    "max_total_input_file_bytes"
                ]
                == 10485760
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.asyncio
async def test_total_http_deadline_stops_drip_and_preserves_external_cancellation() -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from agent_sandbox.managed_agents.backend import bridge_request

    closed = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            raw = b'{"status":"running","padding":"continuous drip"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            try:
                for character in raw:
                    self.wfile.write(bytes([character]))
                    self.wfile.flush()
                    time.sleep(0.03)
            except OSError:
                closed.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    resource = {
        "url": f"http://127.0.0.1:{server.server_port}",
        "headers": {},
        "token": "test-drip-token",
    }
    try:
        start = time.monotonic()
        with pytest.raises(ManagedError) as deadline:
            await bridge_request(resource, "GET", "/receipt", timeout_seconds=0.15)
        assert deadline.value.code == "guest_request_timeout" and time.monotonic() - start < 0.6
        for _ in range(50):
            if closed.is_set():
                break
            await asyncio.sleep(0.02)
        assert closed.is_set()
        task = asyncio.create_task(bridge_request(resource, "GET", "/receipt", timeout_seconds=5))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.asyncio
async def test_expired_observer_drip_releases_owned_compute_and_preserves_uncertain_turn(
    components: Any,
) -> None:
    service, backend, worker, _ = components
    service.config.limits["maxRunSeconds"] = 1
    service.config.limits["maxToolSeconds"] = 1
    original_create, original_kill = backend.create, backend.kill
    killed_at = []

    async def create_dripping(session: Any, token: str, created: Any) -> Any:
        resource = await original_create(session, token, created)
        bridge, server, _ = backend.resources[session["id"]]
        original_send = server.RequestHandlerClass._send

        def send(handler: Any, status: int, body: Any) -> None:
            if handler.path == "/managed/submissions" and status < 400:
                until = time.monotonic() + 0.5
                while time.monotonic() < until:
                    _, turn = bridge.runtime.find_turn(body["turn_id"])
                    if turn.started_at:
                        break
                    time.sleep(0.005)
                return original_send(handler, status, bridge.get(body["submission_id"]))
            if handler.path.startswith("/managed/submissions/") and handler.command == "GET":
                raw = json.dumps(body).encode()
                handler.send_response(status)
                handler.send_header("Content-Length", str(len(raw)))
                handler.end_headers()
                try:
                    for character in raw:
                        handler.wfile.write(bytes([character]))
                        handler.wfile.flush()
                        time.sleep(0.03)
                except OSError:
                    pass
                return None
            return original_send(handler, status, body)

        server.RequestHandlerClass._send = send
        return resource

    async def kill(resource: Any) -> bool:
        killed_at.append(time.monotonic())
        return await original_kill(resource)

    backend.create, backend.kill = create_dripping, kill
    sid = create(service, "slow")["id"]
    start = time.monotonic()
    assert await worker.run(sid) is False
    assert killed_at and killed_at[0] - start < 1.6
    assert not backend.resources
    with service.store.transaction() as tx:
        submission = tx.list("submission", parent=sid)[0]
        assert submission["status"] == "uncertain"
        assert tx.get(sid)["_cleanup_confirmed"] is True
        turn = tx.get(submission["turn_id"])
        assert (
            turn["status"] == "failed"
            and turn["x_agent_sandbox"]["execution_status"] == "uncertain"
        )
        assert turn["error"]["code"] == "execution_result_uncertain"


@pytest.mark.parametrize("components", ["postgres"], indirect=True)
def test_real_postgres_statement_and_advisory_timeouts_close_connections(
    components: Any, monkeypatch: Any
) -> None:
    from urllib.parse import parse_qsl, urlencode, urlsplit

    import psycopg

    service = components[0]
    store = ManagedStore(
        service.store.url,
        service.store.application,
        expected_state_id=service.store.state_instance_id,
        statement_timeout_ms=200,
        lock_timeout_ms=100,
    )
    raw_connect = psycopg.connect
    blocker = raw_connect(store.url, autocommit=True)
    lock = int.from_bytes(
        hashlib.sha256(store.application.encode()).digest()[:8], "big", signed=True
    )
    opened = []

    def connect(*args: Any, **kwargs: Any) -> Any:
        connection = raw_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(psycopg, "connect", connect)
    try:
        blocker.execute("SELECT pg_advisory_lock(%s)", (lock,))
        start = time.monotonic()
        with pytest.raises(psycopg.errors.LockNotAvailable), store.transaction():
            pass
        assert time.monotonic() - start < 1 and opened[-1].closed
        blocker.execute("SELECT pg_advisory_unlock(%s)", (lock,))
        with store.transaction() as tx:
            assert tx.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == "200ms"
            assert tx.execute("SHOW lock_timeout").fetchone()["lock_timeout"] == "100ms"
        start = time.monotonic()
        with pytest.raises(psycopg.errors.QueryCanceled), store.transaction() as tx:
            tx.execute("SELECT pg_sleep(1)")
        assert time.monotonic() - start < 1 and opened[-1].closed
        parsed = urlsplit(store.url)
        unsafe = parsed._replace(
            query=urlencode([*parse_qsl(parsed.query), ("options", "-c statement_timeout=0")])
        ).geturl()
        with pytest.raises(ValueError, match="options"):
            ManagedStore(unsafe, store.application)
    finally:
        blocker.close()


def test_guest_never_starts_an_already_expired_submission(tmp_path: Path) -> None:
    from agent_sandbox.server.managed import BridgeError

    bridge = ManagedBridge(str(tmp_path / "journal"), str(tmp_path / "workspace"))
    local = bridge.create_session(
        {"nonce": "expired-test", "agent": {"adapter": "qwen-code", "model": "fixture-model"}}
    )
    with pytest.raises(BridgeError) as expired:
        bridge.submit(
            {
                "submission_id": "expired-submission",
                "session_id": local["session_id"],
                "input": "must not execute",
                "files": [],
                "deadline": time.time() - 1,
            }
        )
    assert expired.value.code == "turn_deadline"
    assert not bridge.runtime.get_session(local["session_id"]).turns
    with bridge._db() as db:
        assert db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_sse_http11_chunks_arrive_during_turn_and_close_cleanly(components: Any) -> None:
    service, _, worker, _ = components
    session = service.handle(
        "owner",
        "POST",
        "/v1/agents/sessions",
        {"agent": {"model": "fixture-model"}, "input": "slow", "metadata": {"note": "你好"}},
    )[1]
    sid = session["id"]
    running = asyncio.create_task(worker.run(sid))
    token = "test-stream-token-" + "x" * 32
    document = {
        "tokens": [
            {
                "sha256": hashlib.sha256(token.encode()).hexdigest(),
                "owner": "owner",
                "scopes": ["agents:read", "agents:write"],
            }
        ]
    }
    server = make_server(service, TokenAuthenticator(lambda: document), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        turns = []
        for _ in range(200):
            turns = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns")[1]["data"]
            if turns:
                break
            await asyncio.sleep(0.02)
        assert turns and turns[0]["status"] == "in_progress"

        def receive() -> list[bytes]:
            with socket.create_connection(
                ("127.0.0.1", server.server_port), timeout=3
            ) as connection:
                connection.sendall(
                    (
                        f"GET /v1/agents/sessions/{sid}/events?after=0 HTTP/1.1\r\n"
                        f"Host: localhost\r\nAuthorization: Bearer {token}\r\n\r\n"
                    ).encode()
                )
                with connection.makefile("rb") as stream:
                    assert stream.readline().startswith(b"HTTP/1.1 200 ")
                    headers = {}
                    while (line := stream.readline()) != b"\r\n":
                        name, value = line.decode().strip().split(":", 1)
                        headers[name.lower()] = value.strip()
                    assert headers["transfer-encoding"] == "chunked"
                    assert "content-length" not in headers
                    frames = []
                    for _ in range(100):
                        size = int(stream.readline().strip(), 16)
                        payload = stream.read(size)
                        assert len(payload) == size and stream.read(2) == b"\r\n"
                        if not size:
                            assert any(frame.startswith(b"id:") for frame in frames)
                            assert any("你好".encode() in frame for frame in frames)
                            assert b": heartbeat\n\n" in frames
                            return frames
                        frames.append(payload)
                        if payload == b": heartbeat\n\n":
                            document["tokens"] = []
                    raise AssertionError("bounded chunk reader did not receive terminator")

        frames = await asyncio.to_thread(receive)
        assert frames
        assert (
            service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns/{turns[0]['id']}")[1][
                "status"
            ]
            == "in_progress"
        )
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("failure", ["runtime", "managed"])
def test_sse_failure_after_headers_does_not_write_another_http_response(
    components: Any, monkeypatch: Any, failure: str
) -> None:
    service = components[0]
    sid = create(service)["id"]
    original = service.events
    fetches = 0

    def events(*args: Any, **kwargs: Any) -> Any:
        nonlocal fetches
        fetches += 1
        if fetches > 1:
            if failure == "managed":
                raise ManagedError(503, "service_unavailable", "Example service unavailable")
            raise RuntimeError("example stream failure after headers")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "events", events)
    token = "test-failed-stream-token-" + "x" * 32
    auth = TokenAuthenticator(
        {
            "tokens": [
                {
                    "sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "owner": "owner",
                    "scopes": ["agents:read", "agents:write"],
                }
            ]
        }
    )
    server = make_server(service, auth, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=3) as connection:
            connection.sendall(
                (
                    f"GET /v1/agents/sessions/{sid}/events?after=0 HTTP/1.1\r\n"
                    f"Host: localhost\r\nAuthorization: Bearer {token}\r\n\r\n"
                ).encode()
            )
            with connection.makefile("rb") as stream:
                assert stream.readline().startswith(b"HTTP/1.1 200 ")
                while stream.readline() != b"\r\n":
                    pass
                body = stream.read()
        assert b"id:" in body and b"HTTP/1.1" not in body
        assert not body.endswith(b"0\r\n\r\n")
        with service.store.transaction() as tx:
            assert tx.list("subscription", parent=sid) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
