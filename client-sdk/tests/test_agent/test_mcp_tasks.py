"""Real subprocess/task records with a local sandbox transport substitute."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_sandbox.agent import tasks
from agent_sandbox.agent.mcp import SandboxManager
from agent_sandbox.agent.tools import dispatch_tool

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Task runtime requires Linux process APIs"
)


@pytest.fixture
def local_sandbox(tmp_path, monkeypatch):
    source = tasks._RUNTIME.replace('Path("/tmp")', f"Path({str(tmp_path)!r})")
    monkeypatch.setattr(tasks, "_RUNTIME", source)

    async def run(command, **kwargs):
        proc = await asyncio.create_subprocess_exec(
            *shlex.split(command),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), 15)
        return SimpleNamespace(
            stdout=stdout.decode(), stderr=stderr.decode(), exit_code=proc.returncode
        )

    sandbox = SimpleNamespace(
        id="local-owned",
        commands=SimpleNamespace(run=run),
        close=AsyncMock(),
        kill=AsyncMock(),
        set_timeout=AsyncMock(),
    )
    monkeypatch.setattr(
        "agent_sandbox.api.sandbox.Sandbox.connect", AsyncMock(return_value=sandbox)
    )
    return sandbox


def owner(sandbox):
    manager = SandboxManager()
    manager._sandboxes[sandbox.id] = sandbox
    manager._default_sandbox = sandbox
    manager._lifetimes[sandbox.id] = 300
    return manager


async def terminal(handle, manager):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        result = await dispatch_tool("get_task", handle, manager)
        assert "error" not in result, result
        if result["state"] != "running":
            return result
        await asyncio.sleep(0.05)
    pytest.fail("task did not complete")


async def test_reconnect_completed_logs_nonzero_and_pagination(local_sandbox):
    manager = owner(local_sandbox)
    start = await dispatch_tool(
        "start_task",
        {
            "command": "printf FIRST; sleep .3; printf LAST; printf ERR >&2; exit 7",
            "timeout": 10,
        },
        manager,
    )
    assert start["retained_until_sandbox_ttl"] is True
    handle = {k: start[k] for k in ("sandbox_id", "task_id")}
    await manager.shutdown()
    local_sandbox.kill.assert_not_awaited()
    local_sandbox.close.assert_awaited_once()
    fresh = SandboxManager()
    result = await terminal(handle, fresh)
    assert result["state"] == "failed" and result["exit_code"] == 7
    assert result["stdout"] == "FIRSTLAST" and result["stderr"] == "ERR"
    page = await dispatch_tool("get_task", {**handle, "limit": 5}, fresh)
    assert page["stdout"] == "FIRST" and page["stdout_offset"] == 5
    page = await dispatch_tool("get_task", {**handle, "stdout_offset": 5}, fresh)
    assert page["stdout"] == "LAST" and page["stdout_offset"] == 9
    assert not fresh._sandboxes and fresh._default_sandbox is None
    local_sandbox.set_timeout.assert_not_awaited()


async def test_sync_shutdown_still_kills(local_sandbox):
    manager = owner(local_sandbox)
    await manager.shutdown()
    local_sandbox.kill.assert_awaited_once()


@pytest.mark.parametrize(
    "params",
    [
        {"command": "echo ok", "timeout": True},
        {"command": "echo ok", "timeout": 0},
        {"command": "echo ok", "timeout": 3601},
        {"command": "echo ok", "pid": 123},
        {"command": ""},
    ],
)
async def test_start_validation_without_remote(local_sandbox, params):
    local_sandbox.commands.run = AsyncMock()
    result = await dispatch_tool("start_task", params, owner(local_sandbox))
    assert "error" in result
    local_sandbox.commands.run.assert_not_awaited()


@pytest.mark.parametrize("value", ["../etc/passwd", "a" * 31, "A" * 32, "0" * 33, 123])
async def test_task_handle_rejects_paths_and_pids(local_sandbox, value):
    from agent_sandbox.api.sandbox import Sandbox

    result = await dispatch_tool(
        "cancel_task",
        {
            "sandbox_id": "external",
            "task_id": value,
        },
        SandboxManager(),
    )
    assert "error" in result
    Sandbox.connect.assert_not_awaited()


def alive(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


@pytest.mark.parametrize("mode", ["success", "nonzero", "cancel", "timeout"])
async def test_owned_descendants_cleaned_after_leader_exit(local_sandbox, tmp_path, mode):
    # The child ignores TERM and redirects both pipes; pipe EOF cannot prove cleanup.
    marker = tmp_path / "child-pid"
    code = (
        "import os,signal,subprocess,time; "
        'child=subprocess.Popen(["python3","-c",'
        '"import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"],'
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        f"open({str(marker)!r},'w').write(str(child.pid)); "
        "time.sleep(.15); "
        + (
            "time.sleep(60)"
            if mode in {"cancel", "timeout"}
            else "raise SystemExit(7)"
            if mode == "nonzero"
            else "raise SystemExit(0)"
        )
    )
    manager = owner(local_sandbox)
    started = await dispatch_tool(
        "start_task",
        {
            "command": "exec python3 -c " + shlex.quote(code),
            "timeout": 1 if mode == "timeout" else 30,
        },
        manager,
    )
    assert "error" not in started, started
    handle = {k: started[k] for k in ("sandbox_id", "task_id")}
    deadline = time.monotonic() + 5
    while not marker.exists() and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    pid = int(marker.read_text())
    try:
        if mode == "cancel":
            result = await dispatch_tool("cancel_task", handle, manager)
            assert result["state"] == "cancelled"
        else:
            result = await terminal(handle, manager)
            assert (
                result["state"]
                == {"success": "succeeded", "nonzero": "failed", "timeout": "timed_out"}[mode]
            )
        assert not alive(pid)
        # A repeated cancellation of a terminal handle never targets a new PID.
        repeat = await dispatch_tool("cancel_task", handle, SandboxManager())
        assert repeat["state"] == result["state"]
    finally:
        if alive(pid):
            os.kill(pid, 9)


async def test_bounded_logs_are_drained_without_deadlock(local_sandbox):
    manager = owner(local_sandbox)
    source = "import sys; sys.stdout.write('x'*2000000); sys.stderr.write('e'*2000000)"
    start = await dispatch_tool(
        "start_task",
        {
            "command": "python3 -c " + shlex.quote(source),
        },
        manager,
    )
    result = await terminal({k: start[k] for k in ("sandbox_id", "task_id")}, manager)
    assert result["state"] == "succeeded"
    assert result["stdout_size"] == result["stderr_size"] == 1048576
    assert result["stdout_truncated"] and result["stderr_truncated"]
    assert len(result["stdout"]) <= 16384


async def test_external_start_not_adopted_and_private_errors(local_sandbox):
    manager = SandboxManager(api_key="placeholder-test-secret")
    result = await dispatch_tool(
        "start_task",
        {
            "sandbox_id": local_sandbox.id,
            "command": "echo hello",
        },
        manager,
    )
    assert "task_id" in result and not manager._sandboxes
    await manager.shutdown()
    local_sandbox.kill.assert_not_awaited()
    local_sandbox.commands.run = AsyncMock(side_effect=RuntimeError("placeholder-test-secret"))
    failed = await dispatch_tool(
        "get_task",
        {
            "sandbox_id": local_sandbox.id,
            "task_id": "a" * 32,
        },
        manager,
    )
    assert "error" in failed and "placeholder-test-secret" not in json.dumps(failed)


async def test_remote_environment_secret_split_across_chunks(local_sandbox, monkeypatch):
    monkeypatch.setenv("ABX_TEST_SECRET", "test-secret-value-to-mask")
    start = await dispatch_tool(
        "start_task",
        {
            "command": "python3 -u -c "
            + shlex.quote(
                "import os,time; v=os.environ['ABX_TEST_SECRET']; print(v[:8],end='',flush=True); "
                "time.sleep(.2); print(v[8:],flush=True)"
            ),
        },
        owner(local_sandbox),
    )
    handle = {k: start[k] for k in ("sandbox_id", "task_id")}
    result = await terminal(handle, SandboxManager())
    assert result["stdout"] == "[REDACTED]\n"


async def test_progress_logs_flush_before_completion(local_sandbox):
    started = await dispatch_tool(
        "start_task",
        {
            "command": "printf PROGRESS; sleep 1; printf DONE",
        },
        owner(local_sandbox),
    )
    handle = {k: started[k] for k in ("sandbox_id", "task_id")}
    deadline = time.monotonic() + 0.8
    seen = None
    while time.monotonic() < deadline:
        seen = await dispatch_tool("get_task", handle, SandboxManager())
        if seen.get("stdout") == "PROGRESS":
            break
        await asyncio.sleep(0.02)
    assert seen["state"] == "running" and seen["stdout"] == "PROGRESS"
    assert (await terminal(handle, SandboxManager()))["stdout"] == "PROGRESSDONE"


async def test_ambiguous_submission_returns_recoverable_handle(local_sandbox):
    local_sandbox.commands.run = AsyncMock(side_effect=TimeoutError("sensitive transport text"))
    manager = owner(local_sandbox)
    result = await dispatch_tool("start_task", {"command": "sleep 1"}, manager)
    assert result["state"] == "unknown" and len(result["task_id"]) == 32
    assert result["sandbox_id"] == local_sandbox.id
    assert "sensitive transport text" not in json.dumps(result)
    await manager.shutdown()
    local_sandbox.kill.assert_not_awaited()
    local_sandbox.close.assert_awaited_once()


@pytest.mark.parametrize("command", ["'" * 65536, "汉" * 40000], ids=["quotes", "unicode"])
async def test_expanded_command_limit_rejected_before_remote(local_sandbox, command):
    from agent_sandbox.api.sandbox import Sandbox

    local_sandbox.commands.run = AsyncMock()
    result = await dispatch_tool(
        "start_task",
        {
            "sandbox_id": "external",
            "command": command,
        },
        SandboxManager(),
    )
    assert "96 KiB" in result["error"]
    Sandbox.connect.assert_not_awaited()
    local_sandbox.commands.run.assert_not_awaited()


async def test_stdio_dispatch_and_http_delete_reconnect(local_sandbox):
    import httpx

    from agent_sandbox.agent.mcp import SandboxMCPServer
    from agent_sandbox.agent.mcp_http import create_mcp_app

    server = SandboxMCPServer()
    server._manager = owner(local_sandbox)
    response = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "start_task", "arguments": {"command": "sleep .2; echo TRANSPORT"}},
        }
    )
    handle = json.loads(response["result"]["content"][0]["text"])
    handle = {k: handle[k] for k in ("sandbox_id", "task_id")}
    await server.shutdown()
    assert not server._manager._retained_task_sandboxes
    local_sandbox.kill.assert_not_awaited()
    app = create_mcp_app(auth_token="placeholder-test-token")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        initialized = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            headers={"Authorization": "Bearer placeholder-test-token"},
        )
        session_id = initialized.headers["Mcp-Session-Id"]
        headers = {"Authorization": "Bearer placeholder-test-token", "Mcp-Session-Id": session_id}
        # A new HTTP session reads work started through the STDIO dispatcher.
        result = await terminal(handle, SandboxManager())
        assert result["stdout"] == "TRANSPORT\n"
        response = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_task", "arguments": handle},
            },
            headers=headers,
        )
        assert response.status_code == 200
        payload = json.loads(response.json()["result"]["content"][0]["text"])
        assert payload["state"] == "succeeded" and payload["stdout"] == "TRANSPORT\n"
        deleted = await client.delete("/mcp", headers=headers)
        assert deleted.status_code == 200
        local_sandbox.kill.assert_not_awaited()


async def test_late_submission_cannot_restore_shutdown_ownership(local_sandbox, monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed(sandbox, request, manager):
        entered.set()
        await release.wait()
        return {"task_id": request["task_id"], "state": "running"}

    monkeypatch.setattr(tasks, "_operate", delayed)
    manager = owner(local_sandbox)
    pending = asyncio.create_task(dispatch_tool("start_task", {"command": "echo ok"}, manager))
    await entered.wait()
    await manager.shutdown()
    release.set()
    result = await pending
    assert result["retained_until_sandbox_ttl"] is False
    assert not manager._retained_task_sandboxes and not manager._sandboxes
    local_sandbox.kill.assert_awaited_once()


async def test_saved_log_symlink_is_refused(local_sandbox, tmp_path):
    started = await dispatch_tool("start_task", {"command": "echo task"}, owner(local_sandbox))
    handle = {k: started[k] for k in ("sandbox_id", "task_id")}
    await terminal(handle, SandboxManager())
    outside = tmp_path / "outside.txt"
    outside.write_text("PRIVATE_OUTSIDE")
    log = tmp_path / f"abx-mcp-tasks-{os.getuid()}" / handle["task_id"] / "stdout.log"
    log.unlink()
    log.symlink_to(outside)
    result = await dispatch_tool("get_task", handle, SandboxManager())
    assert "error" in result and "PRIVATE_OUTSIDE" not in json.dumps(result)


async def test_qualified_handle_retains_existing_canonical_owner(local_sandbox):
    manager = owner(local_sandbox)
    started = await dispatch_tool(
        "start_task",
        {
            "sandbox_id": "alicloud-express:" + local_sandbox.id,
            "command": "echo qualified",
        },
        manager,
    )
    assert started["retained_until_sandbox_ttl"] is True
    await manager.shutdown()
    local_sandbox.kill.assert_not_awaited()
    handle = {k: started[k] for k in ("sandbox_id", "task_id")}
    assert (await terminal(handle, SandboxManager()))["stdout"] == "qualified\n"
