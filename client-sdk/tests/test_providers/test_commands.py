"""Provider command manifest, consent and one-shot engine contract regressions."""

from __future__ import annotations

# ruff: noqa: F811
import copy
from typing import Any

import httpx
import pytest

from agent_sandbox.models.errors import (
    ProviderConfigError,
    ProviderManifestError,
    ProviderProtocolError,
    ProviderTrustError,
)
from agent_sandbox.providers import commands, installer, manifest
from agent_sandbox.providers.engine_client import EngineClient, EngineRecord
from tests.iso import iso  # noqa: F401
from tests.test_providers.helpers import write_plugin
from tests.test_providers.test_manifest import BASE

ENTRY = """
[commands]
protocol = "provider-commands/1"
[[commands.entries]]
id = "volumes.list"
description = "List volumes"
description_zh = "列出存储卷"
input_schema={type="object",additionalProperties=false,properties={limit={type="integer",minimum=1}}}
output_schema = {type="object"}
effect = "read"
idempotent = true
"""


def test_command_manifest_round_trip_and_copy() -> None:
    command = manifest.parse_manifest(BASE + ENTRY).commands[0]
    assert command.id == "volumes.list"
    assert command.effect == "read" and command.idempotent
    wire = command.to_dict()
    wire["input_schema"]["properties"].clear()
    assert "limit" in command.input_schema["properties"]


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('protocol = "provider-commands/1"', 'protocol = "provider-commands/2"'),
        ('id = "volumes.list"', 'id = "../volumes"'),
        ('id = "volumes.list"', 'id = "Volumes.list"'),
        ('id = "volumes.list"', 'id = "' + "a" * 81 + '"'),
        ('effect = "read"', 'effect = "shell"'),
        ("idempotent = true", 'idempotent = "true"'),
        ("additionalProperties=false", "additionalProperties=true"),
        ('type="object",additionalProperties=false', 'type="array",additionalProperties=false'),
        ('output_schema = {type="object"}', "output_schema = true"),
        ('description = "List volumes"', 'description = ""'),
        ('description_zh = "列出存储卷"', 'description_zh = ""'),
        ('description = "List volumes"', 'description = "   "'),
        ('effect = "read"', 'extra = true\neffect = "read"'),
        ("minimum=1", "minimum=nan"),
        ("minimum=1", "default=2026-10-16"),
    ],
)
def test_rejects_invalid_command_descriptors(old: str, new: str) -> None:
    with pytest.raises(ProviderManifestError):
        manifest.parse_manifest(BASE + ENTRY.replace(old, new))


@pytest.mark.parametrize(
    "keyword",
    [
        "$ref",
        "$dynamicRef",
        "$recursiveRef",
        "$id",
        "$async",
        "pattern",
        "patternProperties",
        "format",
        "__proto__",
        "prototype",
        "constructor",
    ],
)
def test_rejects_schema_references_and_async(keyword: str) -> None:
    with pytest.raises(ProviderManifestError):
        manifest.parse_manifest(
            BASE + ENTRY.replace("minimum=1", f'"{keyword}"="https://example.com/schema"')
        )


@pytest.mark.parametrize("name", ["format", "pattern", "patternProperties", "$ref", "$id"])
def test_schema_business_property_names_are_data(name: str) -> None:
    source = ENTRY.replace('limit={type="integer",minimum=1}', f'"{name}"={{type="string"}}')
    assert name in manifest.parse_manifest(BASE + source).commands[0].input_schema["properties"]


def test_explicit_section_requires_entries() -> None:
    with pytest.raises(ProviderManifestError):
        manifest.parse_manifest(BASE + '\n[commands]\nprotocol="provider-commands/1"\n')


def test_duplicate_and_limits() -> None:
    with pytest.raises(ProviderManifestError, match="duplicate"):
        manifest.parse_manifest(BASE + ENTRY + ENTRY[ENTRY.index("[[commands.entries]]") :])
    with pytest.raises(ProviderManifestError, match="64 KiB"):
        manifest.parse_manifest(BASE + ENTRY.replace("List volumes", "x" * (64 * 1024)))
    with pytest.raises(ProviderManifestError, match="depth 16"):
        nested = "{child=" * 18 + '"value"' + "}" * 18
        manifest.parse_manifest(BASE + ENTRY.replace("minimum=1", f"default={nested}"))
    with pytest.raises(ProviderManifestError, match="128"):
        entries = "\n".join(
            ENTRY[ENTRY.index("[[commands.entries]]") :].replace("volumes.list", f"op{i}")
            for i in range(129)
        )
        manifest.parse_manifest(BASE + '\n[commands]\nprotocol="provider-commands/1"\n' + entries)


def test_rest_rejects_commands_but_accepts_empty_section() -> None:
    rest = (
        BASE.replace('kind = "exec"', 'kind = "rest"')
        + '\n[endpoint]\nbase_url="https://example.com"\n'
    )
    with pytest.raises(ProviderManifestError, match="only node and exec"):
        manifest.parse_manifest(rest + ENTRY)
    assert (
        manifest.parse_manifest(
            rest + '\n[commands]\nprotocol="provider-commands/1"\nentries=[]\n'
        ).commands
        == ()
    )


def test_consent_captures_commands_and_old_receipt_defaults_to_empty() -> None:
    original = manifest.parse_manifest(BASE)
    receipt = {"consented": original.to_summary()}
    receipt["consented"].pop("commands")
    assert installer._diff_aspects(receipt, original) == []
    next_manifest = manifest.parse_manifest(BASE + ENTRY)
    assert installer._diff_aspects(receipt, next_manifest) == ["commands"]
    receipt = {"consented": next_manifest.to_summary()}
    assert installer._diff_aspects(receipt, next_manifest) == []
    changed = manifest.parse_manifest(BASE + ENTRY.replace('effect = "read"', 'effect = "delete"'))
    assert installer._diff_aspects(receipt, changed) == ["commands"]
    assert "commands" in installer.RISK_ASPECTS


def test_installation_requires_consent_when_commands_change(iso: Any, tmp_path: Any) -> None:
    source = write_plugin(tmp_path / "source")
    installer.install(str(source), yes=True)
    write_plugin(source, version="0.2.0", extra=ENTRY)
    plans = []
    with pytest.raises(ProviderTrustError):
        installer.install(
            str(source), force=True, confirm=lambda plan: plans.append(plan.summary()) or False
        )
    assert plans[0]["changes"] == ["commands"]
    assert plans[0]["commands"][0]["id"] == "volumes.list"


class FakeClient:
    instances: list[FakeClient] = []
    response: Any = {}
    failure: Exception | None = None

    def __init__(self, connection: dict[str, Any]) -> None:
        self.connection = connection
        self.calls: list[Any] = []
        self.closed = False
        self.instances.append(self)

    async def call(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.failure:
            raise self.failure
        return copy.deepcopy(self.response)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> type[FakeClient]:
    FakeClient.instances = []
    FakeClient.failure = None
    FakeClient.response = {}
    monkeypatch.setattr(commands, "EngineClient", FakeClient)
    return FakeClient


@pytest.mark.asyncio
async def test_list_get_run_contract(iso: Any, client: type[FakeClient]) -> None:
    descriptor = manifest.parse_manifest(BASE + ENTRY).commands[0].to_dict()
    client.response = {"commands": [descriptor]}
    assert await commands.list_commands("alicloud-express") == [descriptor]
    assert client.instances[-1].calls == [(("GET", "/v1/providers/alicloud-express/commands"), {})]
    client.response = descriptor
    assert await commands.get_command("alicloud-express", "volumes.list") == descriptor
    client.response = {"items": []}
    assert await commands.run_command("alicloud-express", "volumes.list", {"limit": 2}) == {
        "items": []
    }
    args, options = client.instances[-1].calls[0]
    assert args == ("POST", "/v1/providers/alicloud-express/commands/volumes.list")
    assert options == {"json_body": {"input": {"limit": 2}, "confirm": False}, "retry": False}
    await commands.run_command(
        "alicloud-express", "volumes.delete", {"id": "owned"}, confirm=True, region="cn-shanghai"
    )
    assert client.instances[-1].calls[0][1]["json_body"]["confirm"] is True
    assert client.instances[-1].connection["region"] == "cn-shanghai"
    assert all(c.closed for c in client.instances)
    assert all(c.connection["provider"] == "alicloud-express" for c in client.instances)


@pytest.mark.asyncio
async def test_discovery_does_not_resolve_credentials(
    iso: Any, client: type[FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_config(**kwargs: Any) -> None:
        raise AssertionError("metadata discovery must not resolve credentials")

    monkeypatch.setattr(commands, "load_config", unexpected_config)
    monkeypatch.setattr(commands, "get_provider", lambda provider: unexpected_config())
    descriptor = manifest.parse_manifest(BASE + ENTRY).commands[0].to_dict()
    client.response = {"commands": [descriptor]}
    assert await commands.list_commands("demo-prov") == [descriptor]
    client.response = descriptor
    assert await commands.get_command("demo-prov", "volumes.list") == descriptor
    assert all(c.connection == {"provider": "demo-prov"} for c in client.instances)


@pytest.mark.asyncio
async def test_invocation_forwards_only_scoped_credentials(
    iso: Any, tmp_path: Any, client: type[FakeClient]
) -> None:
    source = write_plugin(tmp_path / "node", extra=ENTRY + "\n[config.fields.token]\nsecret=true\n")
    path = source / "abx-provider.toml"
    path.write_text(
        path.read_text().replace('kind = "exec"', 'kind = "node"\nentry = "provider.mjs"')
    )
    (source / "provider.mjs").write_text('throw new Error("must not load in SDK");')
    installer.install(str(source), yes=True)
    client.response = {"items": []}
    await commands.run_command(
        "demo-prov",
        "volumes.list",
        provider_options={"token": "placeholder-token"},
        sandbox_api_key="unrelated-placeholder",
    )
    assert client.instances[-1].connection == {
        "provider": "demo-prov",
        "provider_options": {"token": "placeholder-token"},
    }


@pytest.mark.asyncio
async def test_releases_client_on_protocol_and_engine_errors(
    iso: Any,
    client: type[FakeClient],
) -> None:
    with pytest.raises(ProviderProtocolError):
        await commands.list_commands("alicloud-express")
    with pytest.raises(ProviderProtocolError):
        await commands.get_command("alicloud-express", "volumes.list")
    client.failure = ProviderConfigError("invalid input")
    with pytest.raises(ProviderConfigError):
        await commands.run_command("alicloud-express", "volumes.list")
    assert all(c.closed for c in client.instances)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,command_id,input,confirm",
    [
        ("../demo", "volumes.list", {}, False),
        ("alicloud-express", "../list", {}, False),
        ("alicloud-express", "volumes.list", [], False),
        ("alicloud-express", "volumes.list", {}, "yes"),
    ],
)
async def test_invalid_calls_never_reach_engine(
    iso: Any,
    client: type[FakeClient],
    provider: str,
    command_id: str,
    input: Any,
    confirm: Any,
) -> None:
    with pytest.raises(ProviderConfigError):
        await commands.run_command(provider, command_id, input, confirm=confirm)
    assert client.instances == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_post_not_replayed_after_unauthorized_or_disconnect(failure: bool) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if failure:
            raise httpx.ConnectError("disconnected", request=request)
        return httpx.Response(
            401, json={"error": {"type": "AuthenticationError", "message": "denied"}}
        )

    engine = EngineClient({"provider": "demo-prov"})
    await engine._http.aclose()
    engine._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    engine._record = EngineRecord(1, "127.0.0.1", 12345, "placeholder")
    try:
        if failure:
            with pytest.raises(ProviderProtocolError):
                await engine.call(
                    "POST", "/v1/providers/demo-prov/commands/volumes.create", retry=False
                )
        else:
            response = await engine.request(
                "POST", "/v1/providers/demo-prov/commands/volumes.create", retry=False
            )
            assert response.status_code == 401
        assert calls == 1
    finally:
        await engine.close()
