"""Behaviour of the declarative layer when ``easy-sandbox-server`` is not installed.

``easy_sandbox.server`` ships in a separate distribution; a client-only install
must fail with an actionable message instead of a bare ``ModuleNotFoundError``.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from easy_sandbox.declarative.decorator import _SandboxFactory


@pytest.fixture
def no_server(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [m for m in sys.modules if m.startswith("easy_sandbox.server")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "easy_sandbox.server", None)


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
    lambda f: f.register.upload(),
    lambda f: f.register.download(),
]


@pytest.mark.xfail(
    reason="declarative lazily imports easy_sandbox.server and surfaces a bare "
    "ModuleNotFoundError; it should point at `pip install easy-sandbox[server]`",
    strict=True,
)
@pytest.mark.parametrize("action", _ACTIONS, ids=["start", "getattr", "upload", "download"])
def test_missing_server_error_names_the_distribution(no_server: None, action: Any) -> None:
    factory = _SandboxFactory()
    with pytest.raises(ImportError) as excinfo:
        action(factory)
    message = str(excinfo.value)
    assert "easy-sandbox-server" in message or "easy-sandbox[server]" in message
