# agent-sandbox-client

Provider extensions use [explicit template workflows](../docs/en/guide/template-workflows.md) ([中文](../docs/zh/guide/template-workflows.md)); application HTTP, stateless execution and context operations are independent.

For the current version, use the [paired source installation guide](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/install-python.md); source references below keep client and server versions matched.

**Client SDK.** The product is Agent Sandbox. The import path is `agent_sandbox`. This package runs on your machine: create a sandbox, use it, and kill it. The HTTP service inside the image is [`agent-sandbox-server`](../server-sdk/README.md). Guide: [Client SDK](../docs/en/guide/client-sdk.md).

Template build and deploy are done by the CLI (`abx template build|deploy`). Method names are
The standard root Sandbox/AsyncSandbox and code_interpreter APIs follow Alibaba-supported E2B behavior: [migration guide](../docs/en/guide/migrate-from-e2b.md) ([中文](../docs/zh/guide/migrate-from-e2b.md)). Provider/server/declarative extensions use the explicit ProviderSandbox entry.

This package is the `agent_sandbox` import namespace *except* `agent_sandbox.server`, which is
the container-side runtime shipped separately as
[`agent-sandbox-server`](../server-sdk/README.md) (a hard dependency pinned to the same version,
so [paired source installation guide](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/install-python.md) still provides `agent_sandbox.server`).

The command-line tool (`abx`) is a separate Node.js project that lives in the [`cli`](https://github.com/alibaba-agent-sandbox/agent-sandbox) repository.

## Install

```bash
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=client-sdk"
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client[all] @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=client-sdk"
```

Do not run `pip install agent-sandbox`. That name on PyPI is an unrelated project.

## Quick start

```python
import asyncio
from agent_sandbox import ProviderSandbox as Sandbox


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

Provider management operations use `agent_sandbox.providers.commands`; see the
[English guide](../docs/en/guide/provider-commands.md) and
[中文指南](../docs/zh/guide/provider-commands.md). Writes require explicit confirmation,
and command POST requests are never automatically replayed.

## Layout

| Package | Layer |
|---------|-------|
| `agent_sandbox.transport` | L1 — HTTP/2, WebSocket, API key / AK-SK auth, config loading |
| `agent_sandbox.protocol` | L2 — envd protocol (sandbox, process, filesystem, terminal, port) |
| `agent_sandbox.api` | L3 — `Sandbox`, files, commands, code, named commands, server client |
| `agent_sandbox.declarative` | L4 — `@sandbox` decorator, `sandbox.yaml` |
| `agent_sandbox.agent` | L5 — tool schemas, MCP stdio/HTTP servers |

Run the MCP stdio server directly with `python -m agent_sandbox.agent.mcp`
(reads `E2B_API_KEY`, `E2B_API_URL`, `E2B_DOMAIN`, `ABX_DEFAULT_TEMPLATE`).

Named-command string-array arguments (`list[str]`) preserve native JSON values. See the [server API guide](../docs/en/guide/template-server-api.md#string-array-command-arguments).

## Develop

```bash
# from python-sdk/
pip install -e ./server-sdk -e "./client-sdk[dev]"
cd client-sdk && pytest -m "not integration" && ruff check src tests && mypy src/agent_sandbox
```

Licensed under Apache-2.0.
