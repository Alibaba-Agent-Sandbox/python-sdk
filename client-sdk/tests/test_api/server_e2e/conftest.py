"""Fixtures for client tests that run against a real in-process SandboxServer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from agent_sandbox.api.server_client import ServerClient

from ._live import LiveServer

pytest.importorskip("agent_sandbox.server", reason="needs the agent-sandbox-server distribution")

from agent_sandbox.server.router import default_table  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _pristine_server_groups() -> Iterator[None]:
    """Other suites leave group aliases on the shared default table; start every test clean."""

    def reset() -> None:
        default_table().clear_group_overrides()

    reset()
    yield
    reset()


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``base/{out,secret}`` with files; ``ABX_SERVER_BASE_DIR`` points at ``base``."""
    base = tmp_path / "base"
    (base / "out").mkdir(parents=True)
    (base / "secret").mkdir()
    (base / "out" / "a.txt").write_text("alpha")
    (base / "secret" / "s.txt").write_text("top-secret")
    (tmp_path / "outside.txt").write_text("outside")
    monkeypatch.setenv("ABX_SERVER_BASE_DIR", str(base))
    return base


@pytest.fixture
def server_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[..., tuple[LiveServer, ServerClient]]]:
    """``server_factory(policy=..., token=...)`` -> ``(live, client)``."""
    for var in ("ABX_SERVER_TOKEN", "ABX_SERVER_POLICY", "ABX_SERVER_POLICY_FILE"):
        monkeypatch.delenv(var, raising=False)
    started: list[LiveServer] = []

    def factory(*, token: str | None = None, **kwargs: Any) -> tuple[LiveServer, ServerClient]:
        live = LiveServer(**kwargs)
        started.append(live)
        return live, ServerClient(live.url, token=token, pty_url=live.pty_url, timeout=15)

    yield factory
    for live in started:
        live.close()
