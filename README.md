# Agent Sandbox

[Template workflows](docs/en/guide/template-workflows.md): explicit services, exact provider operations and independently verified consumer paths.

**English** | [中文](README.zh-CN.md)

[Standard E2B migration contract](docs/en/guide/migrate-from-e2b.md)

<!-- badges -->
[![CI](https://github.com/alibaba-agent-sandbox/python-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/alibaba-agent-sandbox/python-sdk/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/agent-sandbox/python-sdk)](LICENSE)

> Cloud sandboxes for AI agents — create, execute, and manage isolated environments in seconds.

**Agent Sandbox** is a Python SDK for sandboxes. The default provider is Alibaba Cloud Express (`alicloud-express`, Function Compute). OpenSandbox, the container edition, CubeSandbox, and E2B are catalog `node` plugins in `awesome-providers` (`provider.mjs`). Install one with `abx provider install alibaba-agent-sandbox/awesome-providers//<id> --allow-unpinned --yes` (or `python -m agent_sandbox.providers install registry:<id> --yes`). After that, both `abx --provider <id>` and `ProviderSandbox.create(provider="<id>")` use it. The Python SDK reaches a `node` provider through the local engine (`abx provider engine serve`; `abx` on `PATH` or `ABX_BIN`). The CLI loads Express plus installed `node`, `exec` and `rest` plugins. It is the
standard sync/async runtime and Template client. Project provider/server template workflows use
`abx template build|deploy` from the CLI. The SDK uses E2B-shaped method names so that E2B code
ports with few changes; the standard API follows Alibaba-supported E2B behavior (see [Migrate from E2B](docs/en/guide/migrate-from-e2b.md)).

This repository (`python-sdk`) contains the **Python SDK**, packaged as two lock-step distributions. The `abx` command-line tool is a separate Node.js project that lives in the
[`agent-sandbox`](https://github.com/alibaba-agent-sandbox/agent-sandbox) repository (see [Related: the abx CLI](#related-the-abx-cli)).

| Folder | Distribution | Import path | Purpose |
|--------|-------------------|-------------|---------|
| [`client-sdk/`](client-sdk/) | `agent-sandbox-client` | `agent_sandbox` | Sync/async client SDK: `Sandbox`, `AsyncSandbox`, `ProviderSandbox`, files, commands, code interpreter, named commands, declarative `@sandbox`, Agents API client, MCP server, E2B migration helper |
| [`server-sdk/`](server-sdk/) | `agent-sandbox-server` | `agent_sandbox.server` | Container-side runtime: the persistent HTTP service (default port 9000) that runs *inside* a sandbox image |

Both distributions share the `agent_sandbox` namespace (the client owns `agent_sandbox/__init__.py`,
the server only ships `agent_sandbox/server/`) and are **versioned in lockstep** with the same version number.

**Client SDK** runs on your machine: create a sandbox and use it. Guide: [Client SDK](docs/en/guide/client-sdk.md). Examples: `examples/quickstart/`, `examples/compat-demos/`, `examples/agents/`, `examples/scenarios/`.

**Server SDK** runs inside the sandbox image: the HTTP service the image starts. Guide: [Server SDK](docs/en/guide/server-sdk.md). Examples: `examples/templates/python-hello/commands.py`, `examples/templates/agents-cli/commands.py`.

## Sites

| Site | URL |
|---|---|
| Official site | https://www.agent-sandbox.cn |
| Provider registry | https://registry.agent-sandbox.cn |

The installer fetches the catalog index at `https://registry.agent-sandbox.cn/providers/index.json`. `ABX_PROVIDER_REGISTRY` overrides that URL.

---

Provider management operations are available through `agent_sandbox.providers.commands`; see the [provider command guide](docs/en/guide/provider-commands.md).

## Client SDK

- **Sync and async standard clients** — `Sandbox.create()` and `AsyncSandbox.create()`, shell execution, code interpretation, file I/O, port forwarding, and WebSocket streaming.
- **Three execution primitives** — `sandbox.commands.run()` (bare shell), `sandbox.run_code()` (code interpreter), `sandbox.run("name", **kwargs)` (a command the Server SDK registered).
- **MCP server** — expose sandbox operations as MCP tools for LLM agents.
- **Declarative decorator** — `@sandbox` turns a plain function into a remote sandbox execution with automatic serialisation.
- **Session persistence** — save and restore sandbox state across runs.
- **Standard sync/async clients** — `agent_sandbox` exports the standard Sandbox and AsyncSandbox; see [Migrate from E2B](docs/en/guide/migrate-from-e2b.md).

## Server SDK

- **In-image HTTP service** — `commands.py` imports `agent_sandbox.server` and calls `start(9000)`.
- **Registered commands** — `@command` functions become routes the Client SDK calls with `sandbox.run`.
- **Agents API** — Codex and Qwen Code HTTP sessions inside the sandbox. Install a CLI when you call it. Guide: [Agents API](docs/en/guide/agents-api.md).
- **Templates** — the image and `template.yaml` are built and deployed with `abx template build|deploy`.

## Installation

Current version 0.3.0 is not on PyPI. Use the [paired source installation guide](docs/en/guide/install-python.md); both source URLs must use the same commit.

```bash
# Client and matching runtime
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=client-sdk"

# Optional extras (MCP + fast JSON + sessions + declarative)
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client[all] @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=client-sdk"

# Container-side runtime (install this inside your sandbox image)
python -m pip install "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=server-sdk"
pip install playwright                       # only if you enable the browser capability group

# Development (from the repository root; includes test & lint tooling for both packages)
pip install -e ./server-sdk -e "./client-sdk[dev]"
```

Do not run `pip install agent-sandbox`. That name on PyPI is an unrelated project. This client is `agent-sandbox-client`.

`agent-sandbox-client` depends on `agent-sandbox-server` of the same version, so installing the [paired sources](docs/en/guide/install-python.md) also provides `agent_sandbox.server` (needed locally by the `@sandbox` decorator's server proxy).

The `abx` CLI is no longer part of the Python package (there is no `[cli]` extra and no `abx`
console script); it is distributed from the [`agent-sandbox`](https://github.com/alibaba-agent-sandbox/agent-sandbox) repository
(see [Related: the abx CLI](#related-the-abx-cli)).

## Quick Start

Configure `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL`, `ABX_SANDBOX_DOMAIN`. Replace E2B imports as described in the [migration guide](docs/en/guide/migrate-from-e2b.md).

```python
from agent_sandbox.code_interpreter import Sandbox

sandbox = Sandbox.create(template="code-interpreter-v1")
try:
    print(sandbox.commands.run("printf hello").stdout)
    print(sandbox.run_code("1 + 1").text)
finally:
    sandbox.kill()
```

## Provider and server extensions


Set `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and `ABX_SANDBOX_DOMAIN` before creating a sandbox. This snippet uses `python-base` because that image registers `hello`. `Sandbox.create()` with no template uses `base`.

```python
import asyncio
from agent_sandbox import ProviderSandbox as Sandbox

async def main():
    async with await Sandbox.create(template="python-base") as sandbox:

        # 1. Bare shell — sandbox.commands.run(cmd)
        proc = await sandbox.commands.run("echo 'Hello from sandbox!'")
        print(proc.stdout)          # Hello from sandbox!
        print(proc.exit_code)       # 0

        # 2. Code interpreter — sandbox.run_code(code)
        result = await sandbox.run_code("print(2 ** 10)")
        print(result.text)          # 1024

        # 3. Named command — sandbox.run(name, **kwargs)
        #    POST /commands/hello on the in-sandbox SandboxServer
        greeting = await sandbox.run("hello", name="Alice")
        print(greeting)             # the registered function's return value

        # 4. File operations
        await sandbox.files.write("/tmp/data.txt", "content")
        content = await sandbox.files.read("/tmp/data.txt")

        # 5. Port access
        url = sandbox.network.get_url(3000)

asyncio.run(main())
```

## Execution API

Three execution methods, each for a distinct use case:

| Method | Purpose | Returns |
|--------|---------|---------|
| `sandbox.commands.run(cmd)` | Execute a bare shell command (raw exec) | `ProcessResult` — `.stdout`, `.stderr`, `.exit_code` |
| `sandbox.run_code(code)` | Execute code via the code interpreter | `CodeResult` — `.text`, `.stdout`, `.stderr` |
| `sandbox.run(name, **kw)` | Call a command registered in the sandbox server | the registered function's JSON return value |

**Named commands** have one mechanism: server-side registered commands. A command is registered with
`@sandbox.register` (or `CommandRegistry`) inside the template, and `sandbox.run("name", **kwargs)` sends
`POST /commands/name` to the in-sandbox SandboxServer. An unknown name raises `CommandNotFoundError`;
`await sandbox.list_commands()` lists what the server has registered. See
[Declarative Usage](docs/en/guide/declarative-usage.md).

> **Environment variables:** envd uses direct exec — shell features (`$VAR`, pipes, redirects) require `sh -c '...'`. Use `printenv VAR` to read a variable. See the [Environment Variables guide (EN)](docs/en/guide/environment-variables.md) | [环境变量指南 (中文)](docs/zh/guide/environment-variables.md) for details.

## Templates

Official and community templates live in the
[`alibaba-agent-sandbox/awesome-templates`](https://github.com/alibaba-agent-sandbox/awesome-templates)
repository — the single source of truth for template content, the index, and
publishing. The index is consumed by the `abx template search|install` commands
([Related: the abx CLI](#related-the-abx-cli)); the `template.yaml` contract that
templates follow is defined in the [Template YAML Spec](docs/en/reference/template-yaml-spec.md).

[`examples/templates/`](examples/templates/) only keeps a minimal
`python-hello` **fixture** for offline tests — it is not a publishing source.
See [examples/templates/README.md](examples/templates/README.md) for the
fixture contract and index behaviour (caching, offline fallback, pinned refs).

## Architecture

```mermaid
graph TB
    L5["L5 Agent — MCP server, Agents API client"]
    L4["L4 Declarative — @sandbox decorator"]
    L3["L3 API — Sandbox, Files, Code, Commands"]
    L2["L2 Protocol — envd REST + WebSocket"]
    L1["L1 Transport — HTTP/2, API Key, envd token"]
    GW["Alibaba Cloud FC"]

    L5 --> L4 --> L3 --> L2 --> L1 --> GW
```

Lower layers never import upper layers. Full design: [`docs/en/design/architecture.md`](docs/en/design/architecture.md).

## Documentation

> Full documentation index: [`docs/README.md`](docs/README.md) (bilingual navigation)

### Tutorials & Guides

| Guide | Link |
|-------|------|
| Getting Started | [Getting Started](docs/en/guide/getting-started.md) |
| Best Practices | [Best Practices](docs/en/guide/best-practices.md) |
| Accessibility | [Accessibility](ACCESSIBILITY.md) |
| File and command controls | [File and command controls](docs/en/guide/file-and-command-controls.md) |
| Hosted agents | [Hosted agents](docs/en/guide/hosted-agents.md) |
| SDK Usage | [SDK Usage](docs/en/guide/sdk-usage.md) |
| Authentication | [Authentication](docs/en/guide/authentication.md) |
| Environment Variables | [Environment Variables](docs/en/guide/environment-variables.md) |
| Authoring Templates | [Authoring Templates](docs/en/guide/authoring-templates.md) |
| Build & Deploy (CLI) | [Build & Deploy](docs/en/guide/build-and-deploy.md) |
| Declarative Usage | [Declarative Usage](docs/en/guide/declarative-usage.md) |
| Binary MCP files | [Upload/download](docs/en/guide/mcp-binary-files.md) |
| Background MCP tasks | [Reconnectable tasks](docs/en/guide/mcp-background-tasks.md) |
| MCP Integration | [MCP Integration](docs/en/guide/mcp-integration.md) |
| Session Persistence | [Session Persistence](docs/en/guide/session-persistence.md) |
| Migrate from E2B | [Migrate from E2B](docs/en/guide/migrate-from-e2b.md) |
| Troubleshooting | [Troubleshooting](docs/en/guide/troubleshooting.md) |

### Reference

| Document | Link |
|----------|------|
| API Reference | [API Reference](docs/en/reference/api-reference.md) |
| Configuration | [Configuration](docs/en/reference/configuration.md) |
| Error Codes | [Error Codes](docs/en/reference/error-codes.md) |
| Template YAML Spec | [Template YAML Spec](docs/en/reference/template-yaml-spec.md) |

### Design & Architecture

| Document | Link |
|----------|------|
| Design Index | [Design Index](docs/en/DESIGN.md) |
| Architecture | [Architecture](docs/en/design/architecture.md) |
| SDK API Design | [SDK API Design](docs/en/design/sdk-api-design.md) |
| Template System | [Template System](docs/en/design/template-system.md) |

### Other Resources

| Resource | Link |
|----------|------|
| Changelog | [CHANGELOG.md](CHANGELOG.md) |
| Contributing Guide | [CONTRIBUTING.md](.github/CONTRIBUTING.md) |
| License | [Apache-2.0](LICENSE) |
| Examples | [examples/](examples/) |
| SDK skill | [agent-sandbox-sdk/SKILL.md](agent-sandbox-sdk/SKILL.md) — how an agent writes a client and a template |

## Related: the abx CLI

The `abx` command-line tool (`@agent-sandbox/cli`, Node.js) is developed in the
[`agent-sandbox`](https://github.com/alibaba-agent-sandbox/agent-sandbox) repository. It shares sandboxes, templates and
credentials with this SDK. Its installation, command reference, tutorials, MCP server
commands and the Agent Skill (`SKILL.md`) are documented there:

- [CLI README](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/README.md) — installation ([CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md))
- [CLI Tutorial](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/cli-tutorial.md) · [CLI Reference](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/cli-reference.md)
- [Agent Skill Installation & Distribution](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/agent-skill-installation.md)

Named commands support native `list[str]` JSON arguments. See the [server API guide](docs/en/guide/template-server-api.md#string-array-command-arguments) for validation and server compatibility.

## Contributing

We welcome contributions! Please read the [Contributing Guide](.github/CONTRIBUTING.md) to get started.

## License

[Apache-2.0](LICENSE) — see [`NOTICE`](NOTICE) for copyright information.

[Builtin runtime architecture and Python engine migration](docs/en/design/builtin-data-plane.md).

Provider-owned pause/resume and Snapshot commands share one implementation across CLI and SDK; see the [registration and usage guide](docs/en/guide/provider-commands.md).

Current API / 当前接口: [development contract](docs/en/guide/current-api.md).
