"""Workflow side effects, runtime preflight and resource ownership regressions."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_sandbox.api.workflow import WorkflowError, launch_workflow
from tests.workflow_fixtures import workflow_manifest


def provider(operations=()):
    return SimpleNamespace(
        id="fixture",
        content_digest=lambda: "sha256:" + "a" * 64,
        describe=lambda: {
            "id": "fixture",
            "operation_contract_version": 1,
            "operations": {"cli": list(operations), "python": list(operations)},
            "workflow_inputs": ["source", "image", "managed"],
            "startup_modes": ["exec", "entrypoint", "none"],
        },
    )


def manifest(input="image"):
    result = workflow_manifest(provider="fixture")
    result["workflows"]["application"].update(input=input, startup="none")
    result["workflows"]["application"]["binding"]["authentication"] = "none"
    if input == "service":
        result["workflows"]["application"]["binding"]["endpoint"] = "explicit-url"
    return result


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


async def test_missing_operations_reject_before_any_resource_or_journal(tmp_path, monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.workflow.Sandbox.create", create)
    journal = tmp_path / "run.jsonl"
    with pytest.raises(WorkflowError, match="requirements-unmet"):
        await launch_workflow(
            manifest(),
            provider=provider(),
            reference="registry/image@sha256:" + "f" * 64,
            journal_path=journal,
        )
    create.assert_not_awaited()
    assert not journal.exists()


@pytest.mark.parametrize(
    ("input_kind", "reference"),
    [("image", "registry/image@sha256:" + "f" * 64), ("managed", "native-template")],
)
async def test_intent_precedes_create_and_owned_resource_is_deleted(
    tmp_path, monkeypatch, input_kind, reference
):
    journal = tmp_path / "run.jsonl"
    server = AsyncMock()
    server.health.return_value = True
    server.discover.return_value = SimpleNamespace(api_version=2, require=lambda endpoint: None)
    sandbox = SimpleNamespace(
        id="owned",
        provider="fixture",
        kill=AsyncMock(),
        application_client=AsyncMock(return_value=server),
    )

    async def create(**kwargs):
        assert events(journal)[-1]["event"] == "create-intent"
        assert kwargs["template"] == reference
        assert "abx_workflow_run" in kwargs["metadata"]
        return sandbox

    monkeypatch.setattr("agent_sandbox.api.workflow.Sandbox.create", create)
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    session = await launch_workflow(
        manifest(input_kind), provider=p, reference=reference, journal_path=journal
    )
    if input_kind == "managed":
        assert events(journal)[0]["artifact_digest"] == "unknown"
    await session.run_command("hello", name="test")
    await session.close()
    sandbox.kill.assert_awaited_once()
    assert events(journal)[-1]["event"] == "cleanup-complete"


@pytest.mark.parametrize(
    ("input_kind", "reference"),
    [("image", "registry/image@sha256:" + "f" * 64), ("managed", "native-template")],
)
async def test_protocol_mismatch_never_sends_application_payload_and_cleans(
    tmp_path, monkeypatch, input_kind, reference
):
    server = AsyncMock()
    server.health.return_value = True
    server.discover.return_value = SimpleNamespace(api_version=99)
    sandbox = SimpleNamespace(
        id="owned",
        provider="fixture",
        kill=AsyncMock(),
        application_client=AsyncMock(return_value=server),
    )
    monkeypatch.setattr(
        "agent_sandbox.api.workflow.Sandbox.create", AsyncMock(return_value=sandbox)
    )
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    with pytest.raises(WorkflowError, match="protocol-mismatch"):
        await launch_workflow(
            manifest(input_kind),
            provider=p,
            reference=reference,
            journal_path=tmp_path / "run",
        )
    sandbox.kill.assert_awaited_once()
    server.commands.run.assert_not_awaited()


async def test_managed_exec_has_no_application_startup(tmp_path, monkeypatch):
    body = manifest("managed")
    body["provides"] = {}
    body["workflows"]["application"] = {
        "kind": "exec",
        "input": "managed",
        "startup": "none",
        "operation": "exec.run",
        "binding": {
            "transport": "exec",
            "endpoint": "provider-native",
            "caller": "host",
            "authentication": "provider",
        },
        "required_operations": [],
    }
    sandbox = SimpleNamespace(
        id="owned",
        provider="fixture",
        kill=AsyncMock(),
        start_server=AsyncMock(),
        application_client=AsyncMock(),
    )
    create = AsyncMock(return_value=sandbox)
    monkeypatch.setattr("agent_sandbox.api.workflow.Sandbox.create", create)
    p = provider(["sandbox.create", "sandbox.delete", "exec.run"])
    async with await launch_workflow(
        body, provider=p, reference="base", journal_path=tmp_path / "run"
    ) as session:
        assert session.sandbox is sandbox
        assert session.server is None
    create.assert_awaited_once()
    sandbox.start_server.assert_not_awaited()
    sandbox.application_client.assert_not_awaited()
    sandbox.kill.assert_awaited_once()


async def test_managed_foreign_provider_rejects_before_create(tmp_path, monkeypatch):
    body = manifest("managed")
    body["provider"] = "foreign-provider"
    create = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.workflow.Sandbox.create", create)
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    with pytest.raises(WorkflowError, match="requirements-unmet"):
        await launch_workflow(body, provider=p, reference="base", journal_path=tmp_path / "run")
    create.assert_not_awaited()


async def test_uncertain_create_is_not_replayed_or_marked_clean(tmp_path, monkeypatch):
    create = AsyncMock(side_effect=TimeoutError("create outcome unknown"))
    monkeypatch.setattr("agent_sandbox.api.workflow.Sandbox.create", create)
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    journal = tmp_path / "run"
    with pytest.raises(TimeoutError):
        await launch_workflow(
            manifest(),
            provider=p,
            reference="registry/image@sha256:" + "f" * 64,
            journal_path=journal,
        )
    create.assert_awaited_once()
    assert "create-uncertain" in [row["event"] for row in events(journal)]
    assert "cleanup-complete" not in [row["event"] for row in events(journal)]


async def test_cleanup_failure_retains_resource_identity(tmp_path, monkeypatch):
    server = AsyncMock()
    server.health.return_value = True
    server.discover.return_value = SimpleNamespace(api_version=2, require=lambda endpoint: None)
    sandbox = SimpleNamespace(
        id="owned",
        provider="fixture",
        kill=AsyncMock(side_effect=RuntimeError()),
        application_client=AsyncMock(return_value=server),
    )
    monkeypatch.setattr(
        "agent_sandbox.api.workflow.Sandbox.create", AsyncMock(return_value=sandbox)
    )
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    journal = tmp_path / "run"
    session = await launch_workflow(
        manifest(), provider=p, reference="registry/image@sha256:" + "f" * 64, journal_path=journal
    )
    with pytest.raises(WorkflowError, match="cleanup-failed"):
        await session.close()
    assert events(journal)[-1] == {
        "event": "cleanup-failed",
        "provider_id": "fixture",
        "sandbox_id": "owned",
    }


async def test_client_close_failure_still_deletes_owned_sandbox(tmp_path):
    from agent_sandbox.api.workflow import WorkflowSession, _Journal

    server = SimpleNamespace(aclose=AsyncMock(side_effect=RuntimeError("close failed")))
    sandbox = SimpleNamespace(id="owned", provider="fixture", kill=AsyncMock())
    journal = tmp_path / "run"
    session = WorkflowSession({}, sandbox, server, _Journal(journal))
    with pytest.raises(WorkflowError, match="cleanup-failed"):
        await session.close()
    sandbox.kill.assert_awaited_once()
    assert any(row["event"] == "deleted" for row in events(journal))
    assert not any(row["event"] == "cleanup-complete" for row in events(journal))


async def test_mutable_image_never_creates_or_executes(tmp_path, monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.workflow.Sandbox.create", create)
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    with pytest.raises(WorkflowError, match="immutable-image-reference-required"):
        await launch_workflow(
            manifest(), provider=p, reference="image:latest", journal_path=tmp_path / "run"
        )
    create.assert_not_awaited()


async def test_created_id_survives_session_assembly_failure(tmp_path, monkeypatch):
    journal = tmp_path / "run"

    async def fail(**kwargs):
        kwargs["on_created"]("known-owned")
        assert events(journal)[-1]["sandbox_id"] == "known-owned"
        error = RuntimeError("session assembly failed")
        error.owned_resource = {"provider_id": "fixture", "sandbox_id": "known-owned"}
        error.resource_cleanup_complete = False
        raise error

    monkeypatch.setattr("agent_sandbox.api.workflow.Sandbox.create", fail)
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    with pytest.raises(RuntimeError, match="session assembly failed"):
        await launch_workflow(
            manifest(), provider=p, reference="sha256:" + "f" * 64, journal_path=journal
        )
    rows = events(journal)
    assert any(row.get("sandbox_id") == "known-owned" for row in rows)
    assert rows[-1]["event"] == "reconciliation-required"
    assert not any(row["event"] == "cleanup-complete" for row in rows)


async def test_cancelled_close_waits_for_owned_resource_cleanup(tmp_path):
    import asyncio

    from agent_sandbox.api.workflow import WorkflowSession, _Journal

    entered, release = asyncio.Event(), asyncio.Event()

    async def kill():
        entered.set()
        await release.wait()

    sandbox = SimpleNamespace(id="owned", provider="fixture", kill=AsyncMock(side_effect=kill))
    session = WorkflowSession({}, sandbox, None, _Journal(tmp_path / "run"))
    task = asyncio.create_task(session.close())
    await entered.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    sandbox.kill.assert_awaited_once()
    assert events(tmp_path / "run")[-1]["event"] == "cleanup-complete"


async def test_journal_failure_never_blocks_owned_cleanup(tmp_path):
    from agent_sandbox.api.workflow import WorkflowSession, _Journal

    journal = _Journal(tmp_path / "run")
    journal.append("created", sandbox_id="owned", provider_id="fixture")
    journal.append = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full"))
    sandbox = SimpleNamespace(id="owned", provider="fixture", kill=AsyncMock())
    server = SimpleNamespace(aclose=AsyncMock())
    session = WorkflowSession({}, sandbox, server, journal)
    with pytest.raises(WorkflowError, match="journal-write-failed"):
        await session.close()
    sandbox.kill.assert_awaited_once()
    server.aclose.assert_awaited_once()
    assert events(tmp_path / "run")[-1]["sandbox_id"] == "owned"


@pytest.mark.parametrize("as_object", [False, True])
async def test_named_builtin_provider_is_not_reregistered(tmp_path, monkeypatch, as_object):
    from agent_sandbox.providers.registry import builtin_provider

    sandbox = SimpleNamespace(id="owned", provider="alicloud-express", kill=AsyncMock())
    create = AsyncMock(return_value=sandbox)
    monkeypatch.setattr("agent_sandbox.api.workflow.Sandbox.create", create)
    spec = manifest("managed")
    spec["provider"] = "alicloud-express"
    spec["provides"] = {}
    spec["workflows"]["application"].update(
        kind="exec",
        operation="exec.run",
        startup="none",
        binding={
            "transport": "exec",
            "endpoint": "provider-native",
            "caller": "host",
            "authentication": "provider",
        },
    )
    spec["workflows"]["application"].pop("service")
    async with await launch_workflow(
        spec,
        provider=builtin_provider() if as_object else "alicloud-express",
        reference="base",
        journal_path=tmp_path / "run",
    ):
        pass
    assert create.call_args.kwargs["provider"] == "alicloud-express"
    assert builtin_provider().id == "alicloud-express"
