# Agent Sandbox — Examples

**English** | [中文](README.zh-CN.md)

Examples are split by which package they exercise.

**Client SDK** scripts run on your machine. They create a sandbox or talk to one that is already up: `quickstart/`, `compat-demos/`, `agents/`, `scenarios/`, and `templates/python-hello/call_api.py`.

**Server SDK** code runs inside the sandbox image. It is `commands.py` in `templates/python-hello/` and `templates/agents-cli/`. Those files import `agent_sandbox.server` and call `start(9000)`. They do not create the cloud sandbox.

## Prerequisites

### 1. Install the SDK

```bash
# Full install (recommended — includes the declarative decorator, MCP server, ...)
python -m pip install "agent-sandbox-client[all]==0.4.0a2"

# Or install selectively
python -m pip install "agent-sandbox-client==0.4.0a2"

# From source (run from the python-sdk repository root)
pip install -e ./server-sdk -e ./client-sdk

# The abx CLI is a separate Node.js project (the `cli` repository)
curl -fsSL https://raw.githubusercontent.com/Alibaba-Agent-Sandbox/agent-sandbox/main/install.sh | sh
```

### 2. Configure Credentials

```bash
# Option 1: Environment variable
export ABX_SANDBOX_API_KEY="your-api-key"

# Option 2: CLI config (persisted to ~/.abx/config.toml; requires the abx CLI)
abx config set sandbox_api_key your-api-key

# For the Codex Agent example, also set:
export OPENAI_API_KEY="your-openai-key-here"
```

> **Environment variables:** envd uses direct exec — shell features (`$VAR`, pipes, redirects) require `sh -c '...'`. Use `printenv VAR` to read a variable. See the [Environment Variables guide (EN)](../docs/en/guide/environment-variables.md) | [环境变量指南 (中文)](../docs/zh/guide/environment-variables.md) for details.

## Client SDK examples

## Directory Structure

```
examples/
├── quickstart/                # Client SDK — create and use a sandbox
├── agents/                    # Client SDK — call an Agents API or a cloud sandbox
├── compat-demos/              # Client SDK — E2B-style and Modal-style calls
├── scenarios/                 # Client SDK — local create, exec, read, kill
└── templates/                 # Server SDK — commands.py starts inside the image
    ├── python-hello/commands.py
    ├── python-hello/call_api.py   # Client SDK: HTTP to a server that is already up
    └── agents-cli/commands.py
```

> `templates/` keeps only the minimal `python-hello` **fixture** used by offline
tests.  Official & community templates — content, index (`awesome-templates.yaml`),
releases and CI — live in the single-source-of-truth repository
[`alibaba-agent-sandbox/awesome-templates`](https://github.com/alibaba-agent-sandbox/awesome-templates);
discover and install them with `abx template search` / `abx template launch <name> --yes`.

## Server SDK examples

### templates/ — Server SDK

`commands.py` in [`python-hello`](templates/python-hello/commands.py) and [`agents-cli`](templates/agents-cli/commands.py) is what the image starts. It imports `agent_sandbox.server`.

[`call_api.py`](templates/python-hello/call_api.py) is Client SDK. It talks to a server that is already running (`GET /health`, `GET /capabilities`, `GET /commands`, one upload, one shell). The base URL comes from argv or `ABX_TEMPLATE_URL`; the token comes from `ABX_SERVER_TOKEN`. Request and response shapes are in the [template server HTTP API](../docs/en/guide/template-server-api.md) guide ([中文](../docs/zh/guide/template-server-api.md)).

## Example Catalog

### quickstart/ — Client SDK

| File | Description | Use Case |
|------|-------------|----------|
| [`01_hello.py`](quickstart/01_hello.py) | **Basic sandbox ops** — create, execute commands, lifecycle | SDK onboarding |
| [`02_file_ops.py`](quickstart/02_file_ops.py) | **File operations** — read/write, directories, binary files | Data exchange |
| [`03_web_service.py`](quickstart/03_web_service.py) | **Web service** — start Express server, get public URL | Web dev, API testing |
| [`04_data_analysis.py`](quickstart/04_data_analysis.py) | **Data analysis** — upload CSV, pandas analysis, run_code | Data science |
| [`05_decorator_usage.py`](quickstart/05_decorator_usage.py) | **@sandbox decorator** — declarative remote execution | Simplified calls |

### agents/ — Client SDK

| File | Description | Use Case |
|------|-------------|----------|
| [`codex_agent.py`](agents/codex_agent.py) | **Model code generation** — a real OpenAI-compatible model on `base` | AI programming |
| [`browser_automation.py`](agents/browser_automation.py) | **Browser automation** — Playwright scraping & screenshots | Web scraping |
| [`complete_case.py`](agents/complete_case.py) | **Complete Agents API case** — local server, Codex and Qwen Code, no model key | Agents API |
| [`hosted_codex.py`](agents/hosted_codex.py) | **Hosted Codex client** — one session against a server you already started | Agents API |
| [`hosted_qwen.py`](agents/hosted_qwen.py) | **Hosted Qwen client** — one session against a server you already started | Agents API |
| [`local_files_and_session.py`](agents/local_files_and_session.py) | **Files plus one Codex session** — local server, a local program named `codex` on `PATH`, no API key | Agents API |

### compat-demos/ — Client SDK

| File | Description | Use Case |
|------|-------------|----------|
| [`e2b_data_analysis.py`](compat-demos/e2b_data_analysis.py) | **E2B-style data analysis** | E2B migration |
| [`e2b_web_scraper.py`](compat-demos/e2b_web_scraper.py) | **E2B-style web scraping** | E2B migration |
| [`modal_compute.py`](compat-demos/modal_compute.py) | **Modal-style scientific computing** | Modal migration |
| [`modal_data_analysis.py`](compat-demos/modal_data_analysis.py) | **Modal-style data analysis** | Modal migration |
| [`comparison.py`](compat-demos/comparison.py) | **E2B vs Modal style comparison** | API style selection |

## Running Examples

```bash
# Basic example
python examples/quickstart/01_hello.py

# Data analysis
python examples/quickstart/04_data_analysis.py

# @sandbox decorator
python examples/quickstart/05_decorator_usage.py

# E2B-style API usage
python examples/compat-demos/e2b_data_analysis.py
```

## Core API Reference

### Execution Methods

```python
from agent_sandbox import ProviderSandbox as Sandbox

async with await Sandbox.create(template="base", sandbox_api_key="...") as sandbox:

    # 1. Bare shell — sandbox.commands.run(cmd)
    proc = await sandbox.commands.run("echo hello")
    print(proc.stdout, proc.exit_code)

    # 2. Code interpreter — sandbox.run_code(code)
    code_result = await sandbox.run_code("print(1 + 1)")
    print(code_result.text)   # "2"

    # 3. Named command — sandbox.run(name, **kwargs)
    #    POST /commands/hello on the template's SandboxServer
    value = await sandbox.run("hello", name="Alice")
    print(value)              # command return value
```

> **Note:** `sandbox.run(name, **kwargs)` calls a command registered in the template's server; it never runs a shell string. Use `sandbox.commands.run(cmd)` for that.

### File Operations

```python
    # Write and read files
    await sandbox.files.write("/app/data.txt", "content")
    content = await sandbox.files.read("/app/data.txt")
```

### Network

```python
    # Get public URL for a port
    url = sandbox.network.get_url(3000)
```

### Declarative Decorator

```python
from agent_sandbox.declarative import sandbox

@sandbox(template="code-interpreter", packages=["numpy"])
def compute(n: int) -> float:
    import numpy as np
    return float(np.random.random(n).mean())

result = compute(1000)  # runs in a remote sandbox automatically
```

## Reproduce the examples

Run `python examples/run_examples_e2e.py` for local real-server/file/process examples. Codex/Qwen executables in that local run are explicitly controlled protocol fixtures; this does not test a model service. Run the cloud scripts individually with your provider credentials; the local runner lists these as `needs-provider`, never passes.

`agents/codex_agent.py` requires a real `OPENAI_API_KEY`; optional `OPENAI_BASE_URL` and `OPENAI_MODEL` select a compatible model. It does not substitute simulated responses. `agents/browser_automation.py` installs real Chromium and defaults to an owned HTTP page; set `BROWSER_URL` to exercise your external page.

`compat-demos/e2b_import_migration.py` uses the standard synchronous interpreter client and the E2B configuration names described in its docstring. The other cloud examples use `ProviderSandbox` or `@sandbox` and `ABX_SANDBOX_API_KEY`. See [cloud examples](../docs/en/guide/cloud-examples.md) for the complete commands.
