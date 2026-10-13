# Easy Sandbox

**English** | [中文](README.zh-CN.md)

<!-- badges -->
[![CI](https://github.com/Easy-Sandbox/python-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/Easy-Sandbox/python-sdk/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/easy-sandbox)](https://pypi.org/project/easy-sandbox/)
[![Python 3.10+](https://img.shields.io/pypi/pyversions/easy-sandbox)](https://pypi.org/project/easy-sandbox/)
[![License](https://img.shields.io/github/license/easy-sandbox/python-sdk)](LICENSE)

> Cloud sandboxes for AI agents — create, execute, and manage isolated environments in seconds.

**Easy Sandbox** is a Python SDK for the Alibaba Cloud FC Agent Sandbox service.
It is **E2B-protocol compatible** with extensions for the Alibaba Cloud ecosystem (OSS, VPC, custom domains).

This repository (`python-sdk`) contains the **Python SDK**, published as two lock-step PyPI
distributions. The `ebx` command-line tool is a separate Node.js project that lives in the
[`cli`](https://github.com/Easy-Sandbox/easy-sandbox) repository (see [Related: the ebx CLI](#related-the-ebx-cli)).

| Folder | PyPI distribution | Import path | Purpose |
|--------|-------------------|-------------|---------|
| [`client-sdk/`](client-sdk/) | `easy-sandbox` | `easy_sandbox` | Async client SDK: `Sandbox`, files, commands, code interpreter, templates API, declarative `@sandbox`, MCP server, E2B compatibility layer |
| [`server-sdk/`](server-sdk/) | `easy-sandbox-server` | `easy_sandbox.server` | Container-side runtime: the persistent HTTP service (default port 9000) that runs *inside* a sandbox image |

Both distributions share the `easy_sandbox` namespace (the client owns `easy_sandbox/__init__.py`,
the server only ships `easy_sandbox/server/`) and are **released in lockstep** with the same version number.

---

## Features

- **Async-first SDK** — `Sandbox.create()`, shell execution, code interpretation, file I/O, port forwarding, and WebSocket streaming.
- **Three execution primitives** — `sandbox.run()` (bare shell), `sandbox.run_code()` (code interpreter), `sandbox.custom()` (named commands with A/B resolution).
- **Template system** — reusable sandbox images (Python, Node, browser automation, AI agent harnesses, …).
- **MCP server** — expose sandbox operations as MCP tools for LLM agents.
- **Declarative decorator** — `@sandbox` turns a plain function into a remote sandbox execution with automatic serialisation.
- **Session persistence** — save and restore sandbox state across runs.
- **E2B compatibility layer** — drop-in replacement for projects already using the E2B SDK.
- **Agents API** — in-sandbox HTTP sessions. Codex and Qwen Code are supported today. Install a CLI when you call it; the base image does not carry both. Guide and complete case: [Agents API](docs/en/guide/agents-api.md).

## Installation

```bash
# Core client SDK only
pip install easy-sandbox

# + Alibaba Cloud template API (template deploy / template create)
pip install "easy-sandbox[alicloud]"

# Everything (MCP + fast JSON + sessions + declarative + alicloud + server)
pip install "easy-sandbox[all]"

# Container-side runtime (install this inside your sandbox image)
pip install easy-sandbox-server
pip install playwright                       # only if you enable the browser capability group

# Development (from the repository root; includes test & lint tooling for both packages)
pip install -e ./server-sdk -e "./client-sdk[dev]"
```

`easy-sandbox` depends on `easy-sandbox-server` of the same version, so `pip install easy-sandbox` also provides `easy_sandbox.server` (needed locally by the `@sandbox` decorator's server proxy). The `[server]` extra is kept as a harmless alias.

> **Upgrading from 0.2.x?** An in-place `pip install -U easy-sandbox` can leave `easy_sandbox.server` broken; run `pip install --force-reinstall --no-deps easy-sandbox-server` (see [Migrating from 0.2](docs/en/guide/migrating-from-0.2.md)).

The `ebx` CLI is no longer part of the Python package (there is no `[cli]` extra and no `ebx`
console script); it is distributed from the [`cli`](https://github.com/Easy-Sandbox/easy-sandbox) repository
(see [Related: the ebx CLI](#related-the-ebx-cli)).

## Quick Start

```python
import asyncio
from easy_sandbox import Sandbox

async def main():
    async with await Sandbox.create(template="python-base") as sandbox:

        # 1. Bare shell — sandbox.run(cmd)
        proc = await sandbox.run("echo 'Hello from sandbox!'")
        print(proc.stdout)          # Hello from sandbox!
        print(proc.exit_code)       # 0

        # 2. Code interpreter — sandbox.run_code(code)
        result = await sandbox.run_code("print(2 ** 10)")
        print(result.text)          # 1024

        # 3. Named command — sandbox.custom(name, **kwargs)
        #    Resolves template custom_commands (A) then SandboxServer (B)
        cmd = await sandbox.custom("hello", name="Alice")
        print(cmd.value)            # return value of the command
        print(cmd.source)           # "template" or "server"

        # 4. File operations
        await sandbox.files.write("/tmp/data.txt", "content")
        content = await sandbox.files.read("/tmp/data.txt")

        # 5. Port access
        url = sandbox.network.get_url(3000)

asyncio.run(main())
```

> **E2B compatibility:** `sandbox.commands.run(cmd)` is the low-level entry that `sandbox.run()` delegates to. Existing E2B code calling `sandbox.commands.run()` continues to work.

## Execution API

Easy Sandbox provides three execution methods, each for a distinct use case:

| Method | Purpose | Returns |
|--------|---------|---------|
| `sandbox.run(cmd)` | Execute a bare shell command | `ProcessResult` — `.stdout`, `.stderr`, `.exit_code` |
| `sandbox.run_code(code)` | Execute code via the code interpreter | `CodeResult` — `.text`, `.stdout`, `.stderr` |
| `sandbox.custom(name, **kw)` | Execute a named command (template A / server B) | `CommandResult` — `.value`, `.source`, `.exit_code` |

**`sandbox.custom()` — A/B Resolution:**

1. **Template** (mechanism A): Looks up `custom_commands` in `template.yaml`, fills `{placeholder}` tokens from kwargs (shlex-quoted), and runs as a shell command.
2. **Server** (mechanism B): If not found in the template, sends `POST /commands/{name}` to the in-sandbox SandboxServer.

```python
# Template command (A) — defined in template.yaml
result = await sandbox.custom("greet", name="World")
print(result.value)     # stdout output (stripped)
print(result.source)    # "template"

# Server command (B) — registered on SandboxServer
result = await sandbox.custom("analyze", data="input.csv")
print(result.value)     # Python function return value (JSON)
print(result.source)    # "server"
```

> **Environment variables:** envd uses direct exec — shell features (`$VAR`, pipes, redirects) require `sh -c '...'`. Use `printenv VAR` to read a variable. See the [Environment Variables guide (EN)](docs/en/guide/environment-variables.md) | [环境变量指南 (中文)](docs/zh/guide/environment-variables.md) for details.

## Templates

Official and community templates live in the
[`Easy-Sandbox/awesome-templates`](https://github.com/Easy-Sandbox/awesome-templates)
repository — the single source of truth for template content, the index, and
publishing. The index is consumed by the `ebx template search|install` commands
([Related: the ebx CLI](#related-the-ebx-cli)); the `template.yaml` contract that
templates follow is defined in the [Template YAML Spec](docs/en/reference/template-yaml-spec.md).

[`examples/templates/`](examples/templates/) only keeps a minimal
`python-hello` **fixture** for offline tests — it is not a publishing source.
See [examples/templates/README.md](examples/templates/README.md) for the
fixture contract and index behaviour (caching, offline fallback, pinned refs).

## Architecture

```mermaid
graph TB
    L6["L6 Agent — MCP server, built-in agents"]
    L5["L5 Declarative — @sandbox decorator"]
    L4["L4 API — Sandbox, Files, Code, Commands"]
    L3["L3 Extensions — OSS, VPC, Custom Domains"]
    L2["L2 Protocol — E2B-compat REST + WebSocket"]
    L1["L1 Transport — HTTP/2, API Key, AK/SK"]
    GW["Alibaba Cloud FC"]

    L6 --> L5 --> L4 --> L3 --> L2 --> L1 --> GW
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
| Build & Deploy | [Build & Deploy](docs/en/guide/build-and-deploy.md) |
| Declarative Usage | [Declarative Usage](docs/en/guide/declarative-usage.md) |
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

## Related: the ebx CLI

The `ebx` command-line tool (`@easy-sandbox/cli`, Node.js) is developed in the
[`cli`](https://github.com/Easy-Sandbox/easy-sandbox) repository. It shares sandboxes, templates and
credentials with this SDK. Its installation, command reference, tutorials, MCP server
commands and the Agent Skill (`SKILL.md`) are documented there:

- [CLI README](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/README.md) — installation (`npm install -g @easy-sandbox/cli`)
- [CLI Tutorial](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/cli-tutorial.md) · [CLI Reference](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/reference/cli-reference.md)
- [Agent Skill Installation & Distribution](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/agent-skill-installation.md)

## Contributing

We welcome contributions! Please read the [Contributing Guide](.github/CONTRIBUTING.md) to get started.

## License

[Apache-2.0](LICENSE) — see [`NOTICE`](NOTICE) for copyright information.
