"""Consent, explicit credential priority and the shared engine's private-file boundary."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from agent_sandbox.models.errors import ProviderProtocolError, ProviderTrustError
from agent_sandbox.providers import commands, engine_client
from agent_sandbox.providers.alicloud_express import prepare_api_key
from agent_sandbox.providers.alicloud_express.managed_api_key import resolve_sandbox_api_key
from agent_sandbox.transport.config import TransportConfig


def config(**options):
    return TransportConfig(
        access_key_id="placeholder-ak", access_key_secret="placeholder-secret", **options
    )


async def test_explicit_key_never_contacts_engine(monkeypatch):
    call = AsyncMock()
    monkeypatch.setattr(commands, "run_command", call)
    assert (
        await resolve_sandbox_api_key(config(sandbox_api_key="placeholder-explicit"))
        == "placeholder-explicit"
    )
    call.assert_not_called()


async def test_readonly_resolution_reuses_private_key(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_client, "abx_dir", lambda: tmp_path)
    directory = tmp_path / "credentials" / "alicloud-express"
    directory.mkdir(parents=True)
    filename = directory / ("a" * 64 + ".json")
    filename.write_text(
        json.dumps(
            {
                "state": "ready",
                "api_key_id": "owned",
                "team_id": "team",
                "api_key_value": "placeholder-prepared",
            }
        )
    )
    filename.chmod(0o600)
    result = {"secret_file": str(filename), "api_key_id": "owned", "team_id": "team"}
    call = AsyncMock(return_value=result)
    monkeypatch.setattr(commands, "run_command", call)
    assert await resolve_sandbox_api_key(config()) == "placeholder-prepared"
    assert call.call_args.args == ("alicloud-express", "api-key.resolve")
    assert "confirm" not in call.call_args.kwargs


async def test_preparation_requires_explicit_consent(monkeypatch):
    call = AsyncMock(return_value={"api_key_id": "owned"})
    monkeypatch.setattr(commands, "run_command", call)
    with pytest.raises(ProviderTrustError, match="confirm=True"):
        await prepare_api_key()
    call.assert_not_called()
    assert await prepare_api_key(confirm=True, team_id="chosen") == {"api_key_id": "owned"}
    assert call.call_args.args == ("alicloud-express", "api-key.prepare", {"team_id": "chosen"})
    assert call.call_args.kwargs["confirm"] is True


@pytest.mark.parametrize(
    "result", [None, {}, {"secret_file": "/etc/passwd"}, {"secret_file": "relative.json"}]
)
async def test_invalid_file_reference_is_rejected(monkeypatch, result):
    monkeypatch.setattr(commands, "run_command", AsyncMock(return_value=result))
    with pytest.raises(ProviderProtocolError):
        await resolve_sandbox_api_key(config())


async def test_standard_explicit_e2b_key_bypasses_managed_resolution(monkeypatch):
    from agent_sandbox._standard.connection_config import ConnectionConfig
    from agent_sandbox.providers.alicloud_express import managed_api_key

    monkeypatch.setenv("E2B_API_KEY", "placeholder-existing")
    monkeypatch.setattr(
        managed_api_key, "standard_api_key", lambda: pytest.fail("must not resolve")
    )
    assert ConnectionConfig._api_key() == "placeholder-existing"
