# Getting Started

For current SDK installation, use the [paired source installation guide](install-python.md).

This is the **Client SDK**: install it on your machine, create a sandbox, and use it. The service that starts inside the image is the [Server SDK](server-sdk.md).

This tutorial covers the lifecycle from install through teardown.

---

## Prerequisites

- Python 3.10 or later
- For the default provider (`alicloud-express`): an API key from the [Agent Sandbox product docs](https://help.aliyun.com/zh/functioncompute/product-overview-of-fc-agent-sandbox). The variable is `E2B_API_KEY`. The standard SDK reads `E2B_API_KEY`, `E2B_API_URL` and `E2B_DOMAIN`.
- Network access to the Alibaba Cloud Hangzhou region (default `cn-hangzhou`)

## 1. Installation

```bash
# Install the SDK
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/e86cb0be24e0083a27396b260298e7cf27b660d6.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/e86cb0be24e0083a27396b260298e7cf27b660d6.tar.gz#subdirectory=client-sdk"

# Install with all extras (recommended)
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/e86cb0be24e0083a27396b260298e7cf27b660d6.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client[all] @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/e86cb0be24e0083a27396b260298e7cf27b660d6.tar.gz#subdirectory=client-sdk"
```

Do not run `pip install agent-sandbox`. That name on PyPI is an unrelated project.

The `abx` CLI is not part of the Python package (there is no `[cli]` extra); it is a separate Node.js project, see [Related: the abx CLI](#related-the-abx-cli). The container-side runtime
(`agent_sandbox.server`) is the separate `agent-sandbox-server` package ([paired source installation guide](install-python.md)); `agent-sandbox-client`
depends on it, so installing the client provides it too.

### Working from a source checkout

From the repository root, with a virtual environment activated, install both
local distributions and the development tools:

```bash
uv pip install -e ./server-sdk -e "./client-sdk[dev]"
```

The root uv workspace resolves the client's runtime dependency to `server-sdk/`.
No `--no-sources` workaround is needed. Regular `pip install` accepts the same
editable arguments; published packages retain the matching server version pin.

## 2. Configure the API Key

There are three ways to configure credentials. When a call actually needs the key, this is the order (highest first). The full table is in [Configuration — Credential resolution](../reference/configuration.md#credential-resolution).

### Option 1: Code parameter (this call only)

```python
from agent_sandbox.api.sandbox import Sandbox

sandbox = await Sandbox.create(sandbox_api_key="your-api-key-here")
```

### Option 2: Environment variable (recommended for CI/CD)

```bash
export E2B_API_KEY="your-api-key-here"
```

### Option 3: Persisted file (`~/.abx/.env`)

Used when neither the environment nor the project `.env` sets the key. The file is written by the `abx` CLI (`abx config set sandbox_api_key your-api-key`, permissions 600; see [Related: the abx CLI](#related-the-abx-cli)) or edited by hand: `E2B_API_KEY=your-api-key`.

## 3. Create Your First Sandbox

### Using the SDK (async)

```python
import asyncio
from agent_sandbox.api.sandbox import Sandbox

async def main():
    # Create a sandbox (default template: base, timeout: 300 seconds)
    sandbox = await Sandbox.create(template="base", timeout=300)
    print(f"Sandbox created: {sandbox.id}")
    print(f"Status: {sandbox.status.value}")

asyncio.run(main())
```

`base` is the default template (`Sandbox.create()` with no template argument). The repository README uses `python-base` because that image registers the `hello` command shown there.

### Using the SDK (sync)

```python
from agent_sandbox.api.sandbox import Sandbox

sandbox = Sandbox.create_sync(template="base")
print(f"Sandbox ID: {sandbox.id}")
```

## 4. Execute Code

### SDK

```python
result = await sandbox.run_code("print('Hello, Agent Sandbox!')")
print(result.text)     # "Hello, Agent Sandbox!"
print(result.stdout)   # "Hello, Agent Sandbox!\n"
print(result.exit_code)  # 0
```

## 5. Run Shell Commands

### SDK

```python
result = await sandbox.commands.run("ls -la /home/user")
print(result.stdout)
print(f"Exit code: {result.exit_code}")
```

## 6. File Operations

### Upload files to the sandbox

```python
# Write a text file
await sandbox.files.write("/home/user/hello.py", "print('hello world')")

# Upload a local file
await sandbox.files.upload("./local_script.py", "/home/user/script.py")
```

### Download files from the sandbox

```python
# Read text
content = await sandbox.files.read("/home/user/hello.py")
print(content)

# Download to local
await sandbox.files.download("/home/user/output.csv", "./output.csv")
```

## 7. List Directory Contents

```python
files = await sandbox.files.list("/home/user")
for f in files:
    print(f"{f.name} ({f.type.value}, {f.size} bytes)")
```

## 8. Destroy a Sandbox

### SDK

```python
await sandbox.kill()
```

### Using a Context Manager (recommended)

```python
async with await Sandbox.create(template="base") as sandbox:
    result = await sandbox.run_code("print('auto cleanup')")
    print(result.text)
# Automatically destroyed after exiting the with block
```

## 9. Complete Example

```python
import asyncio
from agent_sandbox.api.sandbox import Sandbox

async def main():
    async with await Sandbox.create(template="base") as sandbox:
        # Install dependencies
        await sandbox.commands.run("pip install requests")

        # Execute code
        result = await sandbox.run_code("""
import requests
resp = requests.get('https://httpbin.org/get')
print(resp.status_code)
""")
        print(f"Status code: {result.text}")

        # Write and read files
        await sandbox.files.write("/home/user/note.txt", "Hello!")
        content = await sandbox.files.read("/home/user/note.txt")
        print(f"File content: {content}")

asyncio.run(main())
```

---

The sandbox server can also host coding-agent CLIs. Codex (`codex`, npm package `@openai/codex`) and Qwen Code (`qwen`, npm package `@qwen-code/qwen-code`) are supported today, on `/v1/agents/sessions`, after `ABX_SERVER_ENABLED_GROUPS` includes `agents`. See [Hosted agents](hosted-agents.md).

## Next Steps

- [Authentication](authentication.md) — Authentication methods and configuration priority
- [SDK Usage Guide](sdk-usage.md) — Complete API usage
- [Error Codes Reference](../reference/error-codes.md) — Error troubleshooting
- [Troubleshooting](troubleshooting.md) — Common issues and solutions

---

## Related: the abx CLI

The command-line equivalents of the steps above (installing `abx` with npm or as a standalone binary, `abx config set`, `abx create`, `abx exec`, `abx upload` / `download`, `abx kill`) are in the CLI repository: [Getting Started (CLI)](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/getting-started.md), [Binary Installation](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md), [CLI Tutorial](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/cli-tutorial.md) and [Using Templates](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/using-templates.md).
