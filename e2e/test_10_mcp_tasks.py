"""Real Express background tasks survive manager disconnect, not sandbox expiry."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time

import e2e_helpers as helpers


def test_mcp_background_reconnect_complete_and_cancel(run, tracker):  # type: ignore[no-untyped-def]
    from agent_sandbox import Sandbox
    from agent_sandbox.agent.mcp import SandboxManager
    from agent_sandbox.agent.tools import dispatch_tool

    async def wait_terminal(handle, manager):  # type: ignore[no-untyped-def]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            result = await dispatch_tool("get_task", handle, manager)
            assert "error" not in result
            if result["state"] != "running":
                return result
            await asyncio.sleep(0.2)
        raise AssertionError("task completion deadline exceeded")

    async def scenario() -> None:
        owner = SandboxManager(template=helpers.OFFICIAL_BASE)
        observer = SandboxManager()
        sid = None
        try:
            created = await dispatch_tool("create_sandbox", {"timeout": 300}, owner)
            assert "error" not in created
            sid = created["sandbox_id"]
            tracker.sandbox(sid)
            started = await dispatch_tool(
                "start_task",
                {
                    "command": "printf BEFORE; sleep 2; printf AFTER; printf ERR >&2; exit 7",
                    "timeout": 30,
                },
                owner,
            )
            assert "error" not in started
            assert started["retained_until_sandbox_ttl"] is True
            handle = {k: started[k] for k in ("sandbox_id", "task_id")}
            await owner.shutdown()
            # A separate Python process has no submitter manager/cache objects.
            reconnect = """
import asyncio,json,logging,os,sys,uuid
os.environ['ABX_ENGINE_SOCKET']='/tmp/mcp-task-reconnect-'+uuid.uuid4().hex+'.sock'
logging.disable(logging.CRITICAL)
from agent_sandbox.agent.mcp import SandboxManager
from agent_sandbox.agent.tools import dispatch_tool
async def main():
    manager=SandboxManager()
    for _ in range(100):
        result=await dispatch_tool('get_task',json.loads(sys.argv[1]),manager)
        if result.get('state')!='running':
            print(json.dumps(result));return
        await asyncio.sleep(.2)
    raise RuntimeError('reconnect task deadline exceeded')
asyncio.run(main())
"""
            child_env = os.environ.copy()
            child_env["PYTHONPATH"] = os.pathsep.join(
                [
                    str(helpers.REPO_ROOT / "client-sdk" / "src"),
                    str(helpers.REPO_ROOT / "server-sdk" / "src"),
                    child_env.get("PYTHONPATH", ""),
                ]
            )
            raw = await asyncio.to_thread(
                subprocess.check_output,
                [sys.executable, "-c", reconnect, json.dumps(handle)],
                text=True,
                timeout=40,
                env=child_env,
            )
            replaced = json.loads(raw)
            assert replaced["state"] == "failed" and replaced["exit_code"] == 7
            assert replaced["stdout"] == "BEFOREAFTER" and replaced["stderr"] == "ERR"
            result = await wait_terminal(handle, observer)
            assert result["state"] == "failed" and result["exit_code"] == 7
            assert result["stdout"] == "BEFOREAFTER" and result["stderr"] == "ERR"
            page = await dispatch_tool("get_task", {**handle, "limit": 6}, observer)
            assert page["stdout"] == "BEFORE" and page["stdout_offset"] == 6
            page = await dispatch_tool("get_task", {**handle, "stdout_offset": 6}, observer)
            assert page["stdout"] == "AFTER"
            await observer.shutdown()
            fresh = SandboxManager()
            cancelled = await dispatch_tool(
                "start_task",
                {
                    "sandbox_id": sid,
                    "command": "sleep 60",
                    "timeout": 90,
                },
                fresh,
            )
            assert "error" not in cancelled
            cancel_handle = {k: cancelled[k] for k in ("sandbox_id", "task_id")}
            await fresh.shutdown()
            status = await dispatch_tool("cancel_task", cancel_handle, SandboxManager())
            assert status["state"] == "cancelled"
            repeat = await dispatch_tool("get_task", cancel_handle, SandboxManager())
            assert repeat["state"] == "cancelled"
            assert not observer._sandboxes and not fresh._sandboxes
        finally:
            if sid:
                await Sandbox.kill_by_id(sid)
            await owner.shutdown()
            await observer.shutdown()

    run(scenario())
