# Easy Sandbox — Design Document Index

> **Version**: v2.0 | **Last Updated**: 2026-09-24
>
> This document serves as the entry point and index for all Easy Sandbox design documentation. Detailed designs live in the specialized topic documents under [`design/`](design/).

---

## Project Overview

**Easy Sandbox** (`easy-sandbox` on PyPI) is a Python SDK for the Alibaba Cloud FC Agent Sandbox service. It is **E2B-protocol compatible** with extensions for the Alibaba Cloud ecosystem (OSS, VPC, custom domains).

This repository holds the Python SDK as two lock-step PyPI distributions — `easy-sandbox` (`client-sdk/`, import `easy_sandbox`) and `easy-sandbox-server` (`server-sdk/`, import `easy_sandbox.server`, the container-side runtime). The `ebx` CLI is a Node.js/TypeScript project in the `cli` repository, which holds the CLI's own design and guide documents (see [Related: the ebx CLI](#related-the-ebx-cli)).

### Core Principles

1. **E2B Protocol Compatibility** — L2 protocol layer is compatible with the E2B data plane protocol; a migration helper layer (`from easy_sandbox.compat import Sandbox`) eases migration for existing E2B users
2. **AI-First** — Natural language sandbox creation, MCP Server as a first-class citizen, built-in Agent tooling
3. **Zero Configuration Defaults** — Works out of the box; from install to first sandbox in ≤ 3 lines of code

### Quick Start

```bash
pip install easy-sandbox
export SANDBOX_API_KEY=your-api-key
```

```python
from easy_sandbox import Sandbox

async with await Sandbox.create(template="base") as sb:
    result = await sb.run_code("print('Hello, Easy Sandbox!')")
    print(result.text)
```

---

## Architecture Overview

The SDK follows a strict layered architecture — lower layers never import upper layers:

```mermaid
graph TB
    subgraph Upper["Upper Layers"]
        Agent["Agent/MCP — MCP server, builtin agents, tool defs"]
        Decl["Declarative — @sandbox decorator"]
        Compat["Compat — E2B compatibility shim"]
        Ext["Extensions — OSS, VPC, domain"]
    end
    subgraph Core["Core Layers"]
        L3["API — Sandbox, files, code, commands, network, image"]
        L2["Protocol — Sandbox lifecycle, filesystem, process, terminal, port"]
        L1["Transport — HTTP, WebSocket, auth, codec, streaming"]
        L0["Models + Utils — Pydantic models, errors, config, async bridge"]
    end

    Agent --> L3
    Decl --> L3
    Compat --> L3
    Ext --> L3
    L3 --> L2 --> L1 --> L0
```

For the full architecture breakdown, see [Architecture Design](design/architecture.md).

---

## Design Topic Index

Each topic below has its own dedicated design document with complete specifications.

### Core Design

| Topic | Document | Summary |
|-------|----------|---------|
| **System Architecture** | [architecture.md](design/architecture.md) | Six-layer architecture, inter-layer dependencies, dual API layers (Platform API vs Sandbox envd API) |
| **SDK API Design** | [sdk-api-design.md](design/sdk-api-design.md) | Sandbox class, file operations, code execution, commands, network, image builder, session management |
| **Sandbox Type System** | [sandbox-types.md](design/sandbox-types.md) | Ephemeral sandboxes (implemented), persistent sandboxes (future), sandbox lifecycle |
| **Providers and Credentials** | [providers-and-credentials.md](design/providers-and-credentials.md) | One environment variable per configuration key, precedence, provider plugins (`ebx provider ...`), install/trust model, EPP/1 protocol, E8xxx errors; review log in [providers-and-credentials-review.md](design/providers-and-credentials-review.md) |

### Templates

| Topic | Document | Summary |
|-------|----------|---------|
| **Template System** | [template-system.md](design/template-system.md) | Template tiers, GitHub tarball distribution, `template.yaml` specification, custom commands, versioning, marketplace architecture |

### AI & Agent Integration

| Topic | Document | Summary |
|-------|----------|---------|
| **MCP Server** | [mcp-server.md](design/mcp-server.md) | 7 P0 MCP tools, STDIO + Streamable HTTP transports, FC deployment artifact, session binding |
| **Built-in Agents** | [built-in-agents.md](design/built-in-agents.md) | Sandbox-side `AgentModule` sugar over `commands.run()`; agents ship in dedicated templates — the base image preinstalls no agent CLI (the CLI-side guide is [BYO Agent Integration](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/byo-agent-integration.md) in the `cli` repository) |

### Server & Infrastructure

| Topic | Document | Summary |
|-------|----------|---------|
| **Server API** | [server-api.md](design/server-api.md) | Sandbox Server SDK routes, capability groups, browser instance architecture |

### Maintainer Design Documents (English only)

Working design documents for the provider, capability, server-v2 and agents-API workstreams. They have no Chinese counterpart.

| Topic | Document | Summary |
|-------|----------|---------|
| **Agents API** | [agents-api.md](design/agents-api.md), [review](design/agents-api-review.md) | Hosting coding agents in Easy Sandbox; the CLI follow-ups are specified in [agents-api-cli-followups.md](design/agents-api-cli-followups.md) |
| **Fine-grained capabilities** | [fine-grained-capabilities.md](design/fine-grained-capabilities.md), [review](design/fine-grained-capabilities-review.md) | Capability scoping and permissions in `easy-sandbox-server` and `template.yaml` |
| **Client / server alignment** | [client-server-alignment.md](design/client-server-alignment.md) | Gap matrix of every server route against the client |
| **Base image and server SDK** | [base-image-and-server-sdk.md](design/base-image-and-server-sdk.md), [CLI follow-ups](design/cli-followups.md) | The official FC Agent Sandbox base image and the server SDK; the exact `ebx` CLI changes it needs |
| **Server SDK v2** | [server-sdk-v2/](design/server-sdk-v2/README.md) | Operation-model design and implementation plan for the server SDK |
| **OpenSandbox provider research** | [provider-opensandbox-mapping.md](design/provider-opensandbox-mapping.md) | API mapping, config keys and test plan for an OpenSandbox provider |
| **Repository layout** | [repository-layout.md](design/repository-layout.md) | Layout review of the `python-sdk` and `cli` repositories |

---

## Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| SDK core (Sandbox, files, commands, code) | **Implemented** | |
| MCP Server (STDIO) | **Implemented** | 7 P0 tools |
| MCP Server (Streamable HTTP) | **Implemented** | `mcp_http.py` |
| FC deployment artifact application | **Implemented** | `easy_sandbox.agent.mcp_http:asgi_app`; the artifact is generated by `ebx mcp deploy` in the CLI. See [mcp-server.md](design/mcp-server.md#7-fc-deployment) |
| Template build/push/create pipeline | **Implemented** | Via official CreateTemplate API |
| E2B compatibility layer | **Implemented** | `easy_sandbox.compat` |
| One environment variable per configuration key (SDK) | **Implemented** | See [Configuration](reference/configuration.md); CLI spec in `cli/docs/design/providers-and-credentials-cli.md` |
| Provider plugins (SDK, `python -m easy_sandbox.providers`) | **Implemented** | See [Providers](guide/providers.md); `ebx provider` pending in the CLI |
| Persistent sandbox | **Future** | Requires underlying platform support |
| SandboxPool (warm pool) | **Future** | Requires underlying platform support |
| NAS mount / SLS log integration | **Future** | Planned extension modules |

---

## Related Resources

| Resource | Location |
|----------|----------|
| Architecture Decision Records (ADR) | [`.agents/notes/`](../../.agents/notes/README.md) |
| User guides | [`docs/en/guide/`](guide/) |
| API reference | [`docs/en/reference/`](reference/) |
| Chinese (中文) design index | [`docs/zh/DESIGN.md`](../zh/DESIGN.md) |

## Related: the ebx CLI

The `ebx` CLI (Node.js / TypeScript, npm `@easy-sandbox/cli`) is documented in the [`cli` repository](https://github.com/Easy-Sandbox/easy-sandbox); its design index is [DESIGN.md](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/DESIGN.md). Most relevant to SDK readers: [CLI Architecture](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/design/architecture.md), [CLI Command System](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/design/cli-design.md) and [Templates Catalog](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/design/templates-catalog.md).
