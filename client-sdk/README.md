# easy-sandbox-client

Async Python **client SDK** for the Alibaba Cloud FC Agent Sandbox service. It is
E2B-protocol compatible and adds Alibaba Cloud extensions (OSS, VPC, custom domains).

This package is the `easy_sandbox` import namespace *except* `easy_sandbox.server`, which is
the container-side runtime shipped separately as
[`easy-sandbox-server`](../server-sdk/README.md). The command-line tool (`ebx`) is a separate
Node.js project that lives in the [`cli`](../../cli) repository.

## Install

```bash
pip install easy-sandbox-client                 # core SDK
pip install "easy-sandbox-client[alicloud]"     # + template API (Alibaba Cloud FC)
pip install "easy-sandbox-client[all]"          # everything (mcp, yaml, fast json, sessions, ...)
pip install "easy-sandbox-client[server]"       # + easy-sandbox-server (for the @sandbox decorator inside templates)
```

## Quick start

```python
import asyncio
from easy_sandbox import Sandbox

async def main():
    async with await Sandbox.create(template="python-base") as sandbox:
        proc = await sandbox.run("echo 'Hello from sandbox!'")      # bare shell
        print(proc.stdout, proc.exit_code)

        result = await sandbox.run_code("print(2 ** 10)")            # code interpreter
        print(result.text)

        cmd = await sandbox.custom("hello", name="Alice")            # named command
        print(cmd.value, cmd.source)

        await sandbox.files.write("/tmp/data.txt", "content")
        print(await sandbox.files.read("/tmp/data.txt"))

asyncio.run(main())
```

## Layout

| Package | Layer |
|---------|-------|
| `easy_sandbox.transport` | L1 — HTTP/2, WebSocket, API key / AK-SK auth, config loading |
| `easy_sandbox.protocol` | L2 — E2B-compatible protocol (sandbox, process, filesystem, terminal, port) |
| `easy_sandbox.extensions` | L3 — OSS, VPC, custom domain |
| `easy_sandbox.api` | L4 — `Sandbox`, files, commands, code, templates, deploy |
| `easy_sandbox.declarative` | L5 — `@sandbox` decorator, `sandbox.yaml` |
| `easy_sandbox.agent` | L6 — built-in agents, tool schemas, MCP stdio/HTTP servers |

Run the MCP stdio server directly with `python -m easy_sandbox.agent.mcp`
(reads `E2B_API_KEY`, `E2B_API_URL`, `E2B_DOMAIN`, `SANDBOX_TEMPLATE`).

## Develop

```bash
# from python-sdk/
pip install -e ./server-sdk -e "./client-sdk[dev]"
cd client-sdk && pytest -m "not integration" && ruff check src tests && mypy src/easy_sandbox
```

Licensed under Apache-2.0.
