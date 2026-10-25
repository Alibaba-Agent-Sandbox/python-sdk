# SDK API Design

This page describes the current asynchronous `ProviderSandbox` provider/server
extensions. Root `Sandbox` / `AsyncSandbox` and `agent_sandbox.code_interpreter`
are separate standard contracts; see [E2B migration](../guide/migrate-from-e2b.md).
It is a current overview, not a proposal for additional APIs.

## Design rules

- ProviderSandbox creates and operates sandboxes. Source image preparation belongs
  to the CLI: normally `abx template launch <reference>`, with build/deploy as
  advanced operations. Standard Template builders retain their separate contract.
- Shell commands, interpreter execution and template application commands use
  distinct APIs and prerequisites. Creating `base` does not start an application.
- Provider declarations and the actual account determine supported operations.
  A generic method's presence does not certify every provider's implementation.
- Public signatures, typed errors and explicit lifecycle ownership define the API.

## Paradigm 1: Imperative

This complete program runs a command and transfers file content on Express `base`.
Use your account's documented canonical ABX environment configuration. The context
manager destroys this owned sandbox even when the body raises an exception.

```python
import asyncio

from agent_sandbox import ProviderSandbox


async def main():
    async with await ProviderSandbox.create(template="base", timeout=60) as sandbox:
        result = await sandbox.commands.run("printf 'Hello, Agent Sandbox!'")
        assert result.exit_code == 0
        print(result.stdout)
        path = "/home/user/data.csv"
        await sandbox.files.write(path, "name,age\nAlice,30\nBob,25\n")
        assert await sandbox.files.read(path) == "name,age\nAlice,30\nBob,25\n"


asyncio.run(main())
```

For structured interpreter execution, use the standard
`agent_sandbox.code_interpreter` entries with their documented
`code-interpreter-v1` prerequisite. Express ProviderSandbox does not implement
interpreter operations. See [SDK usage](../guide/sdk-usage.md) for lifecycle and
synchronous wrappers; child client APIs keep their documented signatures.

## Paradigm 2: Declarative decorator

The existing `@sandbox` decorator executes a function in a remotely prepared
runtime and owns its cleanup unless the caller explicitly retains or reuses a
sandbox. Packages, interpreter and serializer prerequisites are described in
[declarative usage](../guide/declarative-usage.md). Registration on SandboxServer
uses the existing `@sandbox.register` or server command registration; this does
not create a new platform capability.

## Three things called "command"

| Operation | Entry | Prerequisite |
| --- | --- | --- |
| Shell process | `sandbox.commands.run(...)` | Provider process support |
| Registered application command | Application client's `commands.run(...)` | Running SandboxServer service and its application token |
| Registered command discovery | Application client's `commands.list()` | The same running service |

First launch the entire template with `abx template launch <reference>`. Connect
using the returned sandbox information and `application_client(..., token=...)`
so provider gateway headers and application authentication are preserved. See
[template launch](../guide/template-workflows.md) and
[template server API](../guide/template-server-api.md). A plain platform create
with a familiar template name does not perform this startup sequence.

Specification 5 declares services in `provides` plus `start_cmd` / `ready_cmd`.
It does not use the retired template `capabilities` list as a runtime guarantee.

## Running an agent

The in-sandbox Agents API exposes `/v1/agents/**` for configured agent adapters.
Install and configure the intended agent CLI in its template, then use the
[Agents API guide](../guide/agents-api.md). A local protocol fixture is distinct
from a real configured model invocation.

## Configuration

Use `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and `ABX_SANDBOX_DOMAIN` for project
platform configuration. ProviderSandbox per-call overrides use
`sandbox_api_key`, `sandbox_base_url` and `sandbox_domain`. Standard clients retain
their separate valid `api_key` contract. See [configuration](../reference/configuration.md)
for precedence and provider-specific fields; do not infer generic platform support
from an optional field name.

## Sandbox core API

The [API reference](../reference/api-reference.md) and
[SDK usage guide](../guide/sdk-usage.md) own complete signatures. Native lifecycle,
command/file clients, network resolution and application clients are distinct
from standard interpreter APIs. PTY and other conditional operations require the
owning provider and actual platform support. `close()` releases a connection;
`kill()` deletes a resource and should only be called for a sandbox you own.

## Errors

Provider errors derive from `SandboxError` and carry `code`, `message`, `suggestion`
and `docs_url`; standard clients retain their separate exception contract. This
complete program catches a real process deadline as `CommandTimeoutError` (E3001).
Cleanup runs in `finally`, and transport closure runs even if deletion raises.

```python
import asyncio

from agent_sandbox import ProviderSandbox
from agent_sandbox.models.errors import CommandTimeoutError


async def main():
    sandbox = await ProviderSandbox.create(template="base", timeout=60)
    try:
        await sandbox.commands.run("sleep 100", timeout=5)
    except CommandTimeoutError as error:
        print(error.code)  # E3001
    finally:
        try:
            await sandbox.kill()
        finally:
            await sandbox.close()


asyncio.run(main())
```

See [error codes](../reference/error-codes.md). Do not replace the typed command
timeout with a nonexistent generic SDK `TimeoutError` import.

## Not in the SDK

Python ProviderSandbox does not build/push source images or create a sandbox from
a natural-language prompt; use the CLI's current launch/scaffold/create guides.
There is no global `Config.set(...)` auto-cleanup policy or compatibility alias.
Use explicit owned lifecycle cleanup and the provider's actual timeout support.
