"""Reusable contract tests for providers.

Subclass :class:`ProviderContractTests` in your plugin's test-suite and set ``provider_id``::

    from easy_sandbox.providers.testing import ProviderContractTests

    class TestMyProvider(ProviderContractTests):
        provider_id = "my-provider"
        provider_options = {"token": "test"}

or run the bundled module against an installed plugin::

    pytest --pyargs easy_sandbox.providers.testing --provider-under-test my-provider

(the option is registered by ``easy_sandbox.providers.testing`` used as a pytest plugin:
``pytest -p easy_sandbox.providers.testing``). Tests only exercise features the plugin declares.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast

import pytest

from easy_sandbox.api.sandbox import Sandbox
from easy_sandbox.models.errors import (
    ProviderFeatureNotSupportedError,
    ProviderResourceNotFoundError,
)
from easy_sandbox.providers import registry
from easy_sandbox.providers.base import FEATURES

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from easy_sandbox.models.process import ProcessResult

T = TypeVar("T")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--provider-under-test",
        action="store",
        default=os.environ.get("EBX_PROVIDER_UNDER_TEST"),
        help="Provider id to run ProviderContractTests against.",
    )


def _run(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


class ProviderContractTests:
    """Behavioural contract every provider must satisfy for the features it declares."""

    provider_id: ClassVar[str | None] = None
    provider_options: ClassVar[dict[str, Any]] = {}

    @pytest.fixture
    def pid(self, request: pytest.FixtureRequest) -> str:
        chosen = self.provider_id or request.config.getoption("--provider-under-test", default=None)
        if not chosen:
            pytest.skip("set provider_id or --provider-under-test")
        return str(chosen)

    def _features(self, pid: str) -> frozenset[str]:
        return frozenset(registry.get_provider(pid).features)

    def _need(self, pid: str, feature: str) -> None:
        if feature not in self._features(pid):
            pytest.skip(f"{pid} does not declare {feature}")

    def test_declared_features_are_known(self, pid: str) -> None:
        unknown = set(registry.get_provider(pid).features) - set(FEATURES)
        assert not unknown

    def test_lifecycle(self, pid: str) -> None:
        self._need(pid, "sandbox.lifecycle")

        async def scenario() -> None:
            sb = await Sandbox.create(provider=pid, provider_options=dict(self.provider_options))
            try:
                assert sb.provider == pid
                info = await Sandbox.connect(
                    sb.id, provider=pid, provider_options=dict(self.provider_options)
                )
                assert info.id == sb.id
                await info.close()
                listed = await Sandbox.list(
                    provider=pid, provider_options=dict(self.provider_options)
                )
                assert sb.id in {i.sandbox_id for i in listed}
            finally:
                await sb.kill()
            # kill is idempotent and unknown ids are "not found"
            await Sandbox.kill_by_id(
                sb.id, provider=pid, provider_options=dict(self.provider_options)
            )
            with pytest.raises(ProviderResourceNotFoundError):
                await Sandbox.connect(
                    "does-not-exist-0000",
                    provider=pid,
                    provider_options=dict(self.provider_options),
                )

        _run(scenario())

    def test_exec_run(self, pid: str) -> None:
        self._need(pid, "exec.run")

        async def scenario() -> None:
            sb = await Sandbox.create(provider=pid, provider_options=dict(self.provider_options))
            try:
                res = cast("ProcessResult", await sb.commands.run("echo contract"))
                assert res.exit_code == 0
                assert "contract" in res.stdout
            finally:
                await sb.kill()

        _run(scenario())

    def test_files_roundtrip(self, pid: str) -> None:
        self._need(pid, "files.rw")

        async def scenario() -> None:
            sb = await Sandbox.create(provider=pid, provider_options=dict(self.provider_options))
            try:
                await sb.files.write("/contract.txt", "hello")
                assert await sb.files.read("/contract.txt") == "hello"
            finally:
                await sb.kill()

        _run(scenario())

    def test_undeclared_feature_fails_with_e8004(self, pid: str) -> None:
        self._need(pid, "sandbox.lifecycle")
        probes: dict[str, Callable[[Sandbox], Awaitable[Any]]] = {
            "sandbox.pause": lambda sb: sb.pause(),
            "code.interpret": lambda sb: sb.run_code("1 + 1"),
            "files.watch": lambda sb: sb.files.watch("/"),
            "exec.run": lambda sb: sb.commands.run("true"),
            "files.rw": lambda sb: sb.files.read("/x"),
        }
        undeclared = {f: p for f, p in probes.items() if f not in self._features(pid)}
        if not undeclared:
            pytest.skip("provider declares every probed feature")

        async def scenario() -> None:
            sb = await Sandbox.create(provider=pid, provider_options=dict(self.provider_options))
            try:
                for feature, probe in undeclared.items():
                    with pytest.raises(ProviderFeatureNotSupportedError) as err:
                        await probe(sb)
                    assert err.value.code == "E8004", feature
            finally:
                await sb.kill()

        _run(scenario())


__all__ = ["ProviderContractTests", "pytest_addoption"]
