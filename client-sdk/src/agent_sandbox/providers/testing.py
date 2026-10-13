"""Reusable contract tests for providers.

Three ways to run the kit against a plugin (it only exercises features the plugin declares):

1. **One command** (no test file needed)::

       python -m agent_sandbox.providers test my-provider --option base_url=http://127.0.0.1:8080

2. **pytest, no test file**::

       pytest -p agent_sandbox.providers.testing --pyargs agent_sandbox.providers.contract \\
              --provider-under-test my-provider --provider-option base_url=http://127.0.0.1:8080

3. **Subclass** in your plugin's test-suite and set ``provider_id``::

       from agent_sandbox.providers.testing import ProviderContractTests

       class TestMyProvider(ProviderContractTests):
           provider_id = "my-provider"
           provider_options = {"token": "test"}

The pytest options (``--provider-under-test``, ``--provider-option KEY=VALUE``, repeatable) are
registered by this module used as a pytest plugin (``-p agent_sandbox.providers.testing``).
``agent_sandbox.providers.contract`` holds the ready-made, collectable subclass for forms 1 and 2.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
import uuid
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast

import pytest

from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.models.errors import (
    CapabilityNotSupportedError,
    FileNotFoundError_,
    ProviderFeatureNotSupportedError,
    ProviderResourceNotFoundError,
    SandboxError,
    SandboxNotFoundError,
)
from agent_sandbox.providers import registry
from agent_sandbox.providers.base import FEATURES

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from agent_sandbox.models.process import ProcessChunk, ProcessResult

T = TypeVar("T")

_UNKNOWN_ID = "does-not-exist-0000"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--provider-under-test",
        action="store",
        default=os.environ.get("ABX_PROVIDER_UNDER_TEST"),
        help="Provider id to run ProviderContractTests against.",
    )
    parser.addoption(
        "--provider-option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Provider option passed as provider_options (repeatable).",
    )


def _run(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


def parse_options(pairs: list[str]) -> dict[str, str]:
    """Turn ``["a=1", "b=x=y"]`` into ``{"a": "1", "b": "x=y"}``."""
    out: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            raise pytest.UsageError(f"--provider-option expects KEY=VALUE, got {pair!r}")
        out[key.strip()] = value
    return out


class ProviderContractTests:
    """Behavioural contract every provider must satisfy for the features it declares."""

    provider_id: ClassVar[str | None] = None
    provider_options: ClassVar[dict[str, Any]] = {}

    @pytest.fixture
    def pid(self, request: pytest.FixtureRequest) -> str:
        chosen = self.provider_id or request.config.getoption("--provider-under-test", default=None)
        if not chosen:
            pytest.fail(
                "no provider selected: set provider_id on the class or pass --provider-under-test",
                pytrace=False,
            )
        return str(chosen)

    @pytest.fixture
    def popts(self, request: pytest.FixtureRequest) -> dict[str, Any]:
        cli = parse_options(list(request.config.getoption("--provider-option", default=[]) or []))
        return {**self.provider_options, **cli}

    # ---- helpers

    def _features(self, pid: str) -> frozenset[str]:
        return frozenset(registry.get_provider(pid).features)

    def _need(self, pid: str, *features: str) -> None:
        for feature in features:
            if feature not in self._features(pid):
                pytest.skip(f"{pid} does not declare {feature}")

    @contextlib.asynccontextmanager
    async def _sandbox(self, pid: str, popts: dict[str, Any]) -> AsyncIterator[Sandbox]:
        sb = await Sandbox.create(provider=pid, provider_options=dict(popts))
        try:
            yield sb
        finally:
            await sb.kill()

    # ---- declaration

    def test_declared_features_are_known(self, pid: str) -> None:
        unknown = set(registry.get_provider(pid).features) - set(FEATURES)
        assert not unknown

    def test_describe_never_exposes_secret_defaults(self, pid: str) -> None:
        info = registry.get_provider(pid).describe()
        for field in info["config_fields"]:
            if field["secret"]:
                assert field["default"] in (None, ""), f"secret field {field['key']} has a default"

    # ---- lifecycle

    def test_lifecycle(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "sandbox.lifecycle")

        async def scenario() -> None:
            sb = await Sandbox.create(provider=pid, provider_options=dict(popts))
            try:
                assert sb.provider == pid
                info = await Sandbox.connect(sb.id, provider=pid, provider_options=dict(popts))
                assert info.id == sb.id
                await info.close()
                listed = await Sandbox.list(provider=pid, provider_options=dict(popts))
                assert sb.id in {i.sandbox_id for i in listed}
            finally:
                await sb.kill()
            await Sandbox.kill_by_id(sb.id, provider=pid, provider_options=dict(popts))
            with pytest.raises(SandboxNotFoundError):
                await Sandbox.connect(_UNKNOWN_ID, provider=pid, provider_options=dict(popts))

        _run(scenario())

    def test_kill_is_idempotent(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "sandbox.lifecycle")

        async def scenario() -> None:
            sb = await Sandbox.create(provider=pid, provider_options=dict(popts))
            sandbox_id = sb.id
            await sb.kill()
            for _ in range(2):
                await Sandbox.kill_by_id(sandbox_id, provider=pid, provider_options=dict(popts))
            await Sandbox.kill_by_id(_UNKNOWN_ID, provider=pid, provider_options=dict(popts))

        _run(scenario())

    def test_set_timeout(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "sandbox.lifecycle", "sandbox.timeout")

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                await sb.set_timeout(600)

        _run(scenario())

    def test_pause_resume(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "sandbox.lifecycle", "sandbox.pause")

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                await sb.pause()
                await sb.resume()
                if "exec.run" in self._features(pid):
                    res = cast("ProcessResult", await sb.commands.run("echo back", shell=True))
                    assert "back" in res.stdout

        _run(scenario())

    # ---- exec

    def test_exec_run(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "exec.run")

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                res = cast("ProcessResult", await sb.commands.run("echo contract"))
                assert res.exit_code == 0
                assert "contract" in res.stdout

        _run(scenario())

    def test_exec_exit_code_stderr_and_env(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "exec.run")

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                bad = cast(
                    "ProcessResult", await sb.commands.run("echo oops >&2; exit 3", shell=True)
                )
                assert bad.exit_code == 3
                assert "oops" in bad.stderr
                env = cast(
                    "ProcessResult",
                    await sb.commands.run(
                        "echo $CONTRACT_VAR", shell=True, env={"CONTRACT_VAR": "v1"}
                    ),
                )
                assert env.stdout.strip() == "v1"

        _run(scenario())

    def test_exec_stream_order_and_single_exit(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "exec.run", "exec.stream")

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                chunks: list[ProcessChunk] = []
                async for chunk in sb.commands.stream("echo one; sleep 0.3; echo two; exit 4"):
                    chunks.append(chunk)
                out = "".join(c.data for c in chunks if c.type.value == "stdout")
                assert out.index("one") < out.index("two")
                exits = [c for c in chunks if c.type.value == "exit"]
                assert len(exits) == 1
                assert exits[0] is chunks[-1]
                assert exits[0].exit_code == 4

        _run(scenario())

    def test_exec_timeout_is_enforced(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "exec.run")

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                started = time.monotonic()
                try:
                    res = cast("ProcessResult", await sb.commands.run("sleep 60", timeout=2))
                except SandboxError:
                    pass
                else:
                    assert res.exit_code != 0
                assert time.monotonic() - started < 45, "timeout was not enforced"

        _run(scenario())

    def test_process_list(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "exec.run", "process.manage")

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                procs = await sb.commands.list()
                assert isinstance(procs, list)

        _run(scenario())

    # ---- files

    def test_files_roundtrip(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "files.rw")

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                await sb.files.write("/contract.txt", "hello")
                assert await sb.files.read("/contract.txt") == "hello"

        _run(scenario())

    def test_files_binary_and_unicode(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "files.rw")
        blob = bytes(range(256)) * 4

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                await sb.files.write("/blob.bin", blob)
                assert await sb.files.read_bytes("/blob.bin") == blob
                await sb.files.write("/uni.txt", "héllo 世界")
                assert await sb.files.read("/uni.txt") == "héllo 世界"
                await sb.files.write("/uni.txt", "short")
                assert await sb.files.read("/uni.txt") == "short"

        _run(scenario())

    def test_files_directory_operations(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "files.rw")
        name = f"contract-{uuid.uuid4().hex[:6]}"

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                await sb.files.make_dir(f"/{name}")
                await sb.files.write(f"/{name}/a.txt", "a")
                names = {e.name for e in await sb.files.list(f"/{name}")}
                assert "a.txt" in names
                assert await sb.files.exists(f"/{name}/a.txt")
                await sb.files.move(f"/{name}/a.txt", f"/{name}/b.txt")
                assert await sb.files.read(f"/{name}/b.txt") == "a"
                assert not await sb.files.exists(f"/{name}/a.txt")
                await sb.files.remove(f"/{name}/b.txt")
                assert not await sb.files.exists(f"/{name}/b.txt")

        _run(scenario())

    def test_missing_file_is_a_typed_not_found(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "files.rw")

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                with pytest.raises((FileNotFoundError_, ProviderResourceNotFoundError)):
                    await sb.files.read("/definitely/not/here.txt")

        _run(scenario())

    # ---- ports

    def test_ports_url(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "ports.url")

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                url = await sb.network.resolve_url(8080)
                assert url.startswith(("http://", "https://"))

        _run(scenario())

    # ---- errors and secrets

    def test_undeclared_feature_fails_with_e8004(self, pid: str, popts: dict[str, Any]) -> None:
        self._need(pid, "sandbox.lifecycle")
        probes: dict[str, Callable[[Sandbox], Awaitable[Any]]] = {
            "sandbox.pause": lambda sb: sb.pause(),
            "code.interpret": lambda sb: sb.run_code("1 + 1"),
            "files.watch": lambda sb: sb.files.watch("/"),
            "exec.run": lambda sb: sb.commands.run("true"),
            "files.rw": lambda sb: sb.files.read("/x"),
            "process.manage": lambda sb: sb.commands.list(),
        }
        undeclared = {f: p for f, p in probes.items() if f not in self._features(pid)}
        if not undeclared:
            pytest.skip("provider declares every probed feature")

        async def scenario() -> None:
            async with self._sandbox(pid, popts) as sb:
                for feature, probe in undeclared.items():
                    with pytest.raises(ProviderFeatureNotSupportedError) as err:
                        await probe(sb)
                    assert err.value.code == "E8004", feature
                    assert isinstance(err.value, CapabilityNotSupportedError), feature

        _run(scenario())

    def test_secret_options_are_redacted_from_errors(self, pid: str, popts: dict[str, Any]) -> None:
        provider = registry.get_provider(pid)
        secret_keys = [f.key for f in provider.config_fields if f.secret]
        if not secret_keys:
            pytest.skip(f"{pid} declares no secret config fields")
        canary = "abx-canary-" + uuid.uuid4().hex

        async def scenario() -> None:
            options = {**popts, **{key: canary for key in secret_keys}}
            raised: SandboxError | None = None
            try:
                sb = await Sandbox.create(provider=pid, provider_options=options)
            except SandboxError as exc:
                raised = exc
            else:
                try:
                    await Sandbox.connect(_UNKNOWN_ID, provider=pid, provider_options=options)
                except SandboxError as exc:
                    raised = exc
                finally:
                    await sb.kill()
            if raised is not None:
                blob = " ".join([str(raised), repr(raised), str(raised.to_dict())])
                assert canary not in blob, "a secret option value leaked into an error"

        _run(scenario())


__all__ = ["ProviderContractTests", "parse_options", "pytest_addoption"]
