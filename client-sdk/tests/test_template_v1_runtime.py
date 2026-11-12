"""v1 consumers forward real wire fields and keep Worker environment out of state."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jsonschema import Draft202012Validator

from agent_sandbox.api.template import TemplateLaunchError, launch_template
from agent_sandbox.managed_agents import ManagedConfig, ManagedService, ManagedStore
from agent_sandbox.models.managed_instance import worker_environment
from agent_sandbox.providers.alicloud_express.managed import ExpressBackend
from agent_sandbox.providers.alicloud_express.provider import AlicloudExpressProvider
from agent_sandbox.template_contract.normalize import normalize_template_v1, schema_for_stage
from agent_sandbox.transport.config import TransportConfig

_CONTRACT_ROOT = Path(__file__).parents[1] / "src/agent_sandbox/template_contract"
_FIXTURES = json.loads((_CONTRACT_ROOT / "fixtures.json").read_text())


@pytest.mark.parametrize(
    "case", _FIXTURES["validTemplates"] + _FIXTURES["invalidTemplates"], ids=lambda case: case["id"]
)
def test_owner_admission_vectors_run_with_the_installed_sdk(case):
    schema = json.loads((_CONTRACT_ROOT / "template-v1.schema.json").read_text())
    validator = Draft202012Validator(schema_for_stage(schema, case["stage"])).validate
    kwargs = {"stage": case["stage"], "provider": case.get("provider")}
    if case.get("descriptor"):
        # The owner fixture's actual plugin descriptor; validates JSON Schema,
        # rather than claiming backend support from a no-op callback.
        def descriptor(stage, value, provider):
            assert provider == "third-party" and stage == "sandbox.create"
            Draft202012Validator(
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "timeout": {"type": "integer", "minimum": 1},
                        "envs": {"type": "object"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["timeout"],
                }
            ).validate(value)

        kwargs["validate_provider"] = descriptor
    if case in _FIXTURES["invalidTemplates"]:
        with pytest.raises(ValueError):
            normalize_template_v1(case["manifest"], validator, **kwargs)
    else:
        normalize_template_v1(case["manifest"], validator, **kwargs)


def literal_manifest(instance=None):
    return {
        "specVersion": 1,
        "name": "literal",
        "sandbox": {
            "provider": "alicloud-express",
            "template": {"reference": "prepared"},
            **({"instance": instance} if instance is not None else {}),
        },
    }


async def infrastructure():
    return await AlicloudExpressProvider().build_infra(
        TransportConfig(
            provider="alicloud-express",
            sandbox_api_key="placeholder-platform-key",
            sandbox_base_url="https://sandbox-test.example.com",
            sandbox_domain="sandbox-test.example.com",
            region="cn-hangzhou",
            http2=False,
        )
    )


def cloud_response(timeout=300):
    return {
        "sandboxID": "owned",
        "templateID": "prepared",
        "timeout": timeout,
        "envdAccessToken": "placeholder-envd-token",
        "envdVersion": "0.3.0",
        "trafficAccessToken": "placeholder-traffic-token",
    }


@pytest.mark.parametrize("override", [False, True])
async def test_prepared_literal_forwards_instance_through_actual_http_serializer(
    tmp_path,
    monkeypatch,
    httpx_mock,
    override,
):
    infra = await infrastructure()
    monkeypatch.setattr("agent_sandbox.api.sandbox._provider_infra", AsyncMock(return_value=infra))
    httpx_mock.add_response(
        method="POST", url="https://sandbox-test.example.com/sandboxes", json=cloud_response()
    )
    httpx_mock.add_response(
        method="DELETE", url="https://sandbox-test.example.com/sandboxes/owned", status_code=204
    )
    instance = {
        "timeout": 720,
        "cpu": 2,
        "memory": 2048,
        "disk": 4096,
        "gpu": "A10",
        "volume_mounts": {"/data": "borrowed-data"},
        "envs": {"CUSTOM_VALUE": "placeholder-private-value"},
        "metadata": {"purpose": "literal"},
    }
    original = copy.deepcopy(instance)
    options = (
        {
            "timeout": 900,
            "cpu": 4,
            "memory": 4096,
            "disk": 8192,
            "gpu": "A100",
            "volume_mounts": {"/other": "borrowed-other"},
            "envs": {"CUSTOM_VALUE": "placeholder-override-value"},
            "metadata": {"purpose": "override"},
        }
        if override
        else {}
    )
    journal = tmp_path / "run.jsonl"
    async with await launch_template(
        literal_manifest(instance), provider="alicloud-express", journal_path=journal, **options
    ) as session:
        assert "placeholder-private-value" not in json.dumps(session.plan)
        assert "placeholder-override-value" not in json.dumps(session.plan)
        request = httpx_mock.get_requests(method="POST")[0]
        body = json.loads(request.content)
        for wire, native in {
            "timeout": "timeout",
            "cpuCount": "cpu",
            "memoryMB": "memory",
            "diskSizeMB": "disk",
            "gpu": "gpu",
        }.items():
            assert body[wire] == options.get(native, instance[native])
        assert body["volumeMounts"] == (
            [{"path": "/other", "name": "borrowed-other"}]
            if override
            else [{"path": "/data", "name": "borrowed-data"}]
        )
        assert body["envVars"] == options.get("envs", instance["envs"])
        assert body["metadata"]["purpose"] == ("override" if override else "literal")
        assert body["metadata"]["abx_template_run"]
    assert instance == original
    assert "placeholder-private-value" not in journal.read_text()
    assert "placeholder-override-value" not in journal.read_text()
    assert [r.method for r in httpx_mock.get_requests()] == ["POST", "DELETE"]


async def test_prepared_literal_default_timeout_is_300(tmp_path, monkeypatch):
    sandbox = SimpleNamespace(id="owned", provider="alicloud-express", kill=AsyncMock())
    create = AsyncMock(return_value=sandbox)
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    async with await launch_template(
        literal_manifest(), provider="alicloud-express", journal_path=tmp_path / "run"
    ):
        assert create.call_args.kwargs["timeout"] == 300
        assert "cpu" not in create.call_args.kwargs
        assert "memory" not in create.call_args.kwargs


async def test_explicit_api_override_replaces_an_expression_without_evaluating_it(
    tmp_path, monkeypatch
):
    sandbox = SimpleNamespace(id="owned", provider="alicloud-express", kill=AsyncMock())
    create = AsyncMock(return_value=sandbox)
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    manifest = literal_manifest(
        {"timeout": "${env(TTL)}", "envs": {"VALUE": "${env(PRIVATE_VALUE)}"}}
    )
    async with await launch_template(
        manifest,
        provider="alicloud-express",
        timeout=750,
        envs={"VALUE": "placeholder-explicit-value"},
        journal_path=tmp_path / "run",
    ):
        assert create.call_args.kwargs["timeout"] == 750
        assert create.call_args.kwargs["envs"] == {"VALUE": "placeholder-explicit-value"}


async def test_invalid_explicit_override_fails_before_journaling(tmp_path, monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    with pytest.raises(ValueError, match="schema validation failed"):
        await launch_template(
            literal_manifest(), provider="alicloud-express", cpu=0, journal_path=tmp_path / "run"
        )
    create.assert_not_awaited()
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("timeout", "${env(TTL)}"),
        ("envs", {"VALUE": "${env(PRIVATE_VALUE)}"}),
        ("volume_mounts", {"/data": "${env(VOLUME)}"}),
    ],
)
async def test_unresolved_native_expressions_fail_before_create_or_journal(
    tmp_path, monkeypatch, field, value
):
    create = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    with pytest.raises(ValueError, match="native expressions require the Devs parser"):
        await launch_template(
            literal_manifest({field: value}),
            provider="alicloud-express",
            journal_path=tmp_path / "run",
        )
    create.assert_not_awaited()
    assert not (tmp_path / "run").exists()


async def test_unsupported_lifecycle_does_not_disappear(tmp_path, monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    with pytest.raises(TemplateLaunchError, match="instance-lifecycle-unimplemented"):
        await launch_template(
            literal_manifest({"lifecycle": {"onTimeout": "pause", "autoResume": True}}),
            provider="alicloud-express",
            journal_path=tmp_path / "run",
        )
    create.assert_not_awaited()


async def test_mixed_generic_intent_is_valid_but_sdk_rejects_before_creation(tmp_path, monkeypatch):
    from agent_sandbox.template_contract import normalize_document

    manifest = literal_manifest()
    manifest["deployment"] = {
        "edition": "3.0.0",
        "resources": {"web": {"component": "fc3@0.1.26", "props": {"region": "cn-hangzhou"}}},
    }
    normalized = normalize_document(manifest)
    assert normalized["sandbox"]["template"]["reference"] == "prepared"
    assert normalized["deployment"]["resources"]["web"]["component"] == "fc3@0.1.26"
    create = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    with pytest.raises(TemplateLaunchError, match="deployment-orchestrator-required"):
        await launch_template(manifest, provider="alicloud-express", journal_path=tmp_path / "run")
    create.assert_not_awaited()
    assert not (tmp_path / "run").exists()


def runtime_config(**overrides):
    return ManagedConfig.from_dict(
        {
            "revision": "revision-a",
            "template": "prepared",
            "models": {"fixture-model": "qwen-code"},
            "modelEnvAllowlist": ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"],
            **overrides,
        }
    )


@pytest.mark.parametrize("database", ["sqlite", "postgres"])
def test_managed_session_keeps_instance_snapshot_and_excludes_environment_values(
    tmp_path, database
):
    postgres = None
    if database == "postgres":
        pgserver = pytest.importorskip("pgserver")
        postgres = pgserver.get_server(tmp_path / "postgres", cleanup_mode="delete")
        url = postgres.get_uri()
    else:
        url = "sqlite:///" + str(tmp_path / "state.db")
    config = runtime_config(
        instance={
            "timeout": 1800,
            "cpu": 2,
            "memory": 2048,
            "volume_mounts": {"/data": "borrowed-data"},
            "metadata": {"purpose": "dataset"},
        },
        instanceEnvNames=["CUSTOM_VALUE"],
    )
    try:
        service = ManagedService(ManagedStore(url, local=True), config)
        status, session, _ = service.handle(
            "owner", "POST", "/v1/agents/sessions", {"agent": {"model": "fixture-model"}}
        )
        assert status == 201
        with service.store.transaction() as tx:
            saved = tx.get(session["id"], "owner")
        assert saved["_settings"]["instance"] == config.instance
        assert saved["_settings"]["instanceEnvNames"] == ["CUSTOM_VALUE"]
        assert saved["_settings"]["sessions"]["maxLifetimeSeconds"] == 1800
        assert "envs" not in saved["_settings"]["instance"]
        # Updating a later revision's settings cannot rewrite an existing Session.
        config.instance["cpu"] = 4
        with service.store.transaction() as tx:
            assert tx.get(session["id"], "owner")["_settings"]["instance"]["cpu"] == 2
        private = worker_environment(
            {"CUSTOM_VALUE": "placeholder-private-value"}, ["CUSTOM_VALUE"]
        )
        assert private["CUSTOM_VALUE"] not in json.dumps(saved)
        assert private["CUSTOM_VALUE"] not in json.dumps(session)
    finally:
        if postgres:
            postgres.cleanup()


def test_managed_default_and_single_lifetime_source():
    assert runtime_config().instance["timeout"] == 3600
    config = runtime_config(instance={"timeout": 1500})
    assert config.sessions["maxLifetimeSeconds"] == config.instance["timeout"] == 1500
    config = runtime_config(
        instance={"timeout": 120},
        sessions={"idleTimeoutSeconds": 60},
        limits={"maxRunSeconds": 90, "maxToolSeconds": 30},
    )
    assert config.sessions["maxLifetimeSeconds"] == 120
    with pytest.raises(ValueError, match="must equal"):
        runtime_config(instance={"timeout": 1500}, sessions={"maxLifetimeSeconds": 3600})


@pytest.mark.parametrize(
    "instance",
    [
        {"envs": {"CUSTOM_VALUE": "placeholder-private-value"}},
        {"secure": False},
        {"lifecycle": {"onTimeout": "pause", "autoResume": True}},
        {"metadata": {"abx-session": "foreign"}},
        *[
            {"volume_mounts": {path: "borrowed-data"}}
            for path in ["/workspace", "/workspace/data", "/home", "/home/user"]
        ],
    ],
)
def test_managed_rejects_conflicting_or_unhandled_instance_input(instance):
    with pytest.raises(ValueError):
        runtime_config(instance=instance)


@pytest.mark.parametrize(
    "name",
    [
        "ABX_SERVER_TOKEN",
        "ABX_MANAGED_STATE_DIR",
        "OPENAI_API_KEY",
        "PATH",
        "PYTHONPATH",
        "QWEN_AUTH_TOKEN",
    ],
)
def test_managed_custom_env_cannot_override_runtime_or_models(name):
    with pytest.raises(ValueError, match="runtime/model controls"):
        runtime_config(instanceEnvNames=[name])


async def test_managed_backend_serializes_instance_and_injects_worker_private_env(
    monkeypatch, httpx_mock
):
    provider = {
        "provider": "alicloud-express",
        "apiKey": "placeholder-platform-key",
        "baseUrl": "https://sandbox-test.example.com",
        "domain": "sandbox-test.example.com",
        "region": "cn-hangzhou",
    }
    model = {
        "apiKey": "placeholder-model-key",
        "baseUrl": "https://model-test.example.com",
        "model": "fixture-model",
        "adapter": "qwen-code",
    }
    backend = ExpressBackend(
        provider, model, instance_env={"CUSTOM_VALUE": "placeholder-private-value"}
    )
    infra = await infrastructure()

    class Reader:
        cancel = AsyncMock()

        def __aiter__(self):
            return self.events()

        async def events(self):
            yield SimpleNamespace(pid=123, exit_code=None)

    start = AsyncMock(return_value=Reader())
    infra.process_protocol = SimpleNamespace(start=start)
    monkeypatch.setattr(backend, "_infra", AsyncMock(return_value=infra))
    httpx_mock.add_response(
        method="POST", url="https://sandbox-test.example.com/sandboxes", json=cloud_response(1800)
    )
    config = runtime_config(
        instance={
            "timeout": 1800,
            "cpu": 4,
            "memory": 4096,
            "disk": 8192,
            "gpu": "A10",
            "volume_mounts": {"/data": "borrowed-data"},
            "metadata": {"purpose": "dataset"},
        },
        instanceEnvNames=["CUSTOM_VALUE"],
    )
    settings = {
        "template": config.template,
        "workspace": config.workspace,
        "port": config.port,
        "sessions": config.sessions,
        "modelEnvAllowlist": config.model_env_allowlist,
        "instance": config.instance,
        "instanceEnvNames": config.instance_env_names,
    }
    session = {
        "id": "session-a",
        "_revision": "revision-a",
        "_settings": settings,
        "agent": {"model": "fixture-model", "x_agent_sandbox": {"adapter": "qwen-code"}},
    }
    receipts = []
    await backend.create(session, "placeholder-app-token", receipts.append)
    body = json.loads(httpx_mock.get_request().content)
    assert {
        key: body[key] for key in ["timeout", "cpuCount", "memoryMB", "diskSizeMB", "gpu", "secure"]
    } == {
        "timeout": 1800,
        "cpuCount": 4,
        "memoryMB": 4096,
        "diskSizeMB": 8192,
        "gpu": "A10",
        "secure": True,
    }
    assert body["autoPause"] is False
    assert body["volumeMounts"] == [{"name": "borrowed-data", "path": "/data"}]
    assert body["metadata"] == {
        "purpose": "dataset",
        "abx-managed": "true",
        "abx-session": "session-a",
        "abx-revision": "revision-a",
    }
    assert body["envVars"] == {
        "CUSTOM_VALUE": "placeholder-private-value",
        "ABX_SERVER_TOKEN": "placeholder-app-token",
        "ABX_MANAGED_WORKSPACE": "/workspace",
        "OPENAI_API_KEY": "placeholder-model-key",
        "OPENAI_BASE_URL": model["baseUrl"],
        "OPENAI_MODEL": "fixture-model",
    }
    assert start.call_args.kwargs["env"]["CUSTOM_VALUE"] == "placeholder-private-value"
    assert "placeholder-private-value" not in json.dumps(settings)
    assert "placeholder-private-value" not in json.dumps(receipts)
    assert "placeholder-model-key" not in json.dumps(receipts)
    assert [r.url.path for r in httpx_mock.get_requests()] == ["/sandboxes"]
    # Cleanup only recorded owned compute; no Volume deletion API is called.
    cleanup_infra = await infrastructure()
    monkeypatch.setattr(backend, "_infra", AsyncMock(return_value=cleanup_infra))
    httpx_mock.add_response(
        method="DELETE", url="https://sandbox-test.example.com/sandboxes/owned", status_code=204
    )
    httpx_mock.add_response(
        method="GET", url="https://sandbox-test.example.com/sandboxes/owned", status_code=404
    )
    assert await backend.kill(receipts[-1])
    assert all("volume" not in r.url.path.lower() for r in httpx_mock.get_requests())


def test_canonical_sources_are_locked_to_immutable_owner_bytes():
    root = Path(__file__).parents[1] / "src/agent_sandbox/template_contract"
    lock = json.loads((root / "source.json").read_text())
    assert len(lock["revision"]) == 40
    for entry in lock["files"].values():
        assert hashlib.sha256((root / entry["target"]).read_bytes()).hexdigest() == entry["sha256"]


@pytest.mark.parametrize("source", [False, True])
async def test_selected_plugin_uses_real_sync_schema_without_requiring_plugin_release(
    tmp_path,
    monkeypatch,
    source,
):
    seen = []

    def validate(stage, value):
        seen.append((stage, copy.deepcopy(value)))
        if stage == "template.prepare":
            schema = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"dockerfile": {"type": "string"}, "context": {"const": "."}},
                        "required": ["dockerfile", "context"],
                    },
                    "props": {"type": "object", "additionalProperties": False},
                },
                "required": ["source"],
            }
        else:
            assert stage == "sandbox.create"
            schema = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 1000},
                    "envs": {"type": "object"},
                    "metadata": {"type": "object"},
                },
                "required": ["timeout"],
            }
        Draft202012Validator(schema).validate(value)

    plugin = SimpleNamespace(
        id="strict-plugin",
        validate_template_input=validate,
        content_digest=lambda: "sha256:" + "d" * 64,
        describe=lambda: {
            "id": "strict-plugin",
            "operation_contract_version": 1,
            "operations": {"python": ["sandbox.create", "sandbox.delete"]},
            "workflow_inputs": ["source", "managed"],
            "startup_modes": ["entrypoint", "none"],
        },
    )
    sandbox = SimpleNamespace(id="owned", provider="strict-plugin", kill=AsyncMock())
    create = AsyncMock(return_value=sandbox)
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    manifest = literal_manifest({"timeout": 777})
    manifest["sandbox"]["provider"] = plugin.id
    if source:
        manifest["sandbox"]["template"] = {"source": {"dockerfile": "Dockerfile"}}
    async with await launch_template(
        manifest, provider=plugin, reference="prepared", journal_path=tmp_path / "run"
    ):
        assert create.call_args.kwargs["provider"] is plugin
        assert create.call_args.kwargs["timeout"] == 777
    assert [stage for stage, _ in seen] == (
        ["template.prepare", "sandbox.create"] if source else ["sandbox.create"]
    )
    manifest["sandbox"]["instance"]["timeout"] = 1001
    create.reset_mock()
    with pytest.raises(ValueError, match="selected Provider validation failed"):
        await launch_template(
            manifest, provider=plugin, reference="prepared", journal_path=tmp_path / "rejected"
        )
    create.assert_not_awaited()
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("mode", ["missing", "async"])
async def test_plugin_without_real_sync_validator_rejects_before_side_effects(
    tmp_path, monkeypatch, mode
):
    from agent_sandbox.providers.base import Provider

    plugin = SimpleNamespace(
        id="strict-plugin",
        content_digest=lambda: "sha256:" + "d" * 64,
        describe=lambda: {
            "id": "strict-plugin",
            "operation_contract_version": 1,
            "operations": {"python": ["sandbox.create", "sandbox.delete"]},
            "workflow_inputs": ["managed"],
            "startup_modes": ["none"],
        },
    )
    if mode == "async":

        async def validate(stage, value):
            raise AssertionError("An async validator must never execute")

        plugin.validate_template_input = validate
    else:
        # An inherited default is explicitly not counted as a real validator.
        plugin.validate_template_input = Provider.validate_template_input.__get__(plugin)
    manifest = literal_manifest()
    manifest["sandbox"]["provider"] = plugin.id
    create = AsyncMock()
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    with pytest.raises(ValueError, match="real preparation/create validators|validation failed"):
        await launch_template(manifest, provider=plugin, journal_path=tmp_path / "run")
    create.assert_not_awaited()
    assert not (tmp_path / "run").exists()
