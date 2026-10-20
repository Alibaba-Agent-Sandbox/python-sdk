"""Application acceptance, crash fencing, cancellation and remote-tool regressions."""

from __future__ import annotations

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest

from agent_sandbox.applications import (
    Application,
    ApplicationError,
    ApplicationRuntime,
    Artifact,
    ExecutionResult,
    ExternalAgentExecutor,
    Principal,
    Store,
)


@pytest.fixture
def store(tmp_path):
    return Store("sqlite:///" + str(tmp_path / "state.db"), local=True)


@pytest.fixture
def app():
    return Application("revision-1", "external", {"template": "ready-ref", "modelRef": "model"})


class EchoExecutor:
    def __init__(self, *, delay: float = 0, cleanup: bool = True):
        self.delay, self.cleanup = delay, cleanup
        self.closed = False

    async def execute(self, context):
        context.check()
        await asyncio.sleep(self.delay)
        return ExecutionResult(context.prompt, (Artifact("answer.txt", b"artifact"),))

    async def close(self):
        self.closed = True
        return self.cleanup


def runtime_for(store, app, executor=None, send=None):
    return ApplicationRuntime(
        store,
        {app.revision: app},
        lambda _: executor or EchoExecutor(),
        send or (lambda payload: None),
        lambda token: None,
        heartbeat_seconds=0.01,
        cleanup_seconds=0.1,
    )


def accept(runtime, key="request-1", owner="owner", text="hello"):
    principal = Principal(owner, frozenset(runtime.applications))
    return runtime.create(
        principal, key, {"applicationRevision": "revision-1", "input": {"text": text}}
    )


def test_accept_idempotency_ownership_and_restart(store, app, tmp_path):
    runtime = runtime_for(store, app)
    run = accept(runtime)
    assert accept(runtime)["id"] == run["id"]
    with pytest.raises(ApplicationError, match="another request"):
        accept(runtime, text="different")
    with pytest.raises(ApplicationError) as foreign:
        store.get(run["id"], "other")
    assert foreign.value.status == 404
    restarted = Store("sqlite:///" + str(tmp_path / "state.db"), local=True)
    assert restarted.get(run["id"])["status"] == "accepted"
    assert restarted.events(run["id"], "owner")[0]["type"] == "run.accepted"
    assert restarted.next_dispatch()[0] == run["id"]


def test_concurrent_accept_and_claim_are_single(store, app):
    runtime = runtime_for(store, app)
    with ThreadPoolExecutor(8) as pool:
        ids = list(pool.map(lambda _: accept(runtime)["id"], range(20)))
    assert len(set(ids)) == 1
    with ThreadPoolExecutor(8) as pool:
        claims = list(pool.map(lambda _: store.claim(ids[0], app), range(20)))
    assert sum(claim is not None for claim in claims) == 1


def test_global_admission_and_execution_capacity(store, app):
    app = replace(app, max_queued_runs=2, max_concurrent_runs=1)
    runtime = runtime_for(store, app)
    first, second = accept(runtime), accept(runtime, key="two")
    with pytest.raises(ApplicationError) as full:
        accept(runtime, key="three")
    assert full.value.status == 429
    assert store.claim(first["id"], app)
    assert store.claim(second["id"], app) is None
    assert store.get(second["id"])["attempt"] is None


def test_revision_change_fails_closed(store, app):
    runtime = runtime_for(store, app)
    run = accept(runtime)
    changed = replace(app, snapshot={"template": "different"})
    with pytest.raises(ApplicationError, match="new application revision"):
        accept(runtime_for(store, changed), key="two")
    assert store.claim(run["id"], changed) is None
    assert store.get(run["id"])["failure"] == "revision_unavailable"


@pytest.mark.asyncio
async def test_worker_success_durable_results_artifacts_and_duplicate(store, app):
    runtime = runtime_for(store, app)
    run = accept(runtime)
    assert await runtime.work(run["id"])
    assert not await runtime.work(run["id"])
    result = store.result(run["id"], "owner")
    assert result["status"] == "succeeded" and result["outputText"] == "hello"
    artifact = result["artifacts"][0]
    assert store.artifact(run["id"], "owner", artifact["id"])[0] == b"artifact"
    with pytest.raises(ApplicationError) as foreign:
        store.artifact(run["id"], "other", artifact["id"])
    assert foreign.value.status == 404
    events = store.events(run["id"], "owner")
    assert [e["type"] for e in events] == ["run.accepted", "run.started", "run.completed"]
    assert [e["seq"] for e in events] == [1, 2, 3]


@pytest.mark.asyncio
async def test_cancel_before_claim_never_runs(store, app):
    runtime = runtime_for(store, app)
    run = accept(runtime)
    assert store.cancel(run["id"], "owner")["status"] == "cancelled"
    assert not await runtime.work(run["id"])
    assert store.get(run["id"])["attempt"] is None


@pytest.mark.asyncio
async def test_cancel_running_waits_for_verified_cleanup(store, app):
    executor = EchoExecutor(delay=30)
    runtime = runtime_for(store, app, executor)
    run = accept(runtime)
    task = asyncio.create_task(runtime.work(run["id"]))
    await asyncio.sleep(0.03)
    assert store.cancel(run["id"], "owner")["status"] == "cancelling"
    await task
    assert executor.closed
    assert store.get(run["id"])["status"] == "cancelled"
    assert store.cancel(run["id"], "owner")["status"] == "cancelled"


@pytest.mark.asyncio
async def test_uncertain_cleanup_never_claims_cancellation(store, app):
    runtime = runtime_for(store, app, EchoExecutor(delay=30, cleanup=False))
    run = accept(runtime)
    task = asyncio.create_task(runtime.work(run["id"]))
    await asyncio.sleep(0.03)
    store.cancel(run["id"], "owner")
    await task
    assert store.get(run["id"])["status"] == "requires_reconcile"
    assert store.claim(run["id"], app) is None
    with pytest.raises(ApplicationError) as pending:
        store.result(run["id"], "owner")
    assert pending.value.code == "not_ready"


def test_crash_lease_expiry_does_not_replay_remote_work(store, app, monkeypatch):
    run = accept(runtime_for(store, app))
    attempt = store.claim(run["id"], app, lease_seconds=1)
    now = time.time()
    monkeypatch.setattr("agent_sandbox.applications.store.time.time", lambda: now + 2)
    assert store.reconcile() == 1
    assert store.get(run["id"])["status"] == "requires_reconcile"
    assert store.claim(run["id"], app) is None
    with pytest.raises(ApplicationError, match="lease"):
        store.finish(run["id"], attempt, "succeeded", ExecutionResult("late"))


def test_trusted_reconciliation_requires_proof_and_expected_attempt(store, app):
    runtime = runtime_for(store, app)
    run = accept(runtime)
    attempt = store.claim(run["id"], app)
    store.started(run["id"], attempt)
    store.bind_resource(run["id"], attempt, {"sandboxId": "owned-sandbox"})
    store.uncertain(run["id"], attempt)
    assert not store.resolve_uncertain(run["id"], "wrong-attempt", lambda _: True)
    assert not store.resolve_uncertain(run["id"], attempt, lambda _: False)
    observations = []

    def verify(proof):
        observations.append(proof)
        return True  # Trusted test verifier proves both worker and resources stopped.

    assert store.resolve_uncertain(run["id"], attempt, verify)
    assert observations[0]["resource"]["sandboxId"] == "owned-sandbox"
    assert store.result(run["id"], "owner")["status"] == "failed"
    assert not store.resolve_uncertain(run["id"], attempt, verify)


def test_cancel_uncertain_keeps_lease_fenced_and_reserves_recovery_event(store, app):
    app = replace(app, max_events=5)
    runtime = runtime_for(store, app)
    run = accept(runtime)
    attempt = store.claim(run["id"], app)
    store.started(run["id"], attempt)
    store.uncertain(run["id"], attempt)
    assert store.cancel(run["id"], "owner")["status"] == "requires_reconcile"
    with pytest.raises(ApplicationError, match="lease"):
        store.finish(run["id"], attempt, "succeeded", ExecutionResult("late"))
    assert store.resolve_uncertain(run["id"], attempt, lambda _: True)
    assert store.result(run["id"], "owner")["status"] == "cancelled"
    assert len(store.events(run["id"], "owner")) == 5


def test_cancel_and_success_race_cancellation_wins_if_committed(store, app):
    run = accept(runtime_for(store, app))
    attempt = store.claim(run["id"], app)
    store.cancel(run["id"], "owner")
    store.finish(run["id"], attempt, "succeeded", ExecutionResult("late"))
    assert store.result(run["id"], "owner")["status"] == "cancelled"
    assert store.result(run["id"], "owner")["outputText"] == ""


def test_outbox_send_crash_and_redelivery(store, app, monkeypatch):
    run = accept(runtime_for(store, app))
    leased = store.next_dispatch(lease_seconds=1)
    assert leased[0] == run["id"]
    assert store.next_dispatch() is None
    now = time.time()
    monkeypatch.setattr("agent_sandbox.applications.store.time.time", lambda: now + 2)
    retry = store.next_dispatch()
    assert retry[0] == run["id"] and retry[1] != leased[1]
    store.dispatched(*leased, success=True)  # Stale acknowledgement cannot delete the retry.
    assert store.claim(run["id"], app)
    store.dispatched(*retry, success=True)
    assert store.next_dispatch() is None


def test_pending_deadline_can_expire_without_a_sandbox(store, app, monkeypatch):
    run = accept(runtime_for(store, app))
    now = time.time()
    monkeypatch.setattr("agent_sandbox.applications.store.time.time", lambda: now + 1000)
    store.reconcile()
    assert store.result(run["id"], "owner")["status"] == "timed_out"


def test_sqlite_never_allowed_as_fc_durable_state(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="explicit local"):
        Store("sqlite:///" + str(tmp_path / "state.db"))
    monkeypatch.setenv("FC_FUNCTION_NAME", "worker")
    with pytest.raises(ValueError, match="explicit local"):
        Store("sqlite:///" + str(tmp_path / "state.db"), local=True)


class ToolModel:
    def __init__(self):
        self.calls = 0

    async def complete(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "out.txt", "content": "remote"}),
                        },
                    }
                ],
            }
        assert messages[-1] == {"role": "tool", "tool_call_id": "call-1", "content": "written"}
        return {"role": "assistant", "content": "done"}


@pytest.mark.asyncio
async def test_external_loop_routes_tools_to_sandbox_not_host(store, app):
    writes = []
    killed = []

    async def write(path, content):
        writes.append((path, content))

    async def kill():
        killed.append(True)

    sandbox = SimpleNamespace(sandbox_id="sandbox-1", files=SimpleNamespace(write=write), kill=kill)

    async def sandbox_factory(context):
        return sandbox

    executor = ExternalAgentExecutor(ToolModel(), sandbox_factory)
    runtime = runtime_for(store, app, executor)
    run = accept(runtime)
    await runtime.work(run["id"])
    assert writes == [("/home/user/out.txt", "remote")]
    assert killed == [True]
    assert store.result(run["id"], "owner")["outputText"] == "done"
    assert "sandbox-1" in store.get(run["id"])["resource"]


@pytest.mark.asyncio
async def test_exception_text_is_never_public(store, app):
    class UnsafeExecutor(EchoExecutor):
        async def execute(self, context):
            raise RuntimeError("private-model-credential-placeholder")

    runtime = runtime_for(store, app, UnsafeExecutor())
    run = accept(runtime)
    await runtime.work(run["id"])
    serialized = json.dumps(store.result(run["id"], "owner"))
    assert "private-model" not in serialized
    assert store.result(run["id"], "owner")["failureCode"] == "execution_failed"


@pytest.mark.asyncio
async def test_output_budget_yields_safe_failure(store, app):
    runtime = runtime_for(store, replace(app, max_output_bytes=2))
    run = accept(runtime)
    await runtime.work(run["id"])
    assert store.result(run["id"], "owner")["failureCode"] == "output_budget"


def test_scope_and_revision_cannot_be_supplied_by_client(store, app):
    runtime = runtime_for(store, app)
    principal = Principal("owner", frozenset({app.revision}), frozenset({"runs:read"}))
    with pytest.raises(ApplicationError) as denied:
        runtime.create(
            principal, "key", {"applicationRevision": app.revision, "input": {"text": "x"}}
        )
    assert denied.value.status == 403
    with pytest.raises(ApplicationError) as denied:
        runtime.create(
            Principal("owner", frozenset()),
            "key",
            {"applicationRevision": app.revision, "input": {"text": "x"}},
        )
    assert denied.value.status == 404
