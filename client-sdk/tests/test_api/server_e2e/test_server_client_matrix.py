"""Alignment guard: every built-in server route has a client method (and a sync twin)."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

pytest.importorskip("easy_sandbox.server", reason="needs the easy-sandbox-server distribution")

from easy_sandbox.server.router import CapabilityGroup, default_table  # noqa: E402

from easy_sandbox.api.server_client import ServerClient  # noqa: E402

#: Routes deliberately without a ``ServerClient`` method (see client-server-alignment.md N/A-7).
_DELIBERATELY_ONE_SIDED_GROUPS = {CapabilityGroup.AGENTS}


def _routes() -> dict[str, Any]:
    table = default_table()
    return {r.name: r for r in table._routes}


def _resolve(client: ServerClient, dotted: str) -> Any:
    target: Any = client
    for part in dotted.split("."):
        target = getattr(target, part)
    return target


def test_every_builtin_route_has_a_client_method() -> None:
    missing = [
        name
        for name, route in _routes().items()
        if route.group not in _DELIBERATELY_ONE_SIDED_GROUPS
        and name not in ServerClient.ENDPOINT_METHODS
    ]
    assert missing == [], f"server routes without a ServerClient method: {missing}"


def test_pty_websocket_endpoint_is_mapped() -> None:
    assert "pty_connect" in ServerClient.ENDPOINT_METHODS


def test_every_mapped_method_exists_and_has_a_sync_twin() -> None:
    client = ServerClient("http://127.0.0.1:1")
    problems: list[str] = []
    for endpoint, methods in ServerClient.ENDPOINT_METHODS.items():
        assert methods, endpoint
        for dotted in methods:
            try:
                target = _resolve(client, dotted)
            except AttributeError:
                problems.append(f"{endpoint}: {dotted} does not exist")
                continue
            if inspect.iscoroutinefunction(target):
                owner, _, leaf = dotted.rpartition(".")
                holder = _resolve(client, owner) if owner else client
                if not hasattr(holder, f"{leaf}_sync"):
                    problems.append(f"{endpoint}: {dotted} has no {leaf}_sync twin")
    assert problems == []


def test_mapping_has_no_stale_endpoints() -> None:
    known = set(_routes()) | {"pty_connect"}
    assert set(ServerClient.ENDPOINT_METHODS) <= known
