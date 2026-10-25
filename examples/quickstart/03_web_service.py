"""Start a Node.js HTTP service and call it through the sandbox's public URL."""

import asyncio
import contextlib
import json

import httpx

from agent_sandbox import ProviderSandbox

APP = r"""
const http = require('node:http');
http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  res.setHeader('content-type', 'application/json');
  if (url.pathname === '/health') res.end(JSON.stringify({status: 'ok'}));
  else if (url.pathname === '/api/echo') {
    res.end(JSON.stringify({query: Object.fromEntries(url.searchParams)}));
  }
  else res.end(JSON.stringify({message: 'Hello from Sandbox!', node_version: process.version}));
}).listen(3000, '0.0.0.0');
"""


async def main() -> None:
    async with await ProviderSandbox.create(template="base", timeout=300) as sandbox:
        await sandbox.files.write("/tmp/example-server.js", APP)
        reader = await sandbox.commands.start("node /tmp/example-server.js", timeout=240)

        async def drain() -> None:
            async for _ in reader:
                pass

        task = asyncio.create_task(drain())
        try:
            for _ in range(40):
                ready = await sandbox.commands.run(
                    "curl -fsS http://127.0.0.1:3000/health", timeout=5
                )
                if ready.exit_code == 0:
                    assert json.loads(ready.stdout) == {"status": "ok"}
                    break
                await asyncio.sleep(0.25)
            else:
                raise RuntimeError("The Node.js service did not become ready")

            # Gateway credentials remain in request headers, never in printed URLs/logs.
            origin = sandbox.network.get_url(3000)
            async with httpx.AsyncClient(
                headers=sandbox.network.get_access_headers(), timeout=30
            ) as client:
                response = await client.get(origin + "/")
                response.raise_for_status()
                assert response.json()["message"] == "Hello from Sandbox!"
                response = await client.get(origin + "/health")
                response.raise_for_status()
                assert response.json() == {"status": "ok"}
                response = await client.get(
                    origin + "/api/echo", params={"foo": "bar", "lang": "zh"}
                )
                response.raise_for_status()
                assert response.json() == {"query": {"foo": "bar", "lang": "zh"}}
            print("PASS: public HTTP greeting, health and query echo")
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    print("Sandbox destroyed")


if __name__ == "__main__":
    asyncio.run(main())
