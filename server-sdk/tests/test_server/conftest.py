"""Fixtures for live-server policy tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from easy_sandbox.server.router import _DEFAULT_DISABLED, CapabilityGroup, default_table

from ._live import Live

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _pristine_default_table() -> Iterator[None]:
    """Some legacy tests leave opt-in groups enabled on the shared table; start clean."""

    def reset() -> None:
        table = default_table()
        for group in CapabilityGroup:
            if group == CapabilityGroup.CORE:
                continue
            if group in _DEFAULT_DISABLED:
                table.disable_group(group)
            else:
                table.enable_group(group)

    reset()
    yield
    reset()


@pytest.fixture
def live_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Live]]:
    """Factory: ``live_server(policy={...})`` -> running :class:`Live` server."""
    monkeypatch.delenv("EBX_SERVER_TOKEN", raising=False)
    monkeypatch.delenv("EBX_SERVER_POLICY", raising=False)
    monkeypatch.delenv("EBX_SERVER_POLICY_FILE", raising=False)
    started: list[Live] = []

    def factory(**kwargs: Any) -> Live:
        live = Live(**kwargs)
        started.append(live)
        return live

    yield factory
    for live in started:
        live.close()


@pytest.fixture
def sandbox_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A base dir with ``out/`` and ``secret/`` plus a file outside the base."""
    root = tmp_path / "base"
    (root / "out").mkdir(parents=True)
    (root / "secret").mkdir()
    (root / "out" / "a.txt").write_text("alpha")
    (root / "out" / ".env").write_text("TOKEN=1")
    (root / "secret" / "s.txt").write_text("top-secret")
    (tmp_path / "outside.txt").write_text("outside-data")
    monkeypatch.setenv("EBX_SERVER_BASE_DIR", str(root))
    return root
