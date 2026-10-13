# Getting Started

This tutorial walks you through the complete sandbox lifecycle, from installation to teardown.

---

## Prerequisites

- Python 3.10 or later
- A valid API Key (obtained from the Easy Sandbox platform)
- Network access to the Alibaba Cloud Hangzhou region (default `cn-hangzhou`)

## 1. Installation

```bash
# Install the SDK
pip install easy-sandbox

# Install with all extras (recommended)
pip install "easy-sandbox[all]"
```

The `ebx` CLI is not part of the Python package (there is no `[cli]` extra); it is a separate Node.js project, see [Related: the ebx CLI](#related-the-ebx-cli). The container-side runtime
(`easy_sandbox.server`) is the separate `easy-sandbox-server` package (`pip install easy-sandbox-server`); `easy-sandbox`
depends on it, so installing the client provides it too. Upgrading from 0.2.x in place? See
[Migrating from 0.2.x](migrating-from-0.2.md).

## 2. Configure the API Key

There are three ways to configure credentials. When a call actually needs the key, this is the order (highest first). The full table is in [Configuration — Credential resolution](../reference/configuration.md#credential-resolution).

### Option 1: Code parameter (this call only)

```python
from easy_sandbox.api.sandbox import Sandbox

sandbox = await Sandbox.create(api_key="your-api-key-here")
```

### Option 2: Environment variable (recommended for CI/CD)

```bash
export EBX_SANDBOX_API_KEY="your-api-key-here"
```

### Option 3: Persisted file (`~/.ebx/.env`)

Used when neither the environment nor the project `.env` sets the key. The file is written by the `ebx` CLI (`ebx config set sandbox_api_key your-api-key`, permissions 600; see [Related: the ebx CLI](#related-the-ebx-cli)) or edited by hand: `EBX_SANDBOX_API_KEY=your-api-key`.

## 3. Create Your First Sandbox

### Using the SDK (async)

```python
import asyncio
from easy_sandbox.api.sandbox import Sandbox

async def main():
    # Create a sandbox (default template: base, timeout: 300 seconds)
    sandbox = await Sandbox.create(template="base", timeout=300)
    print(f"Sandbox created: {sandbox.id}")
    print(f"Status: {sandbox.status.value}")

asyncio.run(main())
```

### Using the SDK (sync)

```python
from easy_sandbox.api.sandbox import Sandbox

sandbox = Sandbox.create_sync(template="base")
print(f"Sandbox ID: {sandbox.id}")
```

## 4. Execute Code

### SDK

```python
result = await sandbox.run_code("print('Hello, Easy Sandbox!')")
print(result.text)     # "Hello, Easy Sandbox!"
print(result.stdout)   # "Hello, Easy Sandbox!\n"
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
from easy_sandbox.api.sandbox import Sandbox

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

The sandbox server can also host coding-agent CLIs. Codex (`codex`, npm package `@openai/codex`) and Qwen Code (`qwen`, npm package `@qwen-code/qwen-code`) are supported today, on `/v1/agents/sessions`, after `EBX_SERVER_ENABLED_GROUPS` includes `agents`. See [Hosted agents](hosted-agents.md).

## Next Steps

- [Authentication](authentication.md) — Authentication methods and configuration priority
- [SDK Usage Guide](sdk-usage.md) — Complete API usage
- [Error Codes Reference](../reference/error-codes.md) — Error troubleshooting
- [Troubleshooting](troubleshooting.md) — Common issues and solutions

---

## Related: the ebx CLI

The command-line equivalents of the steps above (installing `ebx` with npm or as a standalone binary, `ebx config set`, `ebx create`, `ebx exec`, `ebx upload` / `download`, `ebx kill`) are in the CLI repository: [Getting Started (CLI)](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/getting-started.md), [Binary Installation](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/binary-installation.md), [CLI Tutorial](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/cli-tutorial.md) and [Using Templates](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/using-templates.md).
