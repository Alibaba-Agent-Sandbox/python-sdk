# Client SDK

For the 0.5 preview installation and runtime extras, use the [installation guide](install-python.md).

The Client SDK runs on **your machine**. It creates a sandbox, connects to one that already exists, and then runs commands, reads and writes files, and calls the code interpreter. The package is `agent-sandbox-client`. Import `agent_sandbox`.

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client==0.5.0a0'
python -m pip check
```

Do not run `pip install agent-sandbox`. That name on PyPI is an unrelated project.

```python
from agent_sandbox import ProviderSandbox as Sandbox

async with await Sandbox.create(template="base") as sandbox:
    result = await sandbox.commands.run("echo hello")
    print(result.stdout)
```

The [Server SDK](server-sdk.md) (`agent-sandbox-server`) is an optional HTTP application running inside a sandbox. Provider operations such as lifecycle, commands and files use the selected Provider's own transports; they do not all run through the Server SDK. Calling a registered business command requires that application's service to be installed, running and authorized.

## Choose the target and client

| Task | Python entry | Target and credential |
| --- | --- | --- |
| Create or manage an Express/OpenSandbox instance | `ProviderSandbox.create()` / `ProviderSandbox.connect()` | Provider template/image or actual Sandbox ID, plus that Provider's configuration |
| Call a running Server SDK application | `ServerClient` | HTTP service URL plus application token and any required gateway headers |
| Call a managed Agents API application | An HTTP client such as `httpx` | The single Gateway URL and business bearer token; see [Managed Agents API](managed-agents-api.md) |

A CLI deployment name, a Sandbox ID, an HTTP URL and an Agents Session ID are distinct. `ProviderSandbox.connect()` takes a Sandbox ID, not a URL or the CLI's local deployment name. `ServerClient` does not create or destroy cloud instances. CLI OpenAPI bindings and aliases do not automatically become Python methods; use the server's documented HTTP interface for APIs outside the typed client.

`ProviderSandbox` can use the configured default Provider, or an explicit `provider="alicloud-express"` / `provider="opensandbox"`. Set it explicitly when managing IDs from more than one backend. This selects a backend; it does not translate IDs or make provider capabilities interchangeable. See [Provider configuration](providers.md) for each backend's endpoint, credentials and installation requirements.

## Close the right resource

`await sandbox.close()` releases local connections and leaves the remote sandbox running. `await sandbox.kill()` deletes the remote sandbox. The `ProviderSandbox` async context manager attempts `kill()` on exit, including when the handle came from `connect()`; for a borrowed sandbox, use `try/finally` with `close()` instead. An HTTP client's `aclose()` closes its transport only.

An Agents Session has its own close/cancel/delete operations. An accepted request is not a finished turn, and an accepted cancellation is not a confirmed stop. Follow the Session, Submission or Operation returned by the [managed API](managed-agents-api.md); a transport timeout does not authorize replaying work with a fresh idempotency key.

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
