# Comparison with Other Sandbox Tools

For current SDK installation, use the [installation guide](install-python.md).

> **Note:** The `abx` commands shown on this page are provided by the Node.js CLI in the `cli` repository ([CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md)). CLI-specific documentation (CLI design, tutorial, reference) lives there too; this repository documents the Python SDK (`agent-sandbox-client`) and the container-side runtime (`agent-sandbox-server`).

This document provides an objective comparison of Agent Sandbox (abx) with other popular sandbox and remote execution platforms: E2B, Modal, and Docker Sandbox.

---

## Positioning and Use Cases

| Platform | Core Positioning | Primary Use Cases |
|----------|-----------------|-------------------|
| **Agent Sandbox (abx)** | Sandbox SDK with pluggable providers. The default provider is Alibaba Cloud Express (FC); others install as plugins | AI agent code execution, cloud or local dev environments, template-driven sandboxes |
| **E2B** | Cloud sandboxes built for AI apps | AI agent tool-use, code interpreters, data analysis in LLM workflows |
| **Modal** | Serverless compute for data/ML pipelines | GPU workloads, batch jobs, model inference, scheduled tasks |
| **Docker Sandbox** | Container-based local/remote isolation | Local development, CI/CD, reproducible environments |

---

## SDK Comparison

The Agent Sandbox column uses the ProviderSandbox extension, imported as Sandbox
in the examples. Root Sandbox / AsyncSandbox and code_interpreter expose the
separate standard contract; interpreter availability depends on that selected entry
and provider. See [E2B migration](migrate-from-e2b.md).

| Dimension | Agent Sandbox | E2B | Modal |
|-----------|-------------|-----|-------|
| **Language** | Python | Python, JS/TS, Kotlin, Go | Python |
| **Install** | [installation guide](install-python.md) | `pip install e2b` | `pip install modal` |
| **Sandbox creation** | `await Sandbox.create()`, or the Modal-style `@sandbox` decorator | `await Sandbox.create()` | `@app.function()` decorator |
| **Sync support** | `Sandbox.create_sync()` | `Sandbox()` (sync class) | N/A (async-native) |
| **Command execution** | `sandbox.commands.run()` | `sandbox.commands.run()` | Remote function call |
| **File operations** | `sandbox.files.read/write/list` | `sandbox.files.read/write/list` | `modal.Volume` mount |
| **Code execution** | `sandbox.run_code()` | `sandbox.run_code()` | Remote function execution |
| **Registered commands** | `sandbox.run(name, **kwargs)` | N/A | N/A |
| **Network access** | `sandbox.network.get_host()` | `sandbox.get_host()` | Built-in URL routing |
| **Terminal (PTY)** | `sandbox.get_terminal()` | `sandbox.terminal.start()` | `modal shell` |
| **E2B migration helper** | `from agent_sandbox import Sandbox` (partial) | Native | N/A |
| **Auth methods** | Depends on the provider. ProviderSandbox uses `ABX_SANDBOX_API_KEY`; Alibaba Cloud Express also uses the official AK/SK names | API Key | Token-based |

### Code Examples

**Agent Sandbox:**

```python
from agent_sandbox import ProviderSandbox as Sandbox

async with await Sandbox.create(template="base") as sb:
    result = await sb.commands.run("python3 -c 'print(\"hello\")'")
    print(result.stdout)
```

**E2B:**

```python
from e2b import Sandbox

sandbox = Sandbox()
result = sandbox.run_code("print('hello')")
print(result.text)
sandbox.kill()
```

**Modal:**

```python
import modal
app = modal.App("example")

@app.function()
def hello():
    print("hello")
```

### Usage Style Comparison

Agent Sandbox supports both **imperative** (E2B style) and **declarative** (Modal style) programming paradigms:

| Dimension | E2B Style (Imperative) | Modal Style (Declarative) |
|-----------|----------------------|-------------------------|
| **Creation** | Manual `Sandbox.create()` | Automatic (`@sandbox` decorator) |
| **Dependency install** | `sb.commands.run("pip install ...")` | Decorator argument `packages=[...]` |
| **Data transfer** | `files.write()` + `files.read()` | Function args and return values auto-serialized |
| **Execution** | `sb.commands.run()` / `sb.run_code()` | Call function directly |
| **Result retrieval** | Parse stdout / read files | Function return value |
| **Lifecycle** | Manual `kill()` or `async with` | Automatically managed |
| **Best for** | Fine-grained control, long-running interactions, multi-step workflows | Simple compute tasks, batch processing, function-as-a-service |

**E2B Style (Imperative) — fine-grained control:**

```python
from agent_sandbox import ProviderSandbox as Sandbox

async with await Sandbox.create() as sb:
    await sb.commands.run("pip install pandas")
    await sb.files.write("/app/data.csv", csv_content)
    result = await sb.commands.run("python3 /app/analyze.py")
    report = await sb.files.read("/app/report.txt")
```

**Modal Style (Declarative) — call like a local function:**

```python
from agent_sandbox.declarative import sandbox

@sandbox(packages=["pandas"])
def analyze(data: list[dict]) -> dict:
    import pandas as pd
    df = pd.DataFrame(data)
    return {"mean": df["value"].mean(), "count": len(df)}

# Called just like a local function — automatically runs in a remote sandbox
result = analyze(my_data)
```

> See [`examples/compat-demos/comparison.py`](../../../examples/compat-demos/comparison.py) for a complete example.

---

## CLI Comparison

| Dimension | abx | e2b CLI | modal CLI |
|-----------|-----|---------|-----------|
| **Install** | [CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md) | `npm i -g @e2b/cli` | `pip install modal` |
| **Runtime** | Node.js (TypeScript) | Node.js | Python (Typer) |
| **Create sandbox** | `abx create` | `e2b sandbox create` | N/A (code-driven) |
| **List sandboxes** | `abx sandbox list` | `e2b sandbox list` | `modal container list` |
| **Connect to sandbox** | `abx connect <id>` | `e2b sandbox connect` | `modal shell` |
| **Template build** | `abx template build` | `e2b template build` | N/A |
| **Template deploy** | `abx template deploy` | `e2b template build --push` | N/A |
| **Auth setup** | Via environment variables (`.env`) | `e2b auth login` | `modal token set` |
| **MCP integration** | `abx mcp install` | N/A | N/A |
| **Secret management** | Via environment variables (`.env`) | N/A | `modal secret create` |

---

## Infrastructure

| Dimension | Agent Sandbox | E2B | Modal | Docker Sandbox |
|-----------|-------------|-----|-------|----------------|
| **Isolation** | Depends on the provider. The default is an Alibaba Cloud FC container; `local-process` is not isolated | Firecracker MicroVM | Container (gVisor) | Container (runc/containerd) |
| **Startup time** | Seconds | ~150ms (MicroVM) | Seconds (cold) / ms (warm) | Seconds |
| **Regions** | Default provider: Alibaba Cloud regions (cn-hangzhou, etc.). Other providers choose their own | US, EU | US (aws-us-east-1, etc.) | Self-hosted |
| **Platform** | Default provider is managed Alibaba Cloud. Plugins can be local or another cloud | Managed (E2B Cloud) | Managed (Modal Cloud) | Self-hosted / Docker Desktop |
| **GPU support** | Via template config | N/A | Native (A10G, A100, H100) | Via NVIDIA Container Toolkit |
| **Max lifetime** | Configurable (up to 86400s) | Configurable | Per-invocation | Unlimited |
| **Pricing** | Alibaba Cloud FC billing | Per-sandbox-second | Per-second compute | Infrastructure cost |

---

## Unique Capabilities of Agent Sandbox

### E2B-shaped API

Agent Sandbox uses E2B-style method names, so E2B code can often be ported with few edits. The standard API follows the pinned Alibaba-supported behavior contract; see the migration guide for backend limits and imports.

```python
# Start of a migration: change the import, then follow the guide
from agent_sandbox import Sandbox
```

See [Migrating from E2B](migrate-from-e2b.md) for the full guide.

### Alibaba Cloud Integration

| Feature | Description |
|---------|-------------|
| **AK/SK Auth** | Native Alibaba Cloud AccessKey authentication |
| **Template build and deploy** | `abx template build` / `abx template deploy` push images to Alibaba Cloud Container Registry and register the template |

VPC, OSS volumes and custom domains are platform settings (template runtime configuration and account-level resources). The Python SDK has no API for them.

### Registered Commands

Functions registered in the sandbox server (`@sandbox.register`, implemented by the Server SDK inside the container) are callable through one API:

```python
result = await sandbox.run("analyze", data="input.csv")
```

This is not available in E2B or Modal.

### MCP Server Integration

Agent Sandbox includes a built-in MCP (Model Context Protocol) Server, enabling AI IDEs (Cursor, Claude Desktop, VS Code) to operate sandboxes directly:

```bash
abx mcp install --target cursor
```

Provides 7 tools: `create_sandbox`, `run_code`, `run_command`, `read_file`, `write_file`, `list_files`, `kill_sandbox`.

### Declarative Sandbox Decorator

```python
from agent_sandbox import sandbox

@sandbox(template="base", timeout=60)
async def my_task():
    ...
```

---

## Other Platforms (Brief)

| Platform | Notes |
|----------|-------|
| **Daytona** | Cloud development environment platform. Transitioned to closed-source in 2026. Previously offered an open-source self-hosted option. |
| **Google Gemini Sandbox** | Code execution sandbox within Google Cloud's Gemini Enterprise Agent Platform (formerly Vertex AI). Managed service, tightly coupled to Google Cloud ecosystem. |
| **Cloudflare Workers** | Uses V8 Isolates for process-level isolation with sub-millisecond cold starts. Focused on edge computing rather than general-purpose sandboxes. |
| **Fly.io Machines** | Firecracker-based ephemeral VMs. Good for running full Linux environments with fast boot times. API-driven, no sandbox-specific SDK. |

---

## Summary

| Consideration | Recommended Platform |
|--------------|---------------------|
| Migrating from E2B to Alibaba Cloud | **Agent Sandbox** — E2B-shaped method names, few code changes (not a drop-in) |
| AI agent with code execution needs | **Agent Sandbox** or **E2B** — purpose-built sandbox SDKs |
| GPU-heavy ML/inference workloads | **Modal** — native GPU support and serverless scaling |
| Local development isolation | **Docker** — industry-standard, self-hosted |
| Alibaba Cloud ecosystem integration | **Agent Sandbox** — AK/SK auth, template build and deploy to ACR |
| MCP-based AI IDE integration | **Agent Sandbox** — built-in MCP Server |

---

## Further Reading

- [Command and SDK map](command-map.md)
- [Migrating from E2B](migrate-from-e2b.md)
- [SDK Usage Guide](sdk-usage.md)
- [CLI Tutorial](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/cli-tutorial.md)
- [MCP Integration](mcp-integration.md)
- [Authentication](authentication.md)
