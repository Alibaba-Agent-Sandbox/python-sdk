"""Fixtures for client tests that run against a real in-process SandboxServer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from easy_sandbox.api.server_client import ServerClient

from ._live import LiveServer

pytest.importorskip("easy_sandbox.server", reason="needs the easy-sandbox-server distribution")

from easy_sandbox.server.router import _DEFAULT_DISABLED, CapabilityGroup, default_table  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _pristine_server_groups() -> Iterator[None]:
    """Other suites toggle groups on the shared default table; start every test clean."""

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
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``base/{out,secret}`` with files; ``EBX_SERVER_BASE_DIR`` points at ``base``."""
    base = tmp_path / "base"
    (base / "out").mkdir(parents=True)
    (base / "secret").mkdir()
    (base / "out" / "a.txt").write_text("alpha")
    (base / "secret" / "s.txt").write_text("top-secret")
    (tmp_path / "outside.txt").write_text("outside")
    monkeypatch.setenv("EBX_SERVER_BASE_DIR", str(base))
    return base


@pytest.fixture
def server_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[..., tuple[LiveServer, ServerClient]]]:
    """``server_factory(policy=..., token=...)`` -> ``(live, client)``."""
    for var in ("EBX_SERVER_TOKEN", "EBX_SERVER_POLICY", "EBX_SERVER_POLICY_FILE"):
        monkeypatch.delenv(var, raising=False)
    started: list[LiveServer] = []

    def factory(*, token: str | None = None, **kwargs: Any) -> tuple[LiveServer, ServerClient]:
        live = LiveServer(**kwargs)
        started.append(live)
        return live, ServerClient(live.url, token=token, pty_url=live.pty_url, timeout=15)

    yield factory
    for live in started:
        live.close()
