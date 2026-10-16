# SDK Usage Guide

This document covers the complete usage of the Agent Sandbox Python SDK.

---

## Installation

```bash
pip install agent-sandbox-client
```

Do not run `pip install agent-sandbox`. That name on PyPI is an unrelated project.

## Import

```python
from agent_sandbox.api.sandbox import Sandbox
```

---

## Template author quick path

Verified 2026-10-15 on Alibaba Cloud Express (`alicloud-express`) with a generation-2 template whose start command runs `agent-sandbox-server`. `Sandbox.create(template=..., provider="alicloud-express")` uses `E2B_API_KEY`, `E2B_API_URL`, and `E2B_DOMAIN`. The template argument is the template id or its name.

```python
import asyncio

from agent_sandbox import ProviderSandbox as Sandbox

TEMPLATE = "hello-x"  # name or id of a generation-2 template


async def main() -> None:
    async with await Sandbox.create(
        template=TEMPLATE, provider="alicloud-express", timeout=300
    ) as sb:
        assert await sb.run("hello", name="Bob") == "Hello, Bob!"
        echoed = await sb.commands.run("echo hi", on_stdout=lambda text: None)
        assert echoed.stdout == "hi\n" and echoed.exit_code == 0
        await sb.files.write("/home/user/note.txt", "abc")
        assert await sb.files.read("/home/user/note.txt") == "abc"
        url = sb.network.get_url(9000)
        headers = sb.network.get_access_headers()
        # GET {url}/health with headers. /health answers 200.


asyncio.run(main())
```

`sandbox.run` is the one call for a named command. It returns the function's value. `timeout=` (seconds) is the HTTP limit for a slow command and is not passed to the function. Shell output streams through `on_stdout` / `on_stderr` on `commands.run`. A named command does not stream its own prints; it returns when the function returns.

An unknown name raises `CommandNotFoundError` and lists the commands the server reported. Bad arguments raise `CommandArgumentError`. A command that raises raises `CommandExecutionError` (`error_type` is the exception class). The context manager calls `kill()`.

Deploy the template with `abx template deploy . -y --generation 2 --start-cmd 'agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py' --ready-cmd 'agent-sandbox-server healthcheck --port 9000'`. Full steps: [Express quickstart](express-quickstart.md).

---

## Create and Destroy

### Async Creation

```python
sandbox = await Sandbox.create(
    template="base",      # Template name (default "base")
    timeout=300,           # Timeout in seconds (1–86400, default 300)
    envs={"KEY": "val"},   # Injected environment variables
    metadata={"team": "x"},# Arbitrary metadata key-value pairs
    cpu=2,                 # CPU cores (optional)
    memory=4096,           # Memory in MB (optional)
    disk=10240,            # Disk in MB (optional)
    gpu="A10",             # GPU spec (optional)
)
```

### Sync Creation

```python
sandbox = Sandbox.create_sync(template="base")
```

### Context Manager (recommended)

Automatically calls `kill()` to destroy the sandbox when exiting the `with` block:

```python
async with await Sandbox.create(template="base") as sandbox:
    result = await sandbox.run_code("print(1+1)")
    print(result.text)  # "2"
# Automatically destroyed
```

### Connect to an Existing Sandbox

```python
sandbox = await Sandbox.connect("sbx-xxxx")

# Sync version
sandbox = Sandbox.connect_sync("sbx-xxxx")
```

### Destroy a Sandbox

```python
# Instance method
await sandbox.kill()

# Class method (destroy by ID, no need to connect first)
await Sandbox.kill_by_id("sbx-xxxx")

# Sync version
Sandbox.kill_by_id_sync("sbx-xxxx")
```

### List Sandboxes

```python
sandboxes = await Sandbox.list(status=SandboxStatus.RUNNING, limit=20)
for sb in sandboxes:
    print(f"{sb.sandbox_id} - {sb.template} - {sb.status.value}")
```

---

## Execute Code — run_code

Execute code via the Code Interpreter:

```python
result = await sandbox.run_code(
    "print('hello')",
    language="python",   # Default "python"
    timeout=30,          # Timeout in seconds (default 30)
    envs={"KEY": "val"}, # Temporary env vars for this execution (envd scope)
)

print(result.text)           # Output text (stdout with trailing whitespace stripped)
print(result.stdout)         # Raw stdout
print(result.stderr)         # Raw stderr
print(result.exit_code)      # Exit code
print(result.execution_time) # Execution time (seconds)
print(result.output_files)   # Output file list [OutputFile]
```

Callback support:

```python
result = await sandbox.run_code(
    "for i in range(3): print(i)",
    on_stdout=lambda s: print(f"[OUT] {s}"),
    on_stderr=lambda s: print(f"[ERR] {s}"),
)
```

> **Capability requirement**: Requires the `code` capability (included in the default capability set `{shell, files, code}`).

---

## Execute Commands — commands

The `sandbox.commands` submodule provides shell command execution capabilities.

### Execute and Wait

```python
result = await sandbox.commands.run(
    "ls -la /home/user",
    timeout=60,                # Timeout in seconds (default 60)
    env={"MY_VAR": "value"},   # Additional env vars for this command (envd scope)
    cwd="/app",                # Working directory
)

print(result.stdout)
print(result.stderr)
print(result.exit_code)
print(result.execution_time)
print(result.success)  # exit_code == 0
```

`on_stdout` and `on_stderr` run once per chunk as the command produces it:

```python
result = await sandbox.commands.run(
    "echo hi",
    on_stdout=lambda text: print(text, end=""),
    on_stderr=lambda text: print(text, end=""),
)
```

### Streaming Output

```python
async for chunk in sandbox.commands.stream("pip install flask"):
    if chunk.type.value == "stdout":
        print(chunk.data, end="")
    elif chunk.type.value == "stderr":
        print(chunk.data, end="", file=sys.stderr)
    elif chunk.type.value == "exit":
        print(f"\nExit code: {chunk.exit_code}")
```

### Background Execution

```python
reader = await sandbox.commands.start("python server.py")
# reader is a StreamReader that can be consumed asynchronously
```

You can also use the `background=True` parameter of `run`:

```python
reader = await sandbox.commands.run("sleep 60", background=True)
```

### Process Management

```python
# List processes
processes = await sandbox.commands.list()

# Kill a process
await sandbox.commands.kill(pid=12345)

# Send a signal: envd delivers only SIGTERM (15) and SIGKILL (9);
# any other number (for example 2, SIGINT) raises ValueError
await sandbox.commands.send_signal(pid=12345, signal=15)  # SIGTERM
await sandbox.commands.send_signal(pid=12345, signal=9)   # SIGKILL

# Send stdin data
await sandbox.commands.send_input(pid=12345, data="yes\n")
```

### Sync Versions

All methods have synchronous counterparts with a `_sync` suffix:

```python
result = sandbox.commands.run_sync("echo hello")
```

---

## File Operations — files

The `sandbox.files` submodule provides filesystem operations.

### Read/Write

```python
# Write text or bytes
await sandbox.files.write("/home/user/hello.txt", "Hello World")
await sandbox.files.write("/home/user/data.bin", b"\x00\x01\x02")

# Read text
text = await sandbox.files.read("/home/user/hello.txt", encoding="utf-8")

# Read bytes
data = await sandbox.files.read_bytes("/home/user/data.bin")
```

### Upload / Download

```python
# Upload a local file to the sandbox
await sandbox.files.upload("./local_file.py", "/home/user/remote.py")

# Download a sandbox file to local
await sandbox.files.download("/home/user/output.csv", "./output.csv")
```

### Directory Operations

```python
# List directory contents
entries = await sandbox.files.list("/home/user")
for entry in entries:
    print(f"{entry.name} - {entry.type.value} - {entry.size}")

# Create a directory (including parents)
await sandbox.files.make_dir("/home/user/new/nested/dir")

# Check if a path exists
exists = await sandbox.files.exists("/home/user/hello.txt")

# Get file info
info = await sandbox.files.get_info("/home/user/hello.txt")
```

### Move / Delete

```python
# Move/rename
await sandbox.files.move("/home/user/old.txt", "/home/user/new.txt")

# Delete a file or directory
await sandbox.files.remove("/home/user/temp.txt")
```

### Watch File Changes

```python
watcher = await sandbox.files.watch("/home/user")
async for event in watcher:
    print(f"{event.type}: {event.path}")
```

---

## Network — network

The `sandbox.network` submodule computes port access URLs (purely local computation, no network requests involved).

> **Capability requirement**: Requires the `ports` capability. The default capability set does not include `ports`; it must be explicitly declared in the template's `template.yaml`.

```python
# Get port URL
url = sandbox.network.get_url(8080)
# => "https://8080-sbx-xxxx.cn-hangzhou.e2b.fc.aliyuncs.com"

# Get host
host = sandbox.network.get_host(8080)
# => "8080-sbx-xxxx.cn-hangzhou.e2b.fc.aliyuncs.com"

# Secure mode: X-Access-Token for the platform gateway (envd /files).
# sandbox.run and sandbox.server do not send this header to port 9000.
headers = sandbox.network.get_access_headers()
```

---

## Sandbox Lifecycle

```python
# Check if running (makes an API call)
running = await sandbox.is_running()

# Refresh sandbox info
info = await sandbox.refresh_info()

# Set timeout
await sandbox.set_timeout(600)

# Pause/resume
await sandbox.pause()
await sandbox.resume()
```

### Properties

```python
sandbox.id           # Sandbox ID (str)
sandbox.status       # Current status (SandboxStatus)
sandbox.url          # envd URL (str)
sandbox.info         # Full info (SandboxInfo)
sandbox.capabilities # Capability set (frozenset[str])
```

---

## Sync vs Async

The SDK uses an **async-first** design — all core methods are asynchronous. Each async method has a corresponding synchronous wrapper (generated via `make_sync`):

| Async Method | Sync Method |
|--------------|-------------|
| `Sandbox.create()` | `Sandbox.create_sync()` |
| `Sandbox.connect()` | `Sandbox.connect_sync()` |
| `sandbox.kill()` | `sandbox.kill_sync()` |
| `sandbox.run_code()` | `sandbox.run_code_sync()` |
| `sandbox.commands.run()` | `sandbox.commands.run_sync()` |
| `sandbox.files.read()` | `sandbox.files.read_sync()` |
| `sandbox.files.write()` | `sandbox.files.write_sync()` |

Sync methods run an event loop in the background and are suitable for scripts and non-async environments.

---

## Error Handling

All SDK errors inherit from `SandboxError` and carry `code`, `message`, and `suggestion` attributes:

```python
from agent_sandbox.models.errors import (
    SandboxError,
    InvalidAPIKeyError,       # E1001
    TemplateNotFoundError,    # E2001
    SandboxNotFoundError,     # E2009
    CapabilityNotSupportedError,  # E3004
    FileNotFoundError_,       # E4001
    ConnectionError_,         # E5001
)

try:
    sandbox = await Sandbox.create(template="nonexistent")
except TemplateNotFoundError as e:
    print(f"[{e.code}] {e.message}")
    print(f"Suggestion: {e.suggestion}")
except SandboxError as e:
    print(f"SDK error: {e}")
```

See [Error Codes Reference](../reference/error-codes.md) for details.

---

## Named Commands

There is one mechanism for named commands: functions registered in the sandbox server (`@sandbox.register`, or the server's `CommandRegistry`). `sandbox.run(name, **kwargs)` calls one of them (`POST /commands/{name}`), and `sandbox.list_commands()` lists them:

```python
commands = await sandbox.list_commands()
for cmd in commands:
    print(f"{cmd.name}: {cmd.description}")

result = await sandbox.run("dev", port=8080)   # the registered function's return value
```

An unknown name raises `CommandNotFoundError` (the message includes the server's available-command list). Bad arguments raise `CommandArgumentError`. A command that raises raises `CommandExecutionError` (also a `ServerAPIError`). Pass `timeout=` when the call may take longer than 30 seconds. The sandbox image must run `agent-sandbox-server` (see below). For a bare shell command, including streamed stdout, use `sandbox.commands.run(cmd)`; it never goes through the registry.

---

## Template Server — server

Templates that ship an `agent-sandbox-server` expose a second, template-authored data plane (port 9000). `sandbox.server`
is its typed client. Use it when the template restricts what is reachable (per-endpoint policy) or when you need
endpoints envd does not have (search, archive, file watching, process output/stdin, git, browser).

```python
async with await Sandbox.create(template="my-server-template") as sandbox:
    server = sandbox.server                        # or sandbox.server_at(9000, token="...")
    caps = await server.discover()                 # explicit; enables fail-fast pre-checks
    if caps.can("files_download_stream"):
        data = await server.files.download("/home/user/out/report.csv")
    await server.files.upload("/home/user/in/data.json", b"{}")

    result = await server.process.shell("ls -la", cwd="/home/user")
    async for event in server.process.shell_stream("make test"):
        print(event.event, event.data)

    print(server.files.list_sync("/home/user"))    # every coroutine has a *_sync twin
```

Starting a server in a running sandbox (the image must contain `agent-sandbox-server`):

```python
server = await sandbox.start_server(policy="read-only", token="s3cret", commands="/home/user/app/commands.py")
```

### Restricting endpoints (template author)

```python
from agent_sandbox.server import SandboxServer

policy = {
    "preset": "transfer-only",                      # only upload + download endpoints, size-capped
    "endpoints": {
        "files_download_stream": {"paths": {"allow": ["/home/user/out"], "deny": ["**/.env"]},
                                  "limits": {"max_bytes": "5MB"}},
        "files_upload_stream":   {"paths": {"allow": ["/home/user/in"]}, "params": {"overwrite": False}},
    },
}
SandboxServer(policy=policy).serve(9000)   # a dict or a ServerPolicy
```

or declaratively in `template.yaml` (`server:` block, see the [template spec](../reference/template-yaml-spec.md)), or
`agent-sandbox-server serve --policy server-policy.json`. Validate with `agent-sandbox-server check-config`.

### Handling denials

```python
from agent_sandbox.models.errors import (
    EndpointNotAvailableError, FilePolicyDeniedError, PayloadTooLargeError, RateLimitedError, ServerAPIError,
)

try:
    await server.files.download("/etc/passwd")
except FilePolicyDeniedError as exc:            # also a PermissionDeniedError
    print(exc.error_code, exc.endpoint)         # path_not_allowed files_download_stream
except EndpointNotAvailableError:               # disabled by policy (or unknown to an older server)
    ...
except RateLimitedError as exc:
    await asyncio.sleep(exc.retry_after or 1)
except ServerAPIError as exc:                   # base class: status_code, error_type, error_code, endpoint
    ...
```

The server is always authoritative: after `discover()` the client merely fails fast with the same exception
without a round trip. Policy changes are picked up with `server.forget_discovery()` + `discover()`.

---

## Environment Variables

Environment variables can be injected at creation (`envs=`) or per-call (`env=`/`envs=`). Commands containing unquoted shell operators (pipes `|`, semicolons `;`, logical operators `&&`/`||`, redirects `>`/`<`, subshells `(...)`, command substitution `$(...)`) are **automatically wrapped** in `sh -c` by `commands.run()`, `commands.stream()`, and `commands.start()`. Variable expansion (`$VAR`), backtick substitution (`` `cmd` ``), and glob patterns (`*`, `?`) still require explicit `sh -c '...'` wrapping, or use `printenv VAR` to read a single variable.

For full details on scopes (envd vs SandboxServer), injection patterns, and security considerations, see the dedicated [Environment Variables Guide](environment-variables.md).

---

## Agent workflow pattern

This is the canonical pattern for AI Agent scenarios — create a sandbox, run task code, collect the result, then destroy it:

```python
import asyncio
from agent_sandbox.api.sandbox import Sandbox

async def agent_workflow(task_code: str) -> str:
    """Agent → create sandbox → exec code → read result → kill sandbox"""
    async with await Sandbox.create(template="my-app") as sandbox:
        # Write the task code
        await sandbox.files.write("/app/task.py", task_code)

        # Execute
        result = await sandbox.commands.run("python3 /app/task.py")

        # Read the output
        if result.exit_code == 0:
            try:
                output = await sandbox.files.read("/app/output.txt")
                return output
            except Exception:
                return result.stdout
        else:
            return f"Error (exit {result.exit_code}): {result.stderr}"

# Usage
result = asyncio.run(agent_workflow("""
import json
data = {"status": "done", "items": [1, 2, 3]}
with open("/app/output.txt", "w") as f:
    json.dump(data, f)
print("Task completed")
"""))
print(result)
```

---
