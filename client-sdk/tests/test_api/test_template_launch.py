"""Workflow side effects, runtime preflight and resource ownership regressions."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_sandbox.api.template import TemplateLaunchError, launch_template
from tests.template_fixtures import template_manifest


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
    result = template_manifest()
    result.pop("start_cmd", None)
    if input == "image":
        result["image"] = "registry/image@sha256:" + "f" * 64
    elif input == "managed":
        result.update(provider="fixture", template_id="base")
    return result


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


async def test_missing_operations_reject_before_any_resource_or_journal(tmp_path, monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    journal = tmp_path / "run.jsonl"
    with pytest.raises(TemplateLaunchError, match="missing-operations|provider-mismatch"):
        await launch_template(
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
        assert "abx_template_run" in kwargs["metadata"]
        return sandbox

    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    session = await launch_template(
        manifest(input_kind), provider=p, reference=reference, journal_path=journal
    )
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
        "agent_sandbox.api.template.Sandbox.create", AsyncMock(return_value=sandbox)
    )
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    with pytest.raises(TemplateLaunchError, match="protocol-mismatch"):
        await launch_template(
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
    sandbox = SimpleNamespace(
        id="owned",
        provider="fixture",
        kill=AsyncMock(),
        start_server=AsyncMock(),
        application_client=AsyncMock(),
    )
    create = AsyncMock(return_value=sandbox)
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    p = provider(["sandbox.create", "sandbox.delete", "exec.run"])
    async with await launch_template(
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
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    with pytest.raises(TemplateLaunchError, match="missing-operations|provider-mismatch"):
        await launch_template(body, provider=p, reference="base", journal_path=tmp_path / "run")
    create.assert_not_awaited()


async def test_uncertain_create_is_not_replayed_or_marked_clean(tmp_path, monkeypatch):
    create = AsyncMock(side_effect=TimeoutError("create outcome unknown"))
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    journal = tmp_path / "run"
    with pytest.raises(TimeoutError):
        await launch_template(
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
        "agent_sandbox.api.template.Sandbox.create", AsyncMock(return_value=sandbox)
    )
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    journal = tmp_path / "run"
    session = await launch_template(
        manifest(), provider=p, reference="registry/image@sha256:" + "f" * 64, journal_path=journal
    )
    with pytest.raises(TemplateLaunchError, match="cleanup-failed"):
        await session.close()
    assert events(journal)[-1] == {
        "event": "cleanup-failed",
        "provider_id": "fixture",
        "sandbox_id": "owned",
    }


async def test_client_close_failure_still_deletes_owned_sandbox(tmp_path):
    from agent_sandbox.api.template import TemplateSession, _Journal

    server = SimpleNamespace(aclose=AsyncMock(side_effect=RuntimeError("close failed")))
    sandbox = SimpleNamespace(id="owned", provider="fixture", kill=AsyncMock())
    journal = tmp_path / "run"
    session = TemplateSession(
        {"services": {"app": {"protocol": "agent-sandbox-server"}}},
        sandbox,
        {"app": server},
        _Journal(journal),
    )
    with pytest.raises(TemplateLaunchError, match="cleanup-failed"):
        await session.close()
    sandbox.kill.assert_awaited_once()
    assert any(row["event"] == "deleted" for row in events(journal))
    assert not any(row["event"] == "cleanup-complete" for row in events(journal))


async def test_created_id_survives_session_assembly_failure(tmp_path, monkeypatch):
    journal = tmp_path / "run"

    async def fail(**kwargs):
        kwargs["on_created"]("known-owned")
        assert events(journal)[-1]["sandbox_id"] == "known-owned"
        error = RuntimeError("session assembly failed")
        error.owned_resource = {"provider_id": "fixture", "sandbox_id": "known-owned"}
        error.resource_cleanup_complete = False
        raise error

    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", fail)
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    with pytest.raises(RuntimeError, match="session assembly failed"):
        await launch_template(
            manifest(), provider=p, reference="sha256:" + "f" * 64, journal_path=journal
        )
    rows = events(journal)
    assert any(row.get("sandbox_id") == "known-owned" for row in rows)
    assert rows[-1]["event"] == "reconciliation-required"
    assert not any(row["event"] == "cleanup-complete" for row in rows)


async def test_cancelled_close_waits_for_owned_resource_cleanup(tmp_path):
    import asyncio

    from agent_sandbox.api.template import TemplateSession, _Journal

    entered, release = asyncio.Event(), asyncio.Event()

    async def kill():
        entered.set()
        await release.wait()

    sandbox = SimpleNamespace(id="owned", provider="fixture", kill=AsyncMock(side_effect=kill))
    session = TemplateSession({"services": {}}, sandbox, {}, _Journal(tmp_path / "run"))
    task = asyncio.create_task(session.close())
    await entered.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    sandbox.kill.assert_awaited_once()
    assert events(tmp_path / "run")[-1]["event"] == "cleanup-complete"


async def test_journal_failure_never_blocks_owned_cleanup(tmp_path):
    from agent_sandbox.api.template import TemplateSession, _Journal

    journal = _Journal(tmp_path / "run")
    journal.append("created", sandbox_id="owned", provider_id="fixture")
    journal.append = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full"))
    sandbox = SimpleNamespace(id="owned", provider="fixture", kill=AsyncMock())
    server = SimpleNamespace(aclose=AsyncMock())
    session = TemplateSession(
        {"services": {"app": {"protocol": "agent-sandbox-server"}}},
        sandbox,
        {"app": server},
        journal,
    )
    with pytest.raises(TemplateLaunchError, match="journal-write-failed"):
        await session.close()
    sandbox.kill.assert_awaited_once()
    server.aclose.assert_awaited_once()
    assert events(tmp_path / "run")[-1]["sandbox_id"] == "owned"


@pytest.mark.parametrize("as_object", [False, True])
async def test_named_builtin_provider_is_not_reregistered(tmp_path, monkeypatch, as_object):
    from agent_sandbox.providers.registry import builtin_provider

    sandbox = SimpleNamespace(id="owned", provider="alicloud-express", kill=AsyncMock())
    create = AsyncMock(return_value=sandbox)
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    spec = manifest("managed")
    spec["provider"] = "alicloud-express"
    spec["provides"] = {}
    async with await launch_template(
        spec,
        provider=builtin_provider() if as_object else "alicloud-express",
        reference="base",
        journal_path=tmp_path / "run",
    ):
        pass
    assert create.call_args.kwargs["provider"] == "alicloud-express"
    assert builtin_provider().id == "alicloud-express"


async def test_all_services_start_together_without_invoking_commands(tmp_path, monkeypatch):
    from agent_sandbox.models.process import ProcessResult

    body = template_manifest(
        ready_cmd="test -f /tmp/ready",
        env={"ABX_SERVER_TOKEN": ""},
        resources={"cpu": 2, "memory": 2048},
    )
    body["provides"]["second"] = {**body["provides"]["app"], "port": 9001}
    first, second = AsyncMock(), AsyncMock()
    for server in (first, second):
        server.health.return_value = True
        server.discover.return_value = SimpleNamespace(api_version=2)
    sandbox = SimpleNamespace(
        id="owned",
        provider="fixture",
        kill=AsyncMock(),
        application_client=AsyncMock(side_effect=[first, second]),
        commands=SimpleNamespace(run=AsyncMock(return_value=ProcessResult(exit_code=0))),
    )
    create = AsyncMock(return_value=sandbox)
    start = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    monkeypatch.setattr("agent_sandbox.api.template._dispatch_start", start)
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve", "exec.run"])
    async with await launch_template(
        body,
        provider=p,
        reference="prepared-provider-reference",
        application_token="placeholder-token",
        journal_path=tmp_path / "run",
    ) as session:
        assert set(session.services) == set(session.servers) == {"app", "second"}
        assert session.server is None
        start.assert_awaited_once_with(sandbox, body["start_cmd"], 30)
        sandbox.commands.run.assert_awaited_once_with(body["ready_cmd"], timeout=30)
        assert create.call_args.kwargs["envs"]["ABX_SERVER_TOKEN"] == "placeholder-token"
        assert create.call_args.kwargs["cpu"] == 2
        assert create.call_args.kwargs["memory"] == 2048
        for call in sandbox.application_client.await_args_list:
            assert call.kwargs["token"] == "placeholder-token"
        first.discover.assert_awaited_once()
        second.discover.assert_awaited_once()
        first.commands.run.assert_not_awaited()
        second.commands.run.assert_not_awaited()
    first.aclose.assert_awaited_once()
    second.aclose.assert_awaited_once()
    sandbox.kill.assert_awaited_once()


async def test_second_service_failure_closes_every_resolved_client(tmp_path, monkeypatch):
    body = manifest()
    body["provides"]["second"] = {**body["provides"]["app"], "port": 9001}
    first, second = AsyncMock(), AsyncMock()
    for server, version in ((first, 2), (second, 99)):
        server.health.return_value = True
        server.discover.return_value = SimpleNamespace(api_version=version)
    sandbox = SimpleNamespace(
        id="owned",
        provider="fixture",
        kill=AsyncMock(),
        application_client=AsyncMock(side_effect=[first, second]),
    )
    monkeypatch.setattr(
        "agent_sandbox.api.template.Sandbox.create", AsyncMock(return_value=sandbox)
    )
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    with pytest.raises(TemplateLaunchError, match="protocol-mismatch: second"):
        await launch_template(body, provider=p, journal_path=tmp_path / "run")
    first.aclose.assert_awaited_once()
    second.aclose.assert_awaited_once()
    sandbox.kill.assert_awaited_once()


async def test_source_requires_preparation_before_any_resource(tmp_path, monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    with pytest.raises(TemplateLaunchError, match="prepare-source-with-cli"):
        await launch_template(
            template_manifest(), provider=provider(), journal_path=tmp_path / "run"
        )
    create.assert_not_awaited()
    assert not (tmp_path / "run").exists()


async def test_fixed_mutable_image_is_rejected_before_create(tmp_path, monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    body = manifest()
    body["image"] = "image:latest"
    with pytest.raises(TemplateLaunchError, match="immutable-image-reference-required"):
        await launch_template(body, provider=provider(), journal_path=tmp_path / "run")
    create.assert_not_awaited()


async def test_other_protocol_is_exposed_without_guessing_http_routes(tmp_path, monkeypatch):
    body = manifest()
    body["provides"]["app"]["protocol"] = "custom-http"
    server = AsyncMock()
    sandbox = SimpleNamespace(
        id="owned",
        provider="fixture",
        kill=AsyncMock(),
        application_client=AsyncMock(return_value=server),
    )
    monkeypatch.setattr(
        "agent_sandbox.api.template.Sandbox.create", AsyncMock(return_value=sandbox)
    )
    p = provider(["sandbox.create", "sandbox.delete", "ports.resolve"])
    async with await launch_template(body, provider=p, journal_path=tmp_path / "run") as session:
        assert session.services["app"] is server
        assert session.servers == {}
        server.health.assert_not_awaited()
        server.discover.assert_not_awaited()
    server.aclose.assert_awaited_once()
