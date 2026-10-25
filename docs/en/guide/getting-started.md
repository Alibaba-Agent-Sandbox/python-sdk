# Getting Started

Install the Client SDK on your machine to create and use sandboxes. The
[Server SDK](server-sdk.md) runs applications inside sandbox images.
This tutorial uses the provider extension `ProviderSandbox`. Standard synchronous
`Sandbox` and asynchronous `AsyncSandbox` entries are documented in
[Migrate from E2B](migrate-from-e2b.md).

## 1. Install and configure

Use Python 3.10 or later. Create and activate a virtual environment following the
[installation guide](install-python.md), then install:

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client==0.4.0a4'
python -m pip check
export ABX_SANDBOX_API_KEY='your-api-key'
```

Obtain the Express sandbox API key using the
[Agent Sandbox product documentation](https://help.aliyun.com/zh/functioncompute/product-overview-of-fc-agent-sandbox).
The default provider is `alicloud-express`, region `cn-hangzhou`. All project entries, including standard `Sandbox` / `AsyncSandbox` and
`ProviderSandbox`, support `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and
`ABX_SANDBOX_DOMAIN`. Use these names for project configuration. See
[authentication](authentication.md) for provider-extension `sandbox_api_key=` overrides;
standard entries retain their documented public `api_key=` parameter.

Installing the client installs the matching server distribution. This does not
update a server already inside an existing image. The distribution named
`agent-sandbox` on PyPI is an unrelated project. Optional dependencies and source
development are covered in the [installation guide](install-python.md).

## 2. Create, execute and transfer files

Save this as `quickstart.py`, then run `python quickstart.py`:

```python
import asyncio

from agent_sandbox import ProviderSandbox


async def main():
    async with await ProviderSandbox.create(template="base", timeout=300) as sandbox:
        print(f"Sandbox ID: {sandbox.id}")
        result = await sandbox.commands.run("printf 'Hello, Agent Sandbox!'")
        assert result.exit_code == 0
        print(result.stdout)

        path = "/home/user/note.txt"
        await sandbox.files.write(path, "Hello from Python!")
        assert await sandbox.files.read(path) == "Hello from Python!"
        await sandbox.files.download(path, "note.txt")
        await sandbox.files.upload("note.txt", "/home/user/copied-note.txt")
        assert await sandbox.files.read("/home/user/copied-note.txt") == "Hello from Python!"

    # The context manager destroys this owned sandbox, including on an exception.


asyncio.run(main())
```

`base` provides command and file operations. It does not imply a code interpreter
or application server. Native process calls accept `user="root"` or another
existing OS account; this selects the account for that request only.

For an existing sandbox, `await ProviderSandbox.connect(sandbox_id)` attaches a
client. Call `await sandbox.close()` when finished; delete it with
`await sandbox.kill()` only when you own its lifecycle.

## 3. Run a Python script

Use command execution when you want to run a Python program on `base`:

```python
result = await sandbox.commands.run("python3 -c 'print(1 + 1)'")
assert result.exit_code == 0 and result.stdout.strip() == "2"
```

Run this inside the context from step 2. This exercises a shell process, not an
interpreter API. For structured interpreter results on Express, use the standard
`agent_sandbox.code_interpreter` entry described in [E2B migration](migrate-from-e2b.md);
the Express `ProviderSandbox` adapter does not implement interpreter operations.

## 4. Run a template application

Use the separately installed [abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox)
to launch a catalog template with its declared startup and readiness checks.
Follow [template launch](template-workflows.md) to call its application API and clean
up the owned resources. Creating a plain sandbox with `base` does not start a
template's application.

## Next steps

Template builder helpers are public imports from this installed package:
`from agent_sandbox import Template, AsyncTemplate, wait_for_port, default_build_logger`.
No separate `e2b` installation is needed for these names. Standard template APIs
retain their documented platform/account prerequisites and public parameters.

Standard sandbox classes use `from agent_sandbox import Sandbox, AsyncSandbox`.
Interpreter classes use `from agent_sandbox.code_interpreter import Sandbox, AsyncSandbox`;
these are distinct entries. Their imports require no separate upstream SDK.

The [2026-10-25 public-a4 example record](../../../.agents/evidence/verify/2026-10-25-public-a4-examples.md)
separates 14 real cloud examples from local protocol fixtures, timeout controls
and independent cleanup checks. A passing example is not whole-catalog coverage.

- [SDK usage](sdk-usage.md): provider extensions and their synchronous wrappers.
- [Declarative functions](declarative-usage.md): execute a Python function remotely.
- [MCP integration](mcp-integration.md): connect an IDE or agent.
- [Troubleshooting](troubleshooting.md): installation and runtime errors.

## Related: the abx CLI

The CLI is a separate Node.js package, `@agent-sandbox/cli`. Installing Python does
not install `abx`; there is no Python `[cli]` extra. Follow the
[CLI installation guide](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md).
