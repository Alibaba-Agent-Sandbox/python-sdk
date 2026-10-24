# agent-sandbox-client

Provider extensions use [explicit template workflows](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/template-workflows.md) ([中文](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/zh/guide/template-workflows.md)); application HTTP, stateless execution and context operations are independent.

Install the current alpha with `--pre`; use the [installation guide](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/install-python.md) for a pinned version and environment setup.

**Client SDK.** The product is Agent Sandbox. The import path is `agent_sandbox`. This package runs on your machine: create a sandbox, use it, and kill it. The HTTP service inside the image is [`agent-sandbox-server`](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/server-sdk/README.md). Guide: [Client SDK](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/client-sdk.md).

Template build and deploy are done by the CLI (`abx template build|deploy`).
The standard root Sandbox/AsyncSandbox and code_interpreter APIs follow Alibaba-supported E2B behavior: [migration guide](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/migrate-from-e2b.md) ([中文](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/zh/guide/migrate-from-e2b.md)). Provider/server/declarative extensions use the explicit ProviderSandbox entry.

This package is the `agent_sandbox` import namespace *except* `agent_sandbox.server`, which is
the container-side runtime shipped separately as
[`agent-sandbox-server`](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/server-sdk/README.md) (a hard dependency pinned to the same version,
so installing the published client also installs the matching server).

The command-line tool (`abx`) is a separate Node.js project that lives in the [`cli`](https://github.com/alibaba-agent-sandbox/agent-sandbox) repository.

## Install

```bash
python -m pip install --upgrade --pre agent-sandbox-client
# Optional extras:
python -m pip install --upgrade --pre 'agent-sandbox-client[all]'
python -m pip check
```

Do not run `pip install agent-sandbox`. That name on PyPI is an unrelated project.

## Quick start

Configure the Express API key before this example. It uses standard command and file APIs; provider-specific interpreters and registered server commands have separate requirements.

```python
import asyncio
from agent_sandbox import AsyncSandbox


async def main():
    sandbox = await AsyncSandbox.create(template="base")
    try:
        result = await sandbox.commands.run("echo hello")
        print(result.stdout)
        await sandbox.files.write("/tmp/data.txt", "content")
        print(await sandbox.files.read("/tmp/data.txt"))
    finally:
        await sandbox.kill()


asyncio.run(main())
```

Provider management operations use `agent_sandbox.providers.commands`; see the
[English guide](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/provider-commands.md) and
[中文指南](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/zh/guide/provider-commands.md). Writes require explicit confirmation,
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
(reads `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL`, `ABX_SANDBOX_DOMAIN` and `ABX_DEFAULT_TEMPLATE`).

Named-command string-array arguments (`list[str]`) preserve native JSON values. See the [server API guide](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/template-server-api.md#string-array-command-arguments).

## Develop

```bash
# from python-sdk/
pip install -e ./server-sdk -e "./client-sdk[dev]"
cd client-sdk && pytest -m "not integration" && ruff check src tests && mypy src/agent_sandbox
```

Licensed under Apache-2.0.
