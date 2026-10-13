# Agent Sandbox — Examples

**English** | [中文](README.zh-CN.md)

This directory contains complete usage examples for the Agent Sandbox SDK, covering everything from basic operations to advanced scenarios.

## Prerequisites

### 1. Install the SDK

```bash
# Full install (recommended — includes the declarative decorator, MCP server, ...)
pip install "agent-sandbox[all]"

# Or install selectively
pip install "agent-sandbox[declarative]"   # @sandbox decorator only

# From source (run from the python-sdk repository root)
pip install -e ./server-sdk -e ./client-sdk

# The abx CLI is a separate Node.js project (the `cli` repository)
npm install -g @agent-sandbox/cli
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

## Directory Structure

```
examples/
├── quickstart/                # Quick start examples
│   ├── 01_hello.py            # Basic sandbox ops — create, execute, lifecycle
│   ├── 02_file_ops.py         # File operations — read/write, directory management
│   ├── 03_web_service.py      # Web service — start server, get public URL
│   ├── 04_data_analysis.py    # Data analysis — CSV upload, pandas analysis
│   └── 05_decorator_usage.py  # @sandbox decorator — declarative remote execution
├── agents/                    # Agent integration examples
│   ├── codex_agent.py         # Cloud Codex sandbox — needs a provider and OPENAI_API_KEY
│   ├── browser_automation.py  # Browser automation — needs a provider
│   ├── hosted_codex.py        # Agents API client for a server that is already up
│   ├── hosted_qwen.py         # Agents API client for Qwen Code
│   └── local_files_and_session.py  # Local server, local codex program, no model key
├── compat-demos/              # E2B/Modal compatibility demos
│   ├── e2b_data_analysis.py   # E2B-style data analysis
│   ├── e2b_web_scraper.py     # E2B-style web scraping
│   ├── modal_compute.py       # Modal-style scientific computing
│   ├── modal_data_analysis.py # Modal-style data analysis
│   └── comparison.py          # E2B vs Modal style comparison
└── templates/                 # Offline fixtures (NOT the publishing source)
    ├── python-hello/          # Publishable templates: github.com/alibaba-agent-sandbox/awesome-templates
    └── agents-cli/            # Agents API for Codex and Qwen Code; CLIs are not preinstalled
```

> `templates/` keeps only the minimal `python-hello` **fixture** used by offline
tests.  Official & community templates — content, index (`awesome-templates.yaml`),
releases and CI — live in the single-source-of-truth repository
[`alibaba-agent-sandbox/awesome-templates`](https://github.com/alibaba-agent-sandbox/awesome-templates);
discover and install them with `abx template search` / `abx template install <name>`.

[`templates/python-hello/call_api.py`](templates/python-hello/call_api.py) talks to a server that is already running (`GET /health`, `GET /capabilities`, `GET /commands`, one upload, one shell). The base URL comes from argv or `ABX_TEMPLATE_URL`; the token comes from `ABX_SERVER_TOKEN`. Request and response shapes are in the [template server HTTP API](../docs/en/guide/template-server-api.md) guide ([中文](../docs/zh/guide/template-server-api.md)).

## Example Catalog

### quickstart/ — Getting Started

| File | Description | Use Case |
|------|-------------|----------|
| [`01_hello.py`](quickstart/01_hello.py) | **Basic sandbox ops** — create, execute commands, lifecycle | SDK onboarding |
| [`02_file_ops.py`](quickstart/02_file_ops.py) | **File operations** — read/write, directories, binary files | Data exchange |
| [`03_web_service.py`](quickstart/03_web_service.py) | **Web service** — start Express server, get public URL | Web dev, API testing |
| [`04_data_analysis.py`](quickstart/04_data_analysis.py) | **Data analysis** — upload CSV, pandas analysis, run_code | Data science |
| [`05_decorator_usage.py`](quickstart/05_decorator_usage.py) | **@sandbox decorator** — declarative remote execution | Simplified calls |

### agents/ — Agent Integration

| File | Description | Use Case |
|------|-------------|----------|
| [`codex_agent.py`](agents/codex_agent.py) | **Codex Agent** — AI code generation & execution | AI programming |
| [`browser_automation.py`](agents/browser_automation.py) | **Browser automation** — Playwright scraping & screenshots | Web scraping |
| [`complete_case.py`](agents/complete_case.py) | **Complete Agents API case** — local server, Codex and Qwen Code, no model key | Agents API |
| [`hosted_codex.py`](agents/hosted_codex.py) | **Hosted Codex client** — one session against a server you already started | Agents API |
| [`hosted_qwen.py`](agents/hosted_qwen.py) | **Hosted Qwen client** — one session against a server you already started | Agents API |
| [`local_files_and_session.py`](agents/local_files_and_session.py) | **Files plus one Codex session** — local server, a local program named `codex` on `PATH`, no API key | Agents API |

### compat-demos/ — Compatibility Layer

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
from agent_sandbox import Sandbox

async with await Sandbox.create(template="base", api_key="...") as sandbox:

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
