"""Verify MCP HTTP against one owned Express sandbox, then confirm cleanup.

Run with authorized ABX_SANDBOX_API_KEY / optional endpoint settings in the
process environment. Creates only one base sandbox with a120-second lifetime.
Outputs sanitized assertion results; never prints credentials or sandbox IDs.
"""

import asyncio
import json
import os
import pathlib
import secrets
import tempfile

import httpx
import uvicorn

from agent_sandbox.agent.mcp_http import create_mcp_app
from agent_sandbox.api.sandbox import Sandbox


async def main():
    results = []
    session = None
    owned = None
    failed = False
    rpc_id = 0
    options = {
        k: os.environ.get(v)
        for k, v in {
            "sandbox_api_key": "ABX_SANDBOX_API_KEY",
            "sandbox_base_url": "ABX_SANDBOX_BASE_URL",
        }.items()
    }
    app = create_mcp_app(
        **options,
        sandbox_domain=os.environ.get("ABX_SANDBOX_DOMAIN"),
        auth_token=(token := secrets.token_hex(32)),
        template="base",
    )
    with tempfile.TemporaryDirectory(prefix="abx-mcp-python-real-") as directory:
        socket = str(pathlib.Path(directory) / "mcp.sock")
        server = uvicorn.Server(
            uvicorn.Config(app, uds=socket, log_level="critical", lifespan="on")
        )
        task = asyncio.create_task(server.serve())
        try:

            async def wait_started():
                while not server.started:
                    if task.done():
                        await task
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_started(), 15)
            async with httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(uds=socket),
                base_url="http://localhost",
                timeout=90,
            ) as client:

                async def request(method, body=None, auth=True, version="2025-06-18"):
                    headers = {"MCP-Protocol-Version": version}
                    if auth:
                        headers["Authorization"] = "Bearer " + token
                    if session:
                        headers["Mcp-Session-Id"] = session
                    return await client.request(method, "/mcp", headers=headers, json=body)

                async def rpc(method, params):
                    nonlocal rpc_id
                    rpc_id += 1
                    return await request(
                        "POST", {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}
                    )

                def record(step, ok):
                    results.append({"step": step, "passed": bool(ok)})
                    if not ok:
                        raise AssertionError(step)

                def value(response):
                    data = response.json()
                    result = data.get("result", {})
                    if response.status_code != 200 or data.get("error") or result.get("isError"):
                        raise AssertionError("tool failed")
                    return json.loads(
                        next(item["text"] for item in result["content"] if item["type"] == "text")
                    )

                denied = await request(
                    "POST",
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18"},
                    },
                    False,
                )
                record("unauthenticated initialize refused", denied.status_code == 401)
                init = await rpc(
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "clientInfo": {"name": "owned-verification", "version": "1"},
                        "capabilities": {},
                    },
                )
                session = init.headers.get("mcp-session-id")
                record("authenticated HTTP initialize", init.status_code == 200 and session)
                tools = (await rpc("tools/list", {})).json()["result"]["tools"]
                record("discover tools", any(t["name"] == "create_sandbox" for t in tools))
                created = value(
                    await rpc(
                        "tools/call",
                        {
                            "name": "create_sandbox",
                            "arguments": {"template": "base", "timeout": 120},
                        },
                    )
                )
                owned = created["sandbox_id"]
                record("create real Express Sandbox", bool(owned))
                command = value(
                    await rpc(
                        "tools/call",
                        {
                            "name": "run_command",
                            "arguments": {
                                "command": "printf python-mcp-real-ok",
                                "sandbox_id": owned,
                                "timeout": 15,
                            },
                        },
                    )
                )
                record(
                    "execute through same HTTP session", "python-mcp-real-ok" in json.dumps(command)
                )
                removed = await request("DELETE")
                record(
                    "HTTP session deletion",
                    removed.status_code == 200
                    and removed.json().get("status") == "session_terminated",
                )
                absent = False
                try:
                    await Sandbox.get_info_by_id(owned, **options)
                except Exception as error:
                    absent = type(error).__name__ == "SandboxNotFoundError"
                record("independent native absence", absent)
                gone = await rpc("ping", {})
                record("deleted MCP session rejected", gone.status_code == 404)
        except Exception as error:
            failed = True
            results.append({"step": "failure", "type": type(error).__name__})
        finally:
            if owned:
                try:
                    await Sandbox.get_info_by_id(owned, **options)
                    await Sandbox.kill_by_id(owned, **options)
                    failed = True
                    results.append({"step": "explicit owned cleanup needed", "passed": False})
                except Exception as error:
                    if type(error).__name__ != "SandboxNotFoundError":
                        failed = True
                        results.append({"step": "final absence unresolved", "passed": False})
            server.should_exit = True
            try:
                await asyncio.wait_for(task, 30)
            except Exception:
                failed = True
                results.append({"step": "server shutdown unresolved", "passed": False})
    print(json.dumps(results, indent=2))
    return 1 if failed else 0


raise SystemExit(asyncio.run(main()))
