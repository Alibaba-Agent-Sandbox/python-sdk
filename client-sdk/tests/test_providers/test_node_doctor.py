"""Doctor must not mistake a lazy EngineClient for initialized plugin code."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from agent_sandbox.providers import doctor, engine_client, installer
from tests.iso import iso  # noqa: F401
from tests.test_providers.helpers import write_plugin


@pytest.fixture
def node_plugin(iso, tmp_path):  # noqa: F811
    source = write_plugin(tmp_path / "node")
    manifest = source / "abx-provider.toml"
    manifest.write_text(
        manifest.read_text().replace(
            'kind = "exec"\ncommand = ["python3", "./provider.py"]',
            'kind = "node"\nentry = "./provider.mjs"',
        )
    )
    (source / "provider.mjs").write_text("invalid JavaScript !")
    installer.install(str(source), yes=True)


def test_missing_engine_is_not_a_successful_handshake(node_plugin, monkeypatch):
    monkeypatch.setenv("ABX_BIN", "/does-not-exist-abx")
    report = doctor.doctor("demo-prov")
    assert not report["ok"]
    assert report["checks"][-1]["name"] == "handshake"
    assert not report["checks"][-1]["ok"]
    assert "Could not start" in report["checks"][-1]["detail"]


def test_no_handshake_does_not_start_engine(node_plugin, monkeypatch):
    discover = AsyncMock(side_effect=AssertionError("must not start"))
    monkeypatch.setattr(engine_client, "discover", discover)
    assert doctor.doctor("demo-prov", handshake=False)["ok"]
    discover.assert_not_called()


@pytest.mark.parametrize(
    "status,payload,ok",
    [
        (200, {"provider": "demo-prov", "initialized": True}, True),
        (200, {"provider": "other", "initialized": True}, False),
        (404, {}, False),
        (500, {"error": {"type": "ProviderProtocolError", "message": "bad syntax"}}, False),
    ],
)
def test_initialization_response_is_awaited(node_plugin, monkeypatch, status, payload, ok):
    request = AsyncMock(return_value=httpx.Response(status, json=payload))
    close = AsyncMock()
    monkeypatch.setattr(engine_client.EngineClient, "request", request)
    monkeypatch.setattr(engine_client.EngineClient, "close", close)
    report = doctor.doctor("demo-prov")
    assert report["ok"] is ok
    assert report["checks"][-1]["name"] == "handshake"
    assert request.call_args.args == ("POST", "/v1/providers/demo-prov/initialize")
    assert request.call_args.kwargs["retry"] is False
    close.assert_awaited_once()
