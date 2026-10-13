"""One registry, one policy engine, one pipeline: the observable consequences over real HTTP."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_sandbox.server.endpoints import ENDPOINTS, endpoints_of
from agent_sandbox.server.router import CapabilityGroup, default_table

if TYPE_CHECKING:
    import pytest

    from ._live import Live


def test_there_is_no_second_dispatch_surface(live_server: Any) -> None:
    live: Live = live_server()
    for method, path in (("GET", "/ops"), ("POST", "/ops/files.read"), ("GET", "/ops/health")):
        status, _ = live.request(method, path)[:2]
        assert status == 404, path


def test_capabilities_lists_exactly_the_declared_endpoints(live_server: Any) -> None:
    live: Live = live_server()
    status, body = live.get("/capabilities")
    assert status == 200
    assert set(body["endpoints"]) == set(ENDPOINTS)
    assert {r.name for r in default_table()._routes} | {"pty_connect"} == set(ENDPOINTS)


def test_capabilities_groups_are_derived_from_endpoint_state(live_server: Any) -> None:
    live: Live = live_server(policy={"endpoints": {"files_list": {"enabled": False}}})
    status, body = live.get("/capabilities")
    assert status == 200
    summary = body["group_summary"]
    total = len(endpoints_of(CapabilityGroup.FILE_OPS))
    assert summary["file_ops"] == {"enabled": total - 1, "total": total}
    assert body["groups"]["file_ops"] is True
    assert summary["browser"]["enabled"] == 0 and body["groups"]["browser"] is False
    entry = body["endpoints"]["files_list"]
    assert entry["allowed"] is False and entry["reason"] == "endpoint_disabled"
    assert entry["rule"] == "policy:endpoints.files_list"


def test_group_selector_in_the_policy_expands_to_endpoints(live_server: Any) -> None:
    live: Live = live_server(policy={"groups": ["process"]})
    body = live.get("/capabilities")[1]
    assert body["groups"]["process"] is True
    assert body["endpoints"]["shell"]["allowed"] is True


def test_denial_names_the_rule_that_denied(live_server: Any) -> None:
    live: Live = live_server(policy={"endpoints": {"shell": {"enabled": False}}})
    status, body = live.post("/shell", {"command": "true"})
    assert status == 404
    assert body["code"] == "endpoint_disabled"
    assert body["rule"] == "policy:endpoints.shell"
    assert "policy:endpoints.shell" in body["error"]

    status, body = live.post("/code/run", {"code": "print(1)"})
    assert status == 404 and body["rule"] == "default:opt-in:dev_tools"
    assert "ABX_SERVER_ENABLED_GROUPS=dev_tools" in body["error"]


def test_env_alias_enables_a_group(live_server: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABX_SERVER_ENABLED_GROUPS", "dev_tools")
    live: Live = live_server()
    status, body = live.post("/code/run", {"code": "print(7)", "language": "python"})
    assert status == 200 and "7" in body["stdout"]
    capabilities = live.get("/capabilities")[1]
    assert capabilities["groups"]["dev_tools"] is True and capabilities["groups"]["agents"] is False


def test_the_old_disable_variable_is_gone(
    live_server: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setenv("ABX_SERVER_DISABLED_GROUPS", "file_ops")
    live: Live = live_server()
    status, _ = live.get(f"/files/stat?path={tmp_path}")
    assert status == 200


def test_core_endpoints_cannot_be_switched_off(live_server: Any) -> None:
    live: Live = live_server(policy={"endpoints": {"health": {"enabled": False}}})
    assert live.get("/health")[0] == 200
