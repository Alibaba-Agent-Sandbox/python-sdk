"""``ServerClient`` against a real in-process ``SandboxServer`` (the built-in defaults)."""

from __future__ import annotations

import base64
import contextlib
import io
import subprocess
import tarfile
import time
import zipfile
from typing import TYPE_CHECKING, Any

import pytest

from agent_sandbox.api.server_client import ServerClient
from agent_sandbox.models.errors import (
    CommandNotFoundError,
    CommandTimeoutError,
    EndpointNotAvailableError,
    FileNotFoundError_,
    FilePolicyDeniedError,
    ServerAPIError,
)
from agent_sandbox.models.server import ShellEventType

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def server(server_factory: Any, tree: Path) -> ServerClient:  # noqa: F811
    from agent_sandbox.server.registry import CommandArg, CommandRegistry

    registry = CommandRegistry()

    def greet(name: str) -> str:
        return f"hello {name}"

    registry.register(
        "greet",
        greet,
        args=[CommandArg(name="name", type="string", required=True)],
        description="Greet",
    )
    live, client = server_factory(registry=registry)
    return client


class TestCoreAndDiscovery:
    async def test_health(self, server: ServerClient) -> None:
        assert await server.health() is True

    async def test_health_false_when_unreachable(self) -> None:
        client = ServerClient("http://127.0.0.1:1", timeout=1)
        assert await client.health() is False

    async def test_discover_unconfigured_server(self, server: ServerClient) -> None:
        assert server.capabilities is None
        caps = await server.discover()
        assert server.capabilities is caps
        assert caps.configured is False and caps.api_version == 2
        assert caps.can("files_upload_stream") and caps.can("shell")
        assert caps.can("code_run") is False
        assert caps.denial("code_run") == "endpoint_disabled"
        assert caps.rule("code_run") == "default:opt-in:dev_tools"
        assert caps.groups["file_ops"] is True and caps.groups["dev_tools"] is False
        assert caps.group_summary["dev_tools"]["enabled"] == 0
        assert caps.group_summary["file_ops"]["enabled"] == caps.group_summary["file_ops"]["total"]
        with pytest.raises(EndpointNotAvailableError) as disabled:
            caps.require("code_run")
        assert "default:opt-in:dev_tools" in str(disabled.value)
        assert disabled.value.rule == "default:opt-in:dev_tools"

    async def test_commands_list_and_run(self, server: ServerClient) -> None:
        commands = await server.commands.list()
        assert [c.name for c in commands] == ["greet"]
        assert commands[0].args[0].name == "name"
        assert await server.commands.run("greet", name="ada") == "hello ada"

    async def test_unknown_command_is_command_not_found(self, server: ServerClient) -> None:
        with pytest.raises(CommandNotFoundError):
            await server.commands.run("nope")

    async def test_bad_command_args_are_server_errors(self, server: ServerClient) -> None:
        with pytest.raises(ServerAPIError) as exc:
            await server.commands.run("greet")
        assert exc.value.status_code == 400


class TestFiles:
    async def test_full_lifecycle(self, server: ServerClient, tree: Path) -> None:
        out = tree / "out"
        made = await server.files.mkdir(str(out / "sub"))
        assert made.created
        result = await server.files.upload(str(out / "sub" / "x.bin"), b"\x00\x01data")
        assert result.size == 6
        info = await server.files.stat(str(out / "sub" / "x.bin"))
        assert info.exists and info.size == 6 and info.type == "file"
        assert await server.files.exists(str(out / "sub" / "x.bin")) is True
        assert await server.files.exists(str(out / "missing")) is False
        assert await server.files.download(str(out / "sub" / "x.bin")) == b"\x00\x01data"
        names = {e.name for e in await server.files.list(str(out / "sub"))}
        assert names == {"x.bin"}
        moved = await server.files.move(str(out / "sub" / "x.bin"), str(out / "sub" / "y.bin"))
        assert moved.destination.endswith("y.bin")
        hits = await server.files.search(str(out), "*.bin")
        assert [h.name for h in hits.results] == ["y.bin"]
        await server.files.delete(str(out / "sub"))
        assert not (out / "sub").exists()

    async def test_text_and_file_helpers(
        self, server: ServerClient, tree: Path, tmp_path: Path
    ) -> None:
        target = str(tree / "out" / "t.txt")
        await server.files.upload(target, "héllo")
        assert await server.files.read_text(target) == "héllo"
        local = tmp_path / "local.txt"
        local.write_text("from-local")
        await server.files.upload_file(local, str(tree / "out" / "up.txt"))
        assert (tree / "out" / "up.txt").read_text() == "from-local"
        dest = tmp_path / "down.txt"
        assert await server.files.download_file(str(tree / "out" / "up.txt"), dest) == 10
        assert dest.read_text() == "from-local"

    async def test_list_recursive_and_limits(self, server: ServerClient, tree: Path) -> None:
        entries = await server.files.list(str(tree), recursive=True)
        assert {e.name for e in entries} >= {"out", "secret", "a.txt", "s.txt"}
        limited = await server.files.list(str(tree), recursive=True, max_entries=1)
        assert len(limited) == 1

    @pytest.mark.parametrize("fmt", ["zip", "tar.gz"])
    async def test_archive(self, server: ServerClient, tree: Path, fmt: str) -> None:
        archive = await server.files.archive([str(tree / "out")], fmt)
        assert archive.format == fmt and archive.size == len(archive.data)
        if fmt == "zip":
            with zipfile.ZipFile(io.BytesIO(archive.data)) as zf:
                assert any(n.endswith("a.txt") for n in zf.namelist())
        else:
            with tarfile.open(fileobj=io.BytesIO(archive.data), mode="r:gz") as tf:
                assert any(n.endswith("a.txt") for n in tf.getnames())

    async def test_legacy_upload_download(self, server: ServerClient, tree: Path) -> None:
        target = str(tree / "out" / "legacy.bin")
        assert (await server.files.upload_legacy(target, b"abc")).size == 3
        assert await server.files.download_legacy(target) == b"abc"

    async def test_watch_reports_changes(self, server: ServerClient, tree: Path) -> None:
        import asyncio

        watched = tree / "out"

        async def mutate() -> None:
            await asyncio.sleep(0.6)
            (watched / "w.txt").write_text("1")

        task = asyncio.create_task(mutate())
        events = await server.files.watch_for(str(watched), 2.0, interval=0.1)
        await task
        assert any(e.type.value == "created" and e.path.endswith("w.txt") for e in events)

    async def test_watch_can_be_closed_early(self, server: ServerClient, tree: Path) -> None:
        import asyncio

        async def mutate() -> None:
            await asyncio.sleep(0.6)
            (tree / "out" / "early.txt").write_text("x")

        task = asyncio.create_task(mutate())
        started = time.monotonic()
        got = None
        async with contextlib.aclosing(
            server.files.watch(str(tree / "out"), timeout=30, interval=0.1)
        ) as stream:
            async for event in stream:
                got = event
                break
        await task
        assert got is not None and got.path.endswith("early.txt")
        assert time.monotonic() - started < 10

    async def test_missing_file_download_error(self, server: ServerClient, tree: Path) -> None:
        with pytest.raises(FileNotFoundError_):
            await server.files.download(str(tree / "out" / "nope"))


class TestProcess:
    async def test_shell(
        self, server: ServerClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ABX_SERVER_BASE_DIR", str(tmp_path))
        result = await server.process.shell("echo hi")
        assert result.success and result.stdout == "hi\n"
        result = await server.process.shell(
            "sh -c 'pwd; echo $X'", cwd=str(tmp_path), env={"X": "1"}
        )
        assert result.stdout.split() == [str(tmp_path.resolve()), "1"]
        failed = await server.process.shell("sh -c 'exit 3'")
        assert failed.exit_code == 3 and not failed.success

    async def test_shell_cwd_outside_the_base_dir_is_denied(
        self, server: ServerClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inside = tmp_path / "inside"
        inside.mkdir()
        monkeypatch.setenv("ABX_SERVER_BASE_DIR", str(inside))
        with pytest.raises(FilePolicyDeniedError) as denied:
            await server.process.shell("pwd", cwd=str(tmp_path))
        assert denied.value.error_code == "path_not_allowed" and denied.value.status_code == 403

    async def test_shell_timeout(self, server: ServerClient) -> None:
        with pytest.raises(CommandTimeoutError):
            await server.process.shell("sleep 5", timeout=0.3)

    async def test_shell_stream_events(self, server: ServerClient) -> None:
        events = [
            e async for e in server.process.shell_stream("sh -c 'echo out; echo err >&2; exit 2'")
        ]
        kinds = {e.event for e in events}
        assert {ShellEventType.STDOUT, ShellEventType.STDERR, ShellEventType.EXIT} <= kinds
        assert events[-1].event == ShellEventType.EXIT and events[-1].exit_code == 2

    async def test_run_stream_callbacks(self, server: ServerClient) -> None:
        seen: list[str] = []
        result = await server.process.run_stream("sh -c 'echo a; echo b'", on_stdout=seen.append)
        assert seen == ["a", "b"] and result.stdout == "a\nb\n" and result.success

    async def test_run_stream_timeout_maps(self, server: ServerClient) -> None:
        with pytest.raises(CommandTimeoutError):
            await server.process.run_stream("sleep 5", timeout=0.3)

    async def test_background_process_output_and_wait(self, server: ServerClient) -> None:
        proc = await server.process.start(
            "sh -c 'echo one; sleep 0.2; echo two'", capture_output=True
        )
        events = [e async for e in server.process.follow(proc.pid, poll=1)]
        assert "".join(e.data for e in events).replace("\n", "") == "onetwo"
        assert await server.process.wait(proc.pid, timeout=5) == 0
        info = await server.process.get(proc.pid)
        assert info.state != "running" and info.exit_code == 0

    async def test_stdin_roundtrip(self, server: ServerClient) -> None:
        proc = await server.process.start("cat", capture_output=True, stdin=True)
        wrote = await server.process.send_stdin(proc.pid, "ping\n")
        assert wrote.written == 5 and wrote.closed is False
        await server.process.send_stdin(proc.pid, b"bytes\n")
        closed = await server.process.close_stdin(proc.pid)
        assert closed.closed is True
        out = await server.process.output(proc.pid, wait=3)
        deadline = time.time() + 5
        while out.state == "running" and time.time() < deadline:
            more = await server.process.output(proc.pid, since=out.next, wait=1)
            out = out.model_copy(
                update={"events": out.events + more.events, "state": more.state, "next": more.next}
            )
        assert out.stdout == "ping\nbytes\n"

    async def test_list_signal_kill(self, server: ServerClient) -> None:
        proc = await server.process.start("sleep 30")
        assert proc.pid in [p.pid for p in await server.process.list()]
        assert (await server.process.get(proc.pid)).running
        sig = await server.process.terminate(proc.pid)
        assert sig.signal == 15
        assert await server.process.wait(proc.pid, timeout=5) != 0
        other = await server.process.start("sleep 30")
        await server.process.kill(other.pid)
        assert await server.process.wait(other.pid, timeout=5) != 0

    async def test_wait_timeout(self, server: ServerClient) -> None:
        proc = await server.process.start("sleep 30")
        with pytest.raises(CommandTimeoutError):
            await server.process.wait(proc.pid, timeout=0.3, poll=0.1)
        await server.process.kill(proc.pid)

    async def test_unknown_pid(self, server: ServerClient) -> None:
        with pytest.raises(ServerAPIError) as exc:
            await server.process.get(999999)
        assert exc.value.status_code == 404


class TestPty:
    async def test_session_lifecycle_and_websocket(self, server: ServerClient) -> None:
        created = await server.pty.create("/bin/sh", cols=90, rows=30)
        try:
            listed = await server.pty.list()
            assert created.session_id in [s.id for s in listed]
            info = await server.pty.get(created.session_id)
            assert (info.cols, info.rows, info.alive) == (90, 30, True)
            resized = await server.pty.resize(created.session_id, 100, 40)
            assert (resized.cols, resized.rows) == (100, 40)
            async with server.pty.connect(created.session_id) as term:
                first = await term.recv(timeout=5)
                assert first is not None and first.event == "started"
                await term.send("echo marker-$((6*7))\n")
                text = await term.expect("marker-42", timeout=10)
                assert "marker-42" in text
                await term.resize(110, 45)
        finally:
            await server.pty.delete(created.session_id)
        with pytest.raises(ServerAPIError) as exc:
            await server.pty.get(created.session_id)
        assert exc.value.status_code == 404

    async def test_expect_times_out(self, server: ServerClient) -> None:
        created = await server.pty.create("/bin/sh")
        try:
            async with server.pty.connect(created.session_id) as term:
                with pytest.raises(CommandTimeoutError):
                    await term.expect("never-appears-xyz", timeout=0.5)
        finally:
            await server.pty.delete(created.session_id)


class TestSystem:
    async def test_info_metrics_env_ports_packages(self, server: ServerClient) -> None:
        info = await server.system.info()
        assert info.cpu_count > 0 and info.os
        metrics = await server.system.metrics()
        assert metrics.memory_total_mb > 0
        assert await server.system.set_env({"CLIENT_TEST_VAR": "yes"}) == ["CLIENT_TEST_VAR"]
        env = await server.system.env()
        assert env["CLIENT_TEST_VAR"] == "yes"
        filtered = await server.system.env(["CLIENT_TEST_VAR"])
        assert list(filtered) == ["CLIENT_TEST_VAR"]
        ports = await server.system.ports()
        assert isinstance(ports, list)
        packages = await server.system.packages("pip")
        assert packages.manager == "pip"


class TestDevtoolsAndBrowser:
    async def test_devtools_off_by_default(self, server: ServerClient) -> None:
        with pytest.raises(EndpointNotAvailableError) as exc:
            await server.devtools.run_code("print(1)")
        assert exc.value.endpoint == "code_run"
        assert exc.value.status_code == 404

    async def test_devtools_enabled(self, server_factory: Any, tree: Path) -> None:
        _live, client = server_factory(policy={"groups": {"dev_tools": True}})
        result = await client.devtools.run_code("print(6*7)")
        assert result.success and result.stdout.strip() == "42"
        bash = await client.devtools.run_code("echo hi", "bash")
        assert bash.stdout.strip() == "hi"
        subprocess.run(["git", "init", "-q", str(tree)], check=True)
        (tree / "f.txt").write_text("1")
        status = await client.devtools.git_status(str(tree))
        assert status.clean is False and any(f.path.endswith("f.txt") for f in status.files)
        diff = await client.devtools.git_diff(str(tree), staged=False)
        assert isinstance(diff.diff, str)

    async def test_browser_off_by_default(self, server: ServerClient) -> None:
        with pytest.raises(EndpointNotAvailableError):
            await server.browser.navigate("https://example.com")
        with pytest.raises(EndpointNotAvailableError):
            await server.browser.console()


class TestSyncTwins:
    def test_sync_wrappers_against_real_server(self, server_factory: Any, tree: Path) -> None:
        _live, client = server_factory()
        assert client.health_sync() is True
        caps = client.discover_sync()
        assert caps.can("shell")
        target = str(tree / "out" / "s.txt")
        assert client.files.upload_sync(target, "sync").size == 4
        assert client.files.read_text_sync(target) == "sync"
        assert client.files.exists_sync(target) is True
        assert client.process.shell_sync("echo sync").stdout == "sync\n"
        assert client.system.info_sync().cpu_count > 0
        proc = client.process.start_sync("sleep 30")
        assert client.process.get_sync(proc.pid).running
        client.process.kill_sync(proc.pid)
        assert client.commands.list_sync() == []
        client.aclose_sync()

    def test_every_coroutine_has_a_sync_twin(self) -> None:
        import inspect

        client = ServerClient("http://127.0.0.1:1")
        owners: list[Any] = [
            client,
            client.files,
            client.process,
            client.pty,
            client.system,
            client.devtools,
            client.browser,
            client.commands,
        ]
        missing: list[str] = []
        for owner in owners:
            for name, member in inspect.getmembers(type(owner)):
                if name.startswith("_") or name.endswith("_sync"):
                    continue
                if inspect.iscoroutinefunction(member) and not hasattr(owner, f"{name}_sync"):
                    missing.append(f"{type(owner).__name__}.{name}")
        assert missing == []


def test_base64_is_not_leaked_into_models() -> None:
    from agent_sandbox.models.server import ArchiveResult

    result = ArchiveResult(content_base64=base64.b64encode(b"zz").decode(), bytes=2)
    assert result.data == b"zz" and result.size == 2
