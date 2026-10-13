"""Behaviour of the declarative layer when ``agent-sandbox-server`` is not installed.

``agent_sandbox.server`` ships in a separate distribution; a client-only install
must fail with an actionable message instead of a bare ``ModuleNotFoundError``.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from agent_sandbox.declarative.decorator import _SandboxFactory


@pytest.fixture
def no_server(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [m for m in sys.modules if m.startswith("agent_sandbox.server")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "agent_sandbox.server", None)


def test_register_still_works_without_server(no_server: None) -> None:
    factory = _SandboxFactory()

    @factory.register
    def double(x: int) -> int:
        return x * 2

    assert double(2) == 4
    assert {c["name"] for c in factory.list_registered()} == {"double"}


_ACTIONS: list[Any] = [
    lambda f: f.server.start(port=1),
    lambda f: f.server.SandboxServer,
]


@pytest.mark.parametrize("action", _ACTIONS, ids=["start", "getattr"])
def test_missing_server_error_names_the_distribution(no_server: None, action: Any) -> None:
    factory = _SandboxFactory()
    with pytest.raises(ImportError) as excinfo:
        action(factory)
    message = str(excinfo.value)
    assert "pip install agent-sandbox-server" in message


def test_empty_namespace_after_inplace_upgrade_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """An in-place 0.2.x upgrade can leave ``agent_sandbox.server`` as an empty namespace."""
    import types

    for name in [m for m in sys.modules if m.startswith("agent_sandbox.server")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(
        sys.modules, "agent_sandbox.server", types.ModuleType("agent_sandbox.server")
    )
    with pytest.raises(ImportError) as excinfo:
        _SandboxFactory().server.start(port=1)
    assert "--force-reinstall --no-deps agent-sandbox-server" in str(excinfo.value)
