# Sandbox Lifecycle and Ownership

This page describes current ProviderSandbox lifecycle behavior. It does not define
additional persistent/hibernated SDK types or a global cleanup service. Standard
`Sandbox` / `AsyncSandbox` retain their separate
[standard contract](../guide/migrate-from-e2b.md).

## Create an owned sandbox

Creating `base` provides the platform's command/file environment. It does not
start a template application or imply interpreter, PTY, storage persistence or
other conditional provider operations. This complete example owns its sandbox:

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

The context manager destroys this sandbox when the body finishes, including when
an exception is raised. See [getting started](../guide/getting-started.md) for
installation/account setup and [SDK usage](../guide/sdk-usage.md) for actual API
signatures. The documented timeout is a resource/command setting; it is not a
universal platform billing or data-retention guarantee.

## Attach to an existing sandbox

`await ProviderSandbox.connect(sandbox_id)` attaches a client. `close()` releases
its local connection; `kill()` deletes the remote sandbox. Delete only resources
whose lifecycle you own. For a borrowed instance, close the client when finished
and leave deletion to its owner. There is no automatic account-wide orphan cleanup
implied by losing a client connection or by the final process exiting.

## Template applications and interpreter execution

For a template application, use the unified CLI launch flow and its readiness
checks before calling the resolved application service with its token. See
[template launch](../guide/template-workflows.md). A familiar platform template
name alone does not perform service startup.

Structured interpreter calls use the standard
`agent_sandbox.code_interpreter` entry and its documented template prerequisite;
Express ProviderSandbox does not implement interpreter operations.

## Conditional platform features

Pause/resume, snapshots and persistent storage depend on the specific provider,
platform and account. Consult its current documentation and exact operation
contract. The SDK does not promise universal persistent/hibernated modes, free
storage, fixed startup latency or retention periods. There is no public
`Config.set(...)` global cleanup policy. No future mode flags or speculative
lifecycle APIs are part of this page.
