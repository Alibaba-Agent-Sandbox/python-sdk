"""envd process API through ``sandbox.commands`` / ``sandbox.run`` on a real sandbox."""

from __future__ import annotations

import asyncio
import os
import time

import pytest

import e2e_helpers as H


def test_run_echo(run, base_sandbox):  # type: ignore[no-untyped-def]
    result = run(base_sandbox.commands.run("echo hello-e2e"))
    assert result.exit_code == 0
    assert result.stdout == "hello-e2e\n"
    assert result.stderr == ""
    assert result.success


def test_native_os_user_matches_standard_on_same_sandbox(run, base_sandbox):  # type: ignore[no-untyped-def]
    from agent_sandbox import AsyncSandbox

    async def scenario():  # type: ignore[no-untyped-def]
        standard = await AsyncSandbox.connect(
            base_sandbox.id,
            api_key=os.environ["ABX_SANDBOX_API_KEY"],
            api_url=os.environ.get("ABX_SANDBOX_BASE_URL"),
            domain=os.environ.get("ABX_SANDBOX_DOMAIN"),
        )
        before = await base_sandbox.commands.run("id -u")
        native_root, native_user, standard_root, standard_user = await asyncio.gather(
            base_sandbox.commands.run("id -u", user="root"),
            base_sandbox.commands.run("id -u", user="user"),
            standard.commands.run("id -u", user="root"),
            standard.commands.run("id -u", user="user"),
        )
        assert all(
            result.exit_code == 0
            for result in (before, native_root, native_user, standard_root, standard_user)
        )
        assert native_root.stdout.strip() == standard_root.stdout.strip() == "0"
        assert native_user.stdout.strip() == standard_user.stdout.strip() == "1000"
        reader = await base_sandbox.commands.start("id -u", user="root")
        chunks = await reader.collect()
        assert "".join(chunk.data for chunk in chunks).strip() == "0"
        after = await base_sandbox.commands.run("id -u")
        assert after.exit_code == 0 and after.stdout == before.stdout

    run(scenario())


def test_native_nonexistent_os_user_does_not_fall_back(run, base_sandbox):  # type: ignore[no-untyped-def]
    from agent_sandbox.models.errors import EnvdRpcError

    with pytest.raises(EnvdRpcError):
        run(base_sandbox.commands.run("id -u", user="abx_e2e_nonexistent_os_user"))


def test_run_reports_nonzero_exit_code_and_stderr(run, base_sandbox):  # type: ignore[no-untyped-def]
    result = run(base_sandbox.commands.run("sh -c 'echo oops >&2; exit 7'"))
    assert result.exit_code == 7
    assert result.stderr == "oops\n"
    assert not result.success


def test_run_with_cwd(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    result = run(base_sandbox.commands.run("pwd", cwd=d))
    assert result.stdout.strip() == d


def test_run_pipeline_is_wrapped_in_a_shell(run, base_sandbox):  # type: ignore[no-untyped-def]
    result = run(base_sandbox.commands.run("echo a-b-c | tr '-' '+'"))
    assert result.stdout.strip() == "a+b+c"


def test_run_shell_flag_expands_variables(run, base_sandbox):  # type: ignore[no-untyped-def]
    result = run(base_sandbox.commands.run("X=42; echo $((X+1))", shell=True))
    assert result.stdout.strip() == "43"


def test_unknown_executable_raises_envd_rpc_error(run, base_sandbox):  # type: ignore[no-untyped-def]
    from agent_sandbox.models.errors import EnvdRpcError

    with pytest.raises(EnvdRpcError) as err:
        run(base_sandbox.commands.run("e2e_no_such_binary_xyz"))
    assert "not found" in str(err.value)


def test_run_with_per_call_env(run, base_sandbox):  # type: ignore[no-untyped-def]
    result = run(
        base_sandbox.commands.run("printenv E2E_CALL_ENV", env={"E2E_CALL_ENV": "per-call"})
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == "per-call"


def test_stream_yields_chunks_in_order_then_exit(run, base_sandbox):  # type: ignore[no-untyped-def]
    async def _collect():  # type: ignore[no-untyped-def]
        out = []
        async for chunk in base_sandbox.commands.stream("sh -c 'echo first; sleep 1; echo second'"):
            out.append(chunk)
        return out

    chunks = run(_collect())
    text = "".join(c.data for c in chunks if c.type.value == "stdout")
    assert text.index("first") < text.index("second")
    assert chunks[-1].type.value == "exit" and chunks[-1].exit_code == 0


def test_command_timeout_stops_a_long_running_command(run, base_sandbox):  # type: ignore[no-untyped-def]
    from agent_sandbox.models.errors import CommandTimeoutError

    started = time.monotonic()
    with pytest.raises(CommandTimeoutError):
        run(base_sandbox.commands.run("sleep 60", timeout=3))
    assert time.monotonic() - started < 30


def test_timed_out_command_is_not_left_running(run, base_sandbox):  # type: ignore[no-untyped-def]
    from agent_sandbox.models.errors import CommandTimeoutError

    with pytest.raises(CommandTimeoutError):
        run(base_sandbox.commands.run("sleep 113", timeout=3))
    alive = run(base_sandbox.commands.run("sh -c 'ps -eo args | grep -c \"^sleep 113\" || true'"))
    assert alive.stdout.strip() == "0"


def test_command_timeout_raises_command_timeout_error(run, base_sandbox):  # type: ignore[no-untyped-def]
    from agent_sandbox.models.errors import CommandTimeoutError

    with pytest.raises(CommandTimeoutError):
        run(base_sandbox.commands.run("sleep 60", timeout=3))


async def _start_background(sandbox, cmd: str):  # type: ignore[no-untyped-def]
    """Start *cmd* and wait (eventual) until envd lists it; returns ``(task, pid)``.

    envd numbers processes itself (the pid is not an OS pid) and the sandbox is shared by the
    tests of this module, so the new process is the one whose pid was not listed before.
    """
    known = {p.pid for p in await sandbox.commands.list()}
    reader = await sandbox.commands.start(cmd, timeout=150)
    task = asyncio.ensure_future(reader.collect())
    for _ in range(30):
        fresh = [p for p in await sandbox.commands.list() if p.pid not in known]
        if fresh:
            return task, fresh[-1].pid
        await asyncio.sleep(1)
    task.cancel()
    raise AssertionError(f"{cmd!r} never appeared in commands.list()")


async def _ended_within(task, seconds: float):  # type: ignore[no-untyped-def]
    try:
        return await asyncio.wait_for(asyncio.shield(task), seconds)
    except asyncio.TimeoutError:
        return None


async def _force_kill(sandbox, pid, task) -> None:  # type: ignore[no-untyped-def]
    """Clean-up helper: SIGKILL through envd (``pid`` is envd's id, so ``kill -9 pid`` would not work)."""
    try:
        await sandbox.commands.send_signal(pid, 9)
        await asyncio.wait_for(task, 15)
    except Exception:  # noqa: BLE001
        task.cancel()


def test_background_process_is_listed_with_its_command(run, base_sandbox):  # type: ignore[no-untyped-def]
    async def _scenario():  # type: ignore[no-untyped-def]
        task, pid = await _start_background(base_sandbox, "sleep 111")
        procs = await base_sandbox.commands.list()
        await _force_kill(base_sandbox, pid, task)
        return pid, procs

    pid, procs = run(_scenario())
    assert any(p.pid == pid for p in procs)


@pytest.mark.parametrize("op", ["kill", "signal_term", "signal_kill"])
def test_kill_and_signal_terminate_a_process(run, base_sandbox, op):  # type: ignore[no-untyped-def]
    async def _scenario():  # type: ignore[no-untyped-def]
        task, pid = await _start_background(base_sandbox, "sleep 112")
        if op == "kill":
            await base_sandbox.commands.kill(pid)
        elif op == "signal_term":
            await base_sandbox.commands.send_signal(pid, 15)
        else:
            await base_sandbox.commands.send_signal(pid, 9)
        chunks = await _ended_within(task, 8)
        if chunks is None:
            await _force_kill(base_sandbox, pid, task)
        return chunks

    chunks = run(_scenario())
    assert chunks is not None and chunks[-1].type.value == "exit"


def test_send_input_reaches_stdin(run, base_sandbox):  # type: ignore[no-untyped-def]
    async def _scenario():  # type: ignore[no-untyped-def]
        task, pid = await _start_background(base_sandbox, "head -n 1")
        try:
            await base_sandbox.commands.send_input(pid, "typed-input\n")
            return await _ended_within(task, 8)
        finally:
            await _force_kill(base_sandbox, pid, task)

    chunks = run(_scenario())
    assert chunks is not None
    assert "typed-input" in "".join(c.data for c in chunks if c.type.value == "stdout")


def test_run_in_background_returns_a_stream_reader(run, base_sandbox):  # type: ignore[no-untyped-def]
    from agent_sandbox.transport.streaming import StreamReader

    reader = run(base_sandbox.commands.run("echo bg", background=True))
    assert isinstance(reader, StreamReader)
    chunks = run(reader.collect())
    assert "bg" in "".join(c.data for c in chunks)


def test_timeout_bounds_continuous_output_and_stops_owned_pid(run, base_sandbox, workdir):
    """Periodic stdout cannot turn a one-second execution limit into an idle timeout."""
    import shlex

    from agent_sandbox.models.errors import CommandTimeoutError

    directory = workdir(base_sandbox)
    pidfile = f"{directory}/continuous-timeout.pid"
    source = (
        f"import os,time; from pathlib import Path; Path({pidfile!r}).write_text(str(os.getpid())); "
        "[(print('tick',flush=True),time.sleep(0.2)) for _ in range(60)]"
    )
    began = time.monotonic()
    with pytest.raises(CommandTimeoutError):
        run(base_sandbox.commands.run("python -u -c " + shlex.quote(source), timeout=1))
    assert time.monotonic() - began < 8
    pid = int(run(base_sandbox.files.read(pidfile)))
    H.eventually(lambda: all(p.pid != pid for p in run(base_sandbox.commands.list())), timeout=5)
    assert (
        run(base_sandbox.commands.run("echo deadline-recovered")).stdout == "deadline-recovered\n"
    )
