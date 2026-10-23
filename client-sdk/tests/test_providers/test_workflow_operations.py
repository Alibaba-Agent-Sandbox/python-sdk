"""Exact operations, engine context routes and same-version code identity regressions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_sandbox.models.errors import ProviderFeatureNotSupportedError, ProviderManifestError
from agent_sandbox.providers.engine_provider import (
    EngineCodeProtocol,
    EngineProcessProtocol,
    EngineProvider,
)
from agent_sandbox.providers.feature_gate import OPERATION_SANDBOX_RULES, gate_protocol
from agent_sandbox.providers.manifest import parse_manifest
from agent_sandbox.workflows.planner import CONTRACT
from tests.test_providers.test_manifest import BASE

MOCK_INTERPRETER_OPERATIONS = frozenset(
    op for op in CONTRACT["operations"] if op.startswith("code.")
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.replace("operation_contract_version = 1", "operation_contract_version = true"),
        lambda s: s.replace("operation_contract_version = 1", ""),
        lambda s: s.replace('inputs = ["managed"]', 'inputs = ["guessed"]'),
        lambda s: s.replace('startups = ["exec", "none"]', 'startups = ["auto"]'),
        lambda s: s.replace('"exec.run",', '"code.interpret",'),
    ],
)
def test_retired_or_ambiguous_provider_contract_is_rejected(mutate: Any) -> None:
    with pytest.raises(ProviderManifestError):
        parse_manifest(mutate(BASE))


async def test_feature_metadata_cannot_grant_a_missing_operation() -> None:
    target = MagicMock(create=AsyncMock())
    wrapped = gate_protocol(target, "sample", OPERATION_SANDBOX_RULES, frozenset())
    with pytest.raises(ProviderFeatureNotSupportedError) as exc:
        await wrapped.create({})
    assert exc.value.feature == "sandbox.create"
    target.create.assert_not_awaited()


async def test_engine_context_routes_preserve_sandbox_and_context_identity() -> None:
    client = MagicMock(
        call=AsyncMock(
            side_effect=[
                {"id": "ctx/a"},
                {"stdout": "42"},
                {"contexts": [{"id": "ctx/a"}]},
                {"id": "ctx/a"},
                {},
            ]
        )
    )
    protocol = EngineCodeProtocol(client, "sample", MOCK_INTERPRETER_OPERATIONS)
    args = ("sb/a", "engine://sample/irrelevant", None)
    assert (await protocol.create_context(*args))["id"] == "ctx/a"
    await protocol.run_code(*args, code="x + 1", context_id="ctx/a")
    assert await protocol.list_contexts(*args) == [{"id": "ctx/a"}]
    await protocol.restart_context(*args, context_id="ctx/a")
    await protocol.remove_context(*args, context_id="ctx/a")
    assert [call.args[:2] for call in client.call.await_args_list] == [
        ("POST", "/v1/sandboxes/sb%2Fa/code/contexts"),
        ("POST", "/v1/sandboxes/sb%2Fa/code/run"),
        ("GET", "/v1/sandboxes/sb%2Fa/code/contexts"),
        ("POST", "/v1/sandboxes/sb%2Fa/code/contexts/ctx%2Fa/restart"),
        ("DELETE", "/v1/sandboxes/sb%2Fa/code/contexts/ctx%2Fa"),
    ]
    assert client.call.await_args_list[1].kwargs["json_body"]["context_id"] == "ctx/a"


async def test_engine_rejects_context_and_stream_before_payload() -> None:
    client = MagicMock(call=AsyncMock())
    protocol = EngineCodeProtocol(client, "sample", frozenset({"code.default-context.execute"}))
    with pytest.raises(ProviderFeatureNotSupportedError):
        await protocol.run_code(
            "id", "engine://sample/id", None, code="raise Exception()", context_id="ctx"
        )
    with pytest.raises(ProviderFeatureNotSupportedError):
        await protocol.run_code(
            "id",
            "engine://sample/id",
            None,
            code="raise Exception()",
            mode="default-context",
            on_stdout=lambda _: None,
        )
    client.call.assert_not_awaited()


def test_same_version_plugin_replacement_changes_full_content_identity(tmp_path: Path) -> None:
    manifest = parse_manifest(
        BASE.replace('kind = "exec"', 'kind = "node"').replace(
            'command = ["python3", "./p.py"]', 'entry = "provider.mjs"'
        )
    )
    (tmp_path / "provider.mjs").write_text("export default () => ({})")
    provider = EngineProvider(manifest, tmp_path)
    before = provider.content_digest()
    (tmp_path / "provider.mjs").write_text("export default () => ({changed: true})")
    assert provider.version == manifest.version
    assert provider.content_digest() != before
    second = provider.content_digest()
    (tmp_path / ".env").write_text("IGNORED_CREDENTIAL=placeholder")
    assert provider.content_digest() == second


async def test_engine_can_consume_native_stateless_without_public_context_grants() -> None:
    client = MagicMock(call=AsyncMock(return_value={"stdout": "42"}))
    protocol = EngineCodeProtocol(client, "sample", frozenset({"code.execute"}))
    assert await protocol.run_code("id", "engine://sample/id", None, code="print(42)") == {
        "stdout": "42"
    }
    client.call.assert_awaited_once()
    assert client.call.await_args.kwargs["json_body"]["mode"] == "stateless"


def test_exact_operation_changes_require_new_install_consent() -> None:
    from agent_sandbox.providers.installer import _diff_aspects

    original = parse_manifest(BASE)
    changed = parse_manifest(BASE.replace('"exec.run",', '"exec.stream",'))
    changes = _diff_aspects({"consented": original.to_summary()}, changed)
    assert changes == ["operations"]
    assert changed.features == original.features


async def test_engine_endpoint_descriptor_is_not_flattened_to_url_headers(tmp_path: Path) -> None:
    from agent_sandbox.protocol.port_contract import PortContext

    manifest = parse_manifest(
        BASE.replace('kind = "exec"', 'kind = "node"').replace(
            'command = ["python3", "./p.py"]', 'entry = "provider.mjs"'
        )
    )
    provider = EngineProvider(manifest, tmp_path)
    endpoint = {
        "provider_id": manifest.id,
        "sandbox_id": "owned",
        "port": 9000,
        "url": "https://gateway.invalid/proxy?sig=fixture",
        "headers": {},
        "authentication_audience": "gateway",
        "path_mode": "operation-signed",
        "expires_at": "2030-01-01T00:00:00Z",
    }
    protocol = MagicMock(application_endpoint=AsyncMock(return_value=endpoint))
    assert (
        await provider.application_endpoint(PortContext("owned", "", True, None), 9000, protocol)
        == endpoint
    )


def test_rest_cannot_declare_interpreter_from_an_unverified_wire_guess() -> None:
    text = (
        BASE.replace('kind = "exec"', 'kind = "rest"')
        .replace('command = ["python3", "./p.py"]', '[endpoint]\nbase_url = "https://api.invalid"')
        .replace('"exec.run",', '"code.execute",')
    )
    with pytest.raises(ProviderManifestError, match="no verified interpreter"):
        parse_manifest(text)


@pytest.mark.parametrize("process_id", [123, "execd-command-opaque"])
async def test_engine_process_start_preserves_real_ack_identity(process_id: int | str) -> None:
    async def frames(*args: Any, **kwargs: Any):
        yield {"type": "stdout", "data": "", "pid": process_id, "timestamp": 123.5}
        yield {"type": "stdout", "data": "ready"}
        yield {"type": "exit", "exit_code": 0}

    client = MagicMock(stream=frames)
    # A startup acknowledgment is internal transport metadata, not a public stream grant.
    protocol = EngineProcessProtocol(client, "sample", frozenset({"exec.run"}))
    stream = await protocol.start("engine://sample/owned", None, cmd="server")
    chunks = [chunk async for chunk in stream]
    assert chunks[0].pid == process_id
    assert type(chunks[0].pid) is type(process_id)
    assert chunks[0].timestamp == 123.5
    assert chunks[0].data == ""
    assert chunks[1].data == "ready" and chunks[1].pid is None
    assert chunks[2].exit_code == 0
