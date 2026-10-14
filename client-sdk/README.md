# agent-sandbox

**Client SDK.** This package runs on your machine: create a sandbox, use it, and kill it. The HTTP service inside the image is [`agent-sandbox-server`](../server-sdk/README.md). Guide: [Client SDK](../docs/en/guide/client-sdk.md).

Template build and deploy are done by the CLI (`abx template build|deploy`). Method names are
E2B-shaped to ease migration; this is not a drop-in replacement (see the "Migrate from E2B" guide).

This package is the `agent_sandbox` import namespace *except* `agent_sandbox.server`, which is
the container-side runtime shipped separately as
[`agent-sandbox-server`](../server-sdk/README.md) (a hard dependency pinned to the same version,
so `pip install agent-sandbox` still provides `agent_sandbox.server`; the `[server]` extra is a
no-op alias kept for compatibility).

The command-line tool (`abx`) is a separate Node.js project that lives in the [`cli`](https://github.com/alibaba-agent-sandbox/agent-sandbox) repository.

## Install

```bash
pip install agent-sandbox                 # core SDK (pulls in agent-sandbox-server of the same version)
pip install "agent-sandbox[all]"          # everything (mcp, yaml, fast json, sessions, ...)
```

## Quick start

```python
import asyncio
from agent_sandbox import Sandbox


async def main():
    async with await Sandbox.create(template="python-base") as sandbox:
        proc = await sandbox.commands.run("echo 'Hello from sandbox!'")  # bare shell
        print(proc.stdout, proc.exit_code)

        result = await sandbox.run_code("print(2 ** 10)")  # code interpreter
        print(result.text)

        # "hello" is a command registered in the sandbox server
        greeting = await sandbox.run("hello", name="Alice")
        print(greeting)

        await sandbox.files.write("/tmp/data.txt", "content")
        print(await sandbox.files.read("/tmp/data.txt"))


asyncio.run(main())
```

## Layout

| Package | Layer |
|---------|-------|
| `agent_sandbox.transport` | L1 — HTTP/2, WebSocket, API key / AK-SK auth, config loading |
| `agent_sandbox.protocol` | L2 — envd protocol (sandbox, process, filesystem, terminal, port) |
| `agent_sandbox.api` | L3 — `Sandbox`, files, commands, code, named commands, server client |
| `agent_sandbox.declarative` | L4 — `@sandbox` decorator, `sandbox.yaml` |
| `agent_sandbox.agent` | L5 — tool schemas, MCP stdio/HTTP servers |

Run the MCP stdio server directly with `python -m agent_sandbox.agent.mcp`
(reads `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL`, `ABX_SANDBOX_DOMAIN`, `ABX_DEFAULT_TEMPLATE`).

## Develop

```bash
# from python-sdk/
pip install -e ./server-sdk -e "./client-sdk[dev]"
cd client-sdk && pytest -m "not integration" && ruff check src tests && mypy src/agent_sandbox
```

Licensed under Apache-2.0.
