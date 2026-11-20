"""Managed Turn retrieval and lifecycle events share stable public identities."""

from __future__ import annotations

import hashlib
import threading
from typing import Any

import pytest

from agent_sandbox.managed_agents import ManagedConfig, ManagedService, ManagedStore
from agent_sandbox.managed_agents.http import TokenAuthenticator, make_server
from agent_sandbox.managed_agents.store import new_object
from agent_sandbox.managed_agents.worker import ManagedWorker


@pytest.fixture
def service(tmp_path: Any) -> ManagedService:
    return ManagedService(
        ManagedStore("sqlite:///" + str(tmp_path / "state.db"), local=True),
        ManagedConfig("revision-a", "template-a", {"test-model": "qwen-code"}),
    )


def start(service: ManagedService, agent_id: str | None = None) -> tuple[str, str, ManagedWorker]:
    body: dict[str, Any] = {"input": "Create a report"}
    body.update({"agent_id": agent_id} if agent_id else {"agent": {"model": "test-model"}})
    session, subid = service.create_session("owner", body)
    sid = session["id"]
    assert subid is not None
    with service.store.transaction() as tx:
        session = tx.get(sid)
        session["_claim"] = "test-claim"
        tx.put(session)
    worker = ManagedWorker(service, None)
    worker._ingest(
        sid,
        subid,
        "test-claim",
        {
            "events": [
                {
                    "seq": 1,
                    "wire": {
                        "type": "agent.session.turn.in_progress",
                        "event_id": "guest-event",
                        "session_id": "guest-session",
                        "turn_id": "guest-turn",
                        "turn": {"id": "guest-turn", "started_at": 1700000000.75},
                    },
                }
            ]
        },
    )
    return sid, subid, worker


def finish(service: ManagedService, sid: str, subid: str, worker: ManagedWorker) -> None:
    worker._finish(
        sid,
        subid,
        "test-claim",
        {"status": "completed", "turn": {"usage": None}, "items": [], "artifacts": []},
    )


def test_turn_retrieval_and_events_preserve_host_identity_and_integer_seconds(
    service: ManagedService,
) -> None:
    sid, subid, worker = start(service)
    session = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}")[1]
    turns = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns")[1]["data"]
    turn = turns[0]
    assert turn["agent_id"] == session["agent"]["id"]
    assert turn["session_id"] == sid and turn["id"] != "guest-turn"
    assert type(turn["created_at"]) is int
    assert type(turn["started_at"]) is int
    assert turn["started_at"] == 1700000000
    assert turn["subagent_id"] is None and turn["completed_at"] is None
    in_progress = next(
        e
        for e in service.events("owner", sid, "0")
        if e["type"] == "agent.session.turn.in_progress"
    )
    assert in_progress["turn"] == turn
    assert in_progress["turn_id"] == turn["id"] and in_progress["session_id"] == sid
    with service.store.transaction() as tx:
        assert type(tx.get(turn["id"])["created_at"]) is float
    finish(service, sid, subid, worker)
    terminal = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns/{turn['id']}")[1]
    assert type(terminal["completed_at"]) is int
    assert terminal["agent_id"] == turn["agent_id"]
    assert terminal["started_at"] == turn["started_at"]
    assert terminal["status"] == "completed"
    event = next(
        e for e in service.events("owner", sid, "0") if e["type"] == "agent.session.turn.completed"
    )
    assert event["turn"] == terminal


def test_saved_agent_identity_stays_frozen_after_definition_update_and_delete(
    service: ManagedService,
) -> None:
    agent = service.handle("owner", "POST", "/v1/agents", {"model": "test-model"})[1]
    sid, subid, worker = start(service, agent["id"])
    service.handle("owner", "POST", "/v1/agents/" + agent["id"], {"instructions": "Changed"})
    service.handle("owner", "DELETE", "/v1/agents/" + agent["id"])
    finish(service, sid, subid, worker)
    turn = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns")[1]["data"][0]
    session = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}")[1]
    assert turn["agent_id"] == session["agent"]["id"] == agent["id"]
    assert session["agent"].get("instructions") != "Changed"


def test_legacy_turn_projection_uses_frozen_session_without_rewriting_private_state(
    service: ManagedService,
) -> None:
    session, _ = service.create_session("owner", {"agent": {"model": "test-model"}})
    sid = session["id"]
    with service.store.transaction() as tx:
        legacy = tx.get(sid)
        legacy["agent"].pop("id", None)
        tx.put(legacy)
        turn = new_object(
            "turn",
            "owner",
            parent=sid,
            session_id=sid,
            status="completed",
            completed_at=1700000001.75,
            usage=None,
            error=None,
        )
        tx.put(turn)
    first = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}")[1]
    again = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}")[1]
    result = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns/{turn['id']}")[1]
    listed = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns")[1]["data"][0]
    assert first["agent"]["id"] == again["agent"]["id"] == result["agent_id"]
    assert result["started_at"] is None and result["subagent_id"] is None
    assert result == listed
    assert result["completed_at"] == 1700000001
    with service.store.transaction() as tx:
        assert "id" not in tx.get(sid)["agent"]
        assert "started_at" not in tx.get(turn["id"])


def test_supported_turn_events_parse_with_official_openai_types(service: ManagedService) -> None:
    openai = pytest.importorskip("openai")
    turn_types = pytest.importorskip("openai.types.beta.agents.sessions.turn")
    progress_types = pytest.importorskip("openai.types.beta.agent_session_turn_in_progress_event")
    completed_types = pytest.importorskip("openai.types.beta.agent_session_turn_completed_event")
    sid, subid, worker = start(service)
    finish(service, sid, subid, worker)
    events = service.events("owner", sid, "0")
    for kind, model in (
        ("agent.session.turn.in_progress", progress_types.AgentSessionTurnInProgressEvent),
        ("agent.session.turn.completed", completed_types.AgentSessionTurnCompletedEvent),
    ):
        event = model.model_validate(next(e for e in events if e["type"] == kind))
        assert event.turn.subagent_id is None
        assert event.turn.id == event.turn_id and event.turn.session_id == sid
        assert event.turn.agent_id
    turn = service.handle("owner", "GET", f"/v1/agents/sessions/{sid}/turns")[1]["data"][0]
    parsed = turn_types.Turn.model_validate(turn)
    assert parsed.status == "completed" and parsed.completed_at is not None
    token = "placeholder-official-client-local-fixture"
    auth = TokenAuthenticator(
        {
            "tokens": [
                {
                    "sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "owner": "owner",
                    "scopes": ["agents:read"],
                }
            ]
        }
    )
    server = make_server(service, auth, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with openai.OpenAI(
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            api_key=token,
            max_retries=0,
            timeout=5,
        ) as client:
            retrieved = client.beta.agents.sessions.turns.retrieve(parsed.id, session_id=sid)
            assert retrieved.agent_id == parsed.agent_id
            assert retrieved.subagent_id is None and retrieved.status == "completed"
            with client.beta.agents.sessions.events.stream(
                sid, extra_query={"after": "0"}
            ) as stream:
                for event in stream:
                    if event.type == "agent.session.turn.completed":
                        assert event.turn.subagent_id is None
                        assert event.turn.id == retrieved.id
                        break
                else:
                    pytest.fail("The completed Turn was absent from its durable event stream")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_capabilities_only_advertise_configured_harness_and_actual_tool_timing(
    service: ManagedService,
) -> None:
    configured = ManagedService(
        service.store, ManagedConfig("revision-a", "template-a", {"test-model": "opencode"})
    )
    caps = configured.handle("owner", "GET", "/v1/agent-sandbox/capabilities")[1]
    assert caps["adapters"] == ["opencode"]
    assert set(caps["adapter_capabilities"]) == {"opencode"}
    assert caps["adapter_capabilities"]["opencode"]["tool_events"] == "completed_only"
    assert caps["adapter_capabilities"]["opencode"]["per_tool_timeout"] is False
    assert caps["features"]["steering"] is False
    runtime = configured.handle("owner", "GET", "/v1/agents/runtimes")[1]["data"][0]
    assert runtime["id"] == "opencode" and runtime["configured"] is True
    assert runtime["installed"] is None


def test_codex_capabilities_describe_complete_messages(service: ManagedService) -> None:
    configured = ManagedService(
        service.store, ManagedConfig("revision-a", "template-a", {"test-model": "codex"})
    )
    caps = configured.handle("owner", "GET", "/v1/agent-sandbox/capabilities")[1]
    assert caps["adapter_capabilities"]["codex"]["streaming"] == "complete_messages"
