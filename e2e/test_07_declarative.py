"""``@sandbox`` declarative remote execution on the real cloud."""

from __future__ import annotations

import asyncio

import pytest

import e2e_helpers as H
from easy_sandbox import sandbox


def test_decorated_function_runs_remotely_on_an_existing_sandbox(sandbox_factory):  # type: ignore[no-untyped-def]
    sb = sandbox_factory(H.OFFICIAL_BASE)

    @sandbox(sandbox_id=sb.id)
    def summarize(values, scale=1):
        import platform

        return {"total": sum(values) * scale, "os": platform.system()}

    assert summarize([1, 2, 3], scale=10) == {"total": 60, "os": "Linux"}


def test_remote_exception_surfaces_as_runtime_error(sandbox_factory):  # type: ignore[no-untyped-def]
    sb = sandbox_factory(H.OFFICIAL_BASE)

    @sandbox(sandbox_id=sb.id)
    def boom():
        raise ValueError("e2e-remote-boom")

    with pytest.raises(RuntimeError) as err:
        boom()
    assert "e2e-remote-boom" in str(err.value)


def test_async_decorated_function(sandbox_factory):  # type: ignore[no-untyped-def]
    sb = sandbox_factory(H.OFFICIAL_BASE)

    @sandbox(sandbox_id=sb.id)
    async def double(x):
        return x * 2

    assert asyncio.run(double(21)) == 42


def test_decorator_with_existing_sandbox_does_not_kill_it(run, sandbox_factory):  # type: ignore[no-untyped-def]
    sb = sandbox_factory(H.OFFICIAL_BASE)

    @sandbox(sandbox_id=sb.id)
    def noop():
        return "ok"

    assert noop() == "ok"
    assert run(sb.is_running()) is True


def test_decorator_creates_and_destroys_its_own_sandbox(run):  # type: ignore[no-untyped-def]
    """Full create path. The decorator cannot tag the sandbox, so it relies on its own ``finally``
    kill plus the short TTL below; the janitor script covers anything that still leaks."""
    from easy_sandbox.api.sandbox import Sandbox

    @sandbox(template=H.OFFICIAL_BASE, timeout=120)
    def where():
        import os

        return os.getcwd() != ""

    before = {i.sandbox_id for i in run(Sandbox.list(limit=200))}
    assert where() is True

    def _no_new_sandbox_left() -> bool:
        after = {i.sandbox_id for i in run(Sandbox.list(limit=200))}
        return not (after - before)

    H.eventually(_no_new_sandbox_left, timeout=40, interval=3, what="decorator-created sandbox to be killed")


def test_invalid_serializer_is_rejected_locally():
    with pytest.raises(ValueError):

        @sandbox(serializer="pickle")
        def f():
            return 1
