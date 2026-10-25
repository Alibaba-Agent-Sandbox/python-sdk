# Express quickstart

Install the [current Python pair](install-python.md) and the separate
[abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md).
Configure the Express provider using the CLI's
[template launch guide](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/using-templates.md);
source builds require the documented Docker/registry prerequisites.

## Launch the application

```bash
export ABX_SERVER_TOKEN='replace_me'
abx --provider alicloud-express template launch 'alibaba-agent-sandbox/awesome-templates//python-hello'
```

The launcher prepares the provider reference, creates the sandbox, runs the
template's startup command and checks its declared services. No workflow selector
is needed. Keep the returned sandbox ID and cleanup instructions.

## Call from Python

Set `SANDBOX_ID` to the returned identifier; keep the same `ABX_SERVER_TOKEN`.
`ABX_SANDBOX_API_KEY` configures platform access and is separate from that token.

```python
import asyncio
import os

from agent_sandbox import ProviderSandbox


async def main():
    sandbox = await ProviderSandbox.connect(
        os.environ["SANDBOX_ID"], provider="alicloud-express"
    )
    try:
        async with await sandbox.application_client(
            9000, token=os.environ["ABX_SERVER_TOKEN"]
        ) as client:
            result = await client.commands.run("hello", name="Python")
            print(result)
    finally:
        await sandbox.close()


asyncio.run(main())
```

This code borrows the CLI-created sandbox and closes its connection. When finished,
use the launch cleanup instructions to delete the sandbox and owned build resources.
See [template launch](template-workflows.md) for the equivalent prepared-reference
Python launcher and lifecycle ownership.
