# SDK entry comparison

Choose an entry by the API your code uses. The entries below share project
configuration (`ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL`, `ABX_SANDBOX_DOMAIN`),
but retain their own method signatures and result models.

| Entry | Use | Requirements |
|---|---|---|
| `from agent_sandbox import Sandbox` | Standard synchronous lifecycle, command and file APIs | Alibaba-supported pinned standard contract; Express account |
| `from agent_sandbox import AsyncSandbox` | The same standard operations from async code | Await asynchronous methods |
| `from agent_sandbox.code_interpreter import Sandbox, AsyncSandbox` | Standard interpreter results and contexts | An interpreter-enabled template such as `code-interpreter-v1` |
| `from agent_sandbox import ProviderSandbox` | Explicit provider extensions, sessions and application clients | The selected provider must implement the requested operation |
| `from agent_sandbox.declarative import sandbox` | Execute a Python function remotely | A template with the required Python environment and dependencies |
| `from agent_sandbox.server import command, start` | Register and serve application commands inside an image | Install the same-version server runtime inside that image |

Install the [published Python packages](install-python.md). The Python packages
do not install the separate [abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox).

## Standard interpreter

```python
from agent_sandbox.code_interpreter import Sandbox

with Sandbox.create(template="code-interpreter-v1") as sandbox:
    result = sandbox.run_code("print(1 + 1)")
    assert result.error is None
    print(result.text)
```

For an existing E2B application, follow the [pinned migration contract](migrate-from-e2b.md).
Changing imports does not remove backend permissions, account restrictions or
runtime prerequisites. Third-party libraries keep their own native configuration.

## Provider command and file operations

```python
from agent_sandbox import ProviderSandbox

async with await ProviderSandbox.create(template="base") as sandbox:
    result = await sandbox.commands.run("printf hello")
    assert result.exit_code == 0
    await sandbox.files.write("/home/user/note.txt", result.stdout)
    assert await sandbox.files.read("/home/user/note.txt") == "hello"
```

This uses command and file operations on Express `base`. It does not exercise an
interpreter API or start an application server. The Express ProviderSandbox
adapter does not implement interpreter operations; use the standard interpreter
entry above for those calls. Other providers' operation declarations are separate
from account availability and live acceptance; see [providers](providers.md).

## Template applications

Use `abx template launch <reference>` to prepare and start the complete template.
Advanced `template build` / `template deploy` handle image preparation separately.
After launch, bind an application client with
`await sandbox.application_client(9000, token=application_token)` and call
`client.commands.run("hello", name="Python")`. This requires a running template
that registers hello; plain `base` does not provide it. See
[Express quickstart](express-quickstart.md) and [template launch](template-workflows.md).

Application tokens and platform credentials have separate audiences. The provider
owns gateway resolution and preserves the required headers and URL prefix.
Close borrowed client connections; delete only sandboxes and build resources
you own.

## Verification scope

A compatible signature or provider declaration is not a live-cloud result.
[Cloud examples](cloud-examples.md) describe reproducible scripts and their
prerequisites. Each recorded test covers its actual account, template, provider
and invocation path. This guide makes no cross-platform startup-time, GPU,
maximum-lifetime or pricing comparison; those depend on platform and account
conditions and are not established by an API comparison.
