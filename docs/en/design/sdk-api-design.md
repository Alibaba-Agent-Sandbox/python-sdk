> The standard public API is now synchronous Sandbox / asynchronous AsyncSandbox. The provider/server extension design below uses ProviderSandbox, including its native `_sync` wrappers; it does not define the standard client API. Standard clients do not switch protocol when `ABX_PROVIDER` changes. See [migration](../guide/migrate-from-e2b.md).

# SDK API Design

> The `agent-sandbox-client` package is the **runtime** client: create a sandbox, use it, kill it. It offers two ways to write that code (imperative and declarative). Building and deploying templates belongs to the `abx` CLI, and running an agent belongs to the Agents API.

---

## Table of Contents

1. [Design rules](#design-rules)
2. [Paradigm 1: Imperative](#paradigm-1-imperative)
3. [Paradigm 2: Declarative decorator](#paradigm-2-declarative-decorator)
4. [Three things called "command"](#three-things-called-command)
5. [Running an agent](#running-an-agent)
6. [Configuration](#configuration)
7. [Sandbox core API](#sandbox-core-api)
8. [Errors](#errors)
9. [Not in the SDK](#not-in-the-sdk)

---

## Design rules

- **Runtime only.** The SDK has no image builder, no Dockerfile generation and no registry push. `abx template build|deploy` owns that pipeline, so there is one build path to document and test.
- **One way to call a named command.** A named command is a function registered in the sandbox's SandboxServer. The client calls it with `sandbox.run("name", **kwargs)`, which is `POST /commands/name`. `template.yaml` has no `custom_commands` key.
- **One way to run an agent.** The Agents API (`/v1/agents/**`) on the SandboxServer. The SDK has no `sb.agent.*` helpers.
- **Typed, explicit surface.** No `__getattr__` dispatch; every method has a signature that mypy checks (`py.typed`).
- **Async first, sync twin.** Every coroutine has a `_sync` twin that manages an event loop for you.
- **Explicit standard and extension contracts.** This page describes the native ProviderSandbox protocol, configuration and error model. `agent_sandbox` exports standard `Sandbox` / `AsyncSandbox`; those clients and `code_interpreter` follow the pinned Alibaba-supported E2B contract. See [Migrate from E2B](../guide/migrate-from-e2b.md).

---

## Paradigm 1: Imperative

```python
from agent_sandbox import ProviderSandbox as Sandbox

sb = await Sandbox.create(template="code-interpreter")

result = await sb.run_code("print('Hello, AliCloud!')")
print(result.text)

result = await sb.commands.run("ls -la /app")
print(result.stdout)

await sb.files.write("/app/data.csv", "name,age\nAlice,30\nBob,25")
content = await sb.files.read("/app/data.csv")
files = await sb.files.list("/app")

await sb.kill()
```

Synchronous mode:

```python
sb = Sandbox.create_sync(template="code-interpreter")
result = sb.run_code_sync("print(1+1)")
sb.kill_sync()
```

Context manager (the sandbox is killed on exit):

```python
async with await Sandbox.create(template="code-interpreter") as sb:
    result = await sb.run_code("import sys; print(sys.version)")
```

Streaming output:

```python
async for chunk in sb.commands.stream("pip install pandas && python train.py"):
    if chunk.type == "stdout":
        print(chunk.data, end="")
    elif chunk.type == "stderr":
        print(f"[ERR] {chunk.data}", end="")
    elif chunk.type == "exit":
        print(f"\nExit code: {chunk.exit_code}")
```

---

## Paradigm 2: Declarative decorator

Inspired by Modal. The decorator runs a local function in a remote sandbox. See [Declarative usage](../guide/declarative-usage.md) for every parameter.

```python
from agent_sandbox.declarative import sandbox

@sandbox(template="code-interpreter-v1", packages=["pandas"])
def analyze(data):
    import pandas as pd
    return pd.DataFrame(data).describe().to_dict()

# create sandbox -> upload function -> run -> return result -> kill sandbox
result = analyze({"col1": [1, 2, 3], "col2": [4, 5, 6]})
```

- `keep_alive=True` keeps the sandbox after the call; `sandbox_id="..."` reuses an existing one.
- `async def` functions are supported, so several calls can run under `asyncio.gather`.
- `@sandbox.register` (inside a sandbox) registers a named command on the SandboxServer; see the next section.

---

## Three things called "command"

| What | Call | Wire |
|------|------|------|
| Raw shell command | `sandbox.commands.run("ls -la")` | envd process API |
| Named command | `sandbox.run("name", x=1)` | `POST /commands/name` on the SandboxServer |
| Catalogue of named commands | `sandbox.list_commands()` | `GET /commands` on the SandboxServer |

`sandbox.run()` never runs a shell string. A name that is not registered raises `CommandNotFoundError`; any other server error raises `ServerAPIError`. Providers without an HTTP data plane (`epp://`) raise `ProviderFeatureNotSupportedError` (E8004).

```python
sb = await Sandbox.create(template="python-hello")

for c in await sb.list_commands():      # list[ServerCommand]
    print(c.name, c.description, c.args)

value = await sb.run("hello", name="Alice")
```

Named commands are registered in the template's `commands.py` (or with `@sandbox.register`). See [Authoring templates](../guide/authoring-templates.md) and [Template server API](../guide/template-server-api.md).

**Capabilities.** `template.yaml` declares `capabilities` (`shell`, `files`, `code`, `terminal`, `ports`) for discovery and documentation. Only `code` is a runtime gate in the client: `run_code()` raises `CapabilityNotSupportedError` (E3004) when `code` is missing. `sandbox.capabilities` returns the effective set.

---

## Running an agent

There is one entry: the Agents API, an HTTP session API on the in-sandbox server (`/v1/agents/**`) that drives Codex and Qwen Code. Install the agent CLI in the template image and call the API. See [Agents API](../guide/agents-api.md) for the guide and the complete case.

---

## Configuration

Resolution order, highest first:

```
Code parameters > Environment variables > .env file > ~/.abx/config.toml > Defaults
```

```bash
export ABX_SANDBOX_API_KEY=your-api-key        # primary credential
export ALICLOUD_ACCESS_KEY_ID=your-ak          # optional AK/SK pair
export ALICLOUD_ACCESS_KEY_SECRET=your-sk
```

Per-call overrides are keyword arguments of `Sandbox.create()` (`api_key`, `api_url`, `domain`, `access_key_id`, `access_key_secret`). The complete key list is in [Configuration](../reference/configuration.md) and [Environment variables](../guide/environment-variables.md).

---

## Sandbox core API

The full signatures are in the [API reference](../reference/api-reference.md). The shape:

| Group | Members |
|-------|---------|
| Lifecycle | `create`, `connect`, `list`, `kill`, `kill_by_id`, `set_timeout`, `is_running`, `pause`, `resume`, `refresh_info` |
| Properties | `id`, `provider`, `status`, `url`, `info`, `capabilities` |
| Code | `run_code` (requires the `code` capability) |
| Commands | `commands.run` / `stream` / `start` / `list` / `kill` (raw shell and processes), `run(name, **kwargs)`, `list_commands()` |
| Files | `files.read` / `read_bytes` / `write` / `list` / `remove` / `exists` / `make_dir` / `move` / `upload` / `download` / `watch` |
| Network | `network.get_host`, `network.get_url`, `network.get_access_headers`, `network.resolve` |
| Terminal | `get_terminal` (PTY over WebSocket) |
| In-sandbox server | `server`, `server_at(port)`, `start_server(...)` return a typed `ServerClient` |

Results are Pydantic models: `CodeResult`, `ProcessResult`, `ProcessChunk`, `FileInfo`, `SandboxInfo`. A sandbox's `metadata` is on `sandbox.info`.

---

## Errors

Every exception derives from `SandboxError` and carries `code`, `message`, `suggestion` and `docs_url`.

```python
from agent_sandbox import ProviderSandbox as Sandbox, SandboxError
from agent_sandbox.models.errors import TemplateNotFoundError, TimeoutError

try:
    sb = await Sandbox.create(template="code-interpreter")
    result = await sb.run_code("import time; time.sleep(100)", timeout=5)
except TemplateNotFoundError as e:
    print(f"[{e.code}] {e.message}")
except TimeoutError as e:
    print(f"[{e.code}] {e.message}")
except SandboxError as e:
    print(f"[{e.code}] {e.message}")
    print(f"Fix suggestion: {e.suggestion}")
```

The full code list is in [Error codes](../reference/error-codes.md).

---

## Not in the SDK

| Not provided | Use instead |
|--------------|-------------|
| Template build, push, deploy (`Image`, `DockerBuilder`, `Sandbox.deploy`) | `abx template build` and `abx template deploy` |
| Natural-language sandbox creation, `Sandbox.plan()` | `abx create --prompt "DESCRIPTION"` and `abx template scaffold "DESCRIPTION"` in the CLI |
| `sb.agent.*` helpers, `Agent(...)` | The [Agents API](../guide/agents-api.md) |
| `Sandbox.custom()`, `run_command()`, `custom_commands` in `template.yaml` | `sandbox.run(name, **kwargs)` with a server-registered command |
| `SandboxPool` | Not planned; create sandboxes per task |
| Per-sandbox VPC, OSS mount, custom domain (`agent_sandbox.extensions`) | The platform has no per-sandbox API for them: VPC is template `vpcConfig`, volumes are control-plane resources, custom domains are account-level |
