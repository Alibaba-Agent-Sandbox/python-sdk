# Client SDK

For current SDK installation, use the [installation guide](install-python.md).

The Client SDK runs on **your machine**. It creates a sandbox, connects to one that already exists, and then runs commands, reads and writes files, and calls the code interpreter. The package is `agent-sandbox-client`. Import `agent_sandbox`.

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client==0.4.0a3'
python -m pip check
```

Do not run `pip install agent-sandbox`. That name on PyPI is an unrelated project.

```python
from agent_sandbox import ProviderSandbox as Sandbox

async with await Sandbox.create(template="base") as sandbox:
    result = await sandbox.commands.run("echo hello")
    print(result.stdout)
```

The HTTP service inside the sandbox image is not written with this package. That process is the [Server SDK](server-sdk.md) (`agent-sandbox-server`). The Client SDK reaches it through envd and that service's HTTP API.

## Start here

| Guide | What it covers |
|------|----------------|
| [Getting Started](getting-started.md) | Install, configure, create, run, destroy |
| [SDK Usage](sdk-usage.md) | `commands`, `files`, `run_code`, named commands |
| [Authentication](authentication.md) | API key and AK/SK |
| [Declarative usage](declarative-usage.md) | `@sandbox` runs a function inside a sandbox |
| [Cloud end-to-end practice](cloud-examples.md) | Run the examples on the default provider |
| [Environment variables](environment-variables.md) | Inject at create, and how the sandbox reads them |
| [Session persistence](session-persistence.md) | Connect again by id after the process exits |
| [Providers](providers.md) | Switch the sandbox backend |
| [Migrate from E2B](migrate-from-e2b.md) | Where the method names match, and where they do not |
| [MCP integration](mcp-integration.md) | Hand sandbox operations to an IDE agent |
| [Command and SDK map](command-map.md) | Commands next to E2B and OpenSandbox |
| [Comparison](comparison.md) | How this sits next to E2B, Modal, and Docker Sandbox |
| [Troubleshooting](troubleshooting.md) | Create, auth, file, and command failures |

Reference: [API reference](../reference/api-reference.md), [Configuration](../reference/configuration.md), [Error codes](../reference/error-codes.md).

## Examples

These scripts run on your machine. See the [example index](../../../examples/README.md#client-sdk-examples):

- `examples/quickstart/` — create, files, code, `@sandbox`
- `examples/compat-demos/` — E2B-style and Modal-style calls
- `examples/agents/` — call an Agents API that is already up, or run Codex on a cloud sandbox
- `examples/scenarios/agent_loop_local.py` — start a local server, then create, exec, read, and kill
- `examples/templates/python-hello/call_api.py` — HTTP against a template server that is already listening

Code that is copied into the image and started inside the sandbox is the [Server SDK](server-sdk.md).
