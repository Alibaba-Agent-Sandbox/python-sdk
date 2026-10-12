"""SDK-level behaviour of ``Sandbox.create(provider="opensandbox")`` (exec-provider adapters)."""

from __future__ import annotations

import asyncio
import time

import pytest

from easy_sandbox.api.sandbox import Sandbox
from easy_sandbox.models.errors import (
    FileNotFoundError_,
    ProviderFeatureNotSupportedError,
    ProviderResourceNotFoundError,
)
from easy_sandbox.models.process import ProcessChunkType

PID = "opensandbox"


def run(coro):
    return asyncio.run(coro)


async def _create(**kw):
    return await Sandbox.create(provider=PID, timeout=300, **kw)


def test_exec_streaming_order_and_exit_codes():
    async def scenario():
        sb = await _create(metadata={"suite": "sdk"})
        try:
            res = await sb.commands.run("echo out; echo err >&2; exit 3", shell=True)
            assert (res.exit_code, res.stdout.strip(), res.stderr.strip()) == (3, "out", "err")

            chunks = []
            async for c in sb.commands.stream(
                "sh -c 'echo a; sleep 0.3; echo b; sleep 0.3; echo c'"
            ):
                chunks.append((time.monotonic(), c))
            kinds = [c.type for _, c in chunks]
            assert kinds[-1] == ProcessChunkType.EXIT and kinds.count(ProcessChunkType.EXIT) == 1
            text = "".join(c.data for _, c in chunks if c.type == ProcessChunkType.STDOUT)
            assert text.split() == ["a", "b", "c"]
            stdout_times = [t for t, c in chunks if c.type == ProcessChunkType.STDOUT]
            assert stdout_times[-1] - stdout_times[0] > 0.4, "output must arrive incrementally"

            res = await sb.commands.run(
                "echo $FOO:$(pwd)", shell=True, env={"FOO": "bar"}, cwd="/tmp"
            )
            assert res.stdout.strip() == "bar:/tmp"
        finally:
            await sb.kill()

    run(scenario())


def test_files_binary_unicode_and_missing():
    async def scenario():
        sb = await _create()
        try:
            await sb.files.write("/tmp/u.txt", "héllo ✓")
            assert await sb.files.read("/tmp/u.txt") == "héllo ✓"
            assert await sb.files.exists("/tmp/u.txt")
            assert not await sb.files.exists("/tmp/nope")
            names = {f.name for f in await sb.files.list("/tmp")}
            assert "u.txt" in names
            await sb.files.remove("/tmp/u.txt")
            assert not await sb.files.exists("/tmp/u.txt")
            with pytest.raises(FileNotFoundError_) as err:
                await sb.files.read("/tmp/definitely-missing")
            assert err.value.code == "E4001"
        finally:
            await sb.kill()

    run(scenario())


def test_timeout_pause_resume_and_process_list():
    async def scenario():
        sb = await _create()
        try:
            await sb.set_timeout(600)
            assert await sb.is_running()
            # StreamReader is lazy: exec.start is only sent once somebody iterates it.
            reader = await sb.commands.start("sleep 120", timeout=130)

            async def drain():
                async for _ in reader:
                    pass

            task = asyncio.create_task(drain())
            await asyncio.sleep(1.5)
            procs = await sb.commands.list()
            assert any("sleep" in (p.command or "") for p in procs)
            task.cancel()
            await sb.pause()
            await sb.resume()
            assert await sb.is_running()
            assert (await sb.commands.run("echo alive")).stdout.strip() == "alive"
        finally:
            await sb.kill()

    run(scenario())


def test_unsupported_features_raise_e8004():
    async def scenario():
        sb = await _create()
        try:
            with pytest.raises(ProviderFeatureNotSupportedError) as err:
                await sb.run_code("1 + 1")
            assert err.value.code == "E8004"
            with pytest.raises(ProviderFeatureNotSupportedError):
                await sb.files.watch("/tmp")
        finally:
            await sb.kill()

    run(scenario())


def test_unknown_sandbox_is_not_found():
    async def scenario():
        with pytest.raises(ProviderResourceNotFoundError):
            await Sandbox.connect("00000000-0000-0000-0000-000000000000", provider=PID)

    run(scenario())
