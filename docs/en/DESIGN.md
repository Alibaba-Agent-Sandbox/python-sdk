# Agent Sandbox — Design Document Index

> **Version**: v2.0 | **Last Updated**: 2026-10-16
>
> This document serves as the entry point and index for all Agent Sandbox design documentation. Detailed designs live in the specialized topic documents under [`design/`](design/).

---

## Project Overview

**Agent Sandbox** (`agent-sandbox-client` on PyPI) is a Python SDK for the Alibaba Cloud FC Agent Sandbox service. It is the runtime client: create, use and kill sandboxes. Source templates normally start with `abx template launch`; Python consumes the returned sandbox. Advanced image preparation uses `abx template build` and `abx template deploy`. Method names are E2B-shaped to ease migration; the standard public API follows the pinned Alibaba E2B contract (see [Migrate from E2B](guide/migrate-from-e2b.md)).

This repository holds the Python SDK as two lock-step PyPI distributions — `agent-sandbox-client` (`client-sdk/`, import `agent_sandbox`) and `agent-sandbox-server` (`server-sdk/`, import `agent_sandbox.server`, the container-side runtime). The `abx` CLI is a Node.js/TypeScript project in the `cli` repository, which holds the CLI's own design and guide documents (see [Related: the abx CLI](#related-the-abx-cli)).

### Core Principles

1. **Pinned standard behavior and explicit provider extensions** — Root `Sandbox` is synchronous; `AsyncSandbox` is asynchronous. Standard and interpreter clients follow the Alibaba-supported E2B baseline through an owned MIT source port. Provider/server/declarative extensions use `ProviderSandbox`; `ABX_PROVIDER` does not switch the standard clients' protocol.
2. **AI-First** — MCP Server as a first-class citizen, coding agents hosted through the Agents API
3. **Explicit connection settings** — Reuse the existing Alibaba API key, API URL and sandbox domain; backend-dependent capabilities remain conditional.

### Quick Start

```bash
python -m pip install --index-url https://pypi.org/simple agent-sandbox-client==0.4.0a6
export ABX_SANDBOX_API_KEY=your-api-key
```

```python
from agent_sandbox import ProviderSandbox as Sandbox

async with await Sandbox.create(template="base") as sb:
    result = await sb.commands.run("printf 'Hello, Agent Sandbox!'")
    print(result.stdout)
```

---

Current builtin runtime: [direct HTTP and migration](design/builtin-data-plane.md).

## Architecture Overview

The native provider extensions follow the layers below. Standard clients use their separate source-ported protocol implementation:

```mermaid
graph TB
    subgraph Upper["Upper Layers"]
        Agent["Agent/MCP — MCP server, tool defs"]
        Decl["Declarative — @sandbox decorator"]
        Compat["compat — standard client aliases"]
        STD["Sandbox / AsyncSandbox / code_interpreter"]
    end
    subgraph Core["Core Layers"]
        L3["ProviderSandbox — files, code, commands, network, server client"]
        PORT["_standard / interpreter — maintained MIT source port"]
        L2["Protocol — Sandbox lifecycle, filesystem, process, terminal, port"]
        L1["Transport — HTTP, WebSocket, auth, codec, streaming"]
        L0["Models + Utils — Pydantic models, errors, config, async bridge"]
    end

    Agent --> L3
    Decl --> L3
    Compat --> STD --> PORT
    L3 --> L2 --> L1 --> L0
```

For the full architecture breakdown, see [Architecture Design](design/architecture.md).

---

## Design Topic Index

Each topic below has its own dedicated design document with complete specifications.

### Core Design

| Topic | Document | Summary |
|-------|----------|---------|
| **System Architecture** | [architecture.md](design/architecture.md) | Standard client source port, native provider extension layers, and their separate protocol paths |
| **SDK API Design** | [sdk-api-design.md](design/sdk-api-design.md) | Sandbox class, file operations, code execution, commands, network, session management |
| **Sandbox Lifecycle and Ownership** | [sandbox-types.md](design/sandbox-types.md) | Owned cleanup, borrowed connections and provider-dependent operations |
| **Providers and Credentials** | [providers-and-credentials.md](design/providers-and-credentials.md) | One environment variable per configuration key, precedence, provider plugins (`abx provider ...`), install/trust model, EPP/1 protocol, E8xxx errors; review log in [providers-and-credentials-review.md](archive/providers-and-credentials-review.md) |

### Templates

| Topic | Document | Summary |
|-------|----------|---------|
| **Template System** | [template-system.md](design/template-system.md) | Template tiers, GitHub tarball distribution, `template.yaml` specification, versioning, marketplace architecture |

### AI & Agent Integration

| Topic | Document | Summary |
|-------|----------|---------|
| **MCP Server** | [mcp-server.md](design/mcp-server.md) | 7 P0 MCP tools, STDIO + Streamable HTTP transports, FC deployment artifact, session binding |
| **Agents API** | [guide/agents-api.md](guide/agents-api.md) | The one way to run an agent in a sandbox: `/v1/agents/**`. The base image does not preinstall a CLI |

### Server & Infrastructure

| Topic | Document | Summary |
|-------|----------|---------|
| **Server API** | [server-api.md](design/server-api.md) | Sandbox Server SDK routes, capability groups, browser instance architecture |

### Maintainer design documents

Chinese copies of these pages live under `docs/zh/`. `repository-layout.md` is English only.

| Topic | Document | Summary |
|-------|----------|---------|
| **Agents API** | [agents-api.md](design/agents-api.md), [review](archive/agents-api-review.md) | Hosting coding agents in Agent Sandbox |
| **Fine-grained capabilities** | [fine-grained-capabilities.md](design/fine-grained-capabilities.md), [review](archive/fine-grained-capabilities-review.md) | Capability scoping and permissions in `agent-sandbox-server` and `template.yaml` |
| **Client / server alignment** | [client-server-alignment.md](design/client-server-alignment.md) | Gap matrix of every server route against the client |
| **Base image and server SDK** | [base-image-and-server-sdk.md](design/base-image-and-server-sdk.md), [CLI follow-ups](archive/cli-followups.md) | The official FC Agent Sandbox base image and the server SDK; the exact `abx` CLI changes it needs |
| **Server SDK v2** | [server-sdk-v2/](archive/server-sdk-v2/README.md) | Target operation-model design for the server SDK (status and not-implemented list on the first page) |
| **OpenSandbox provider** | [provider-opensandbox-mapping.md](design/provider-opensandbox-mapping.md) | Current `node` catalog provider and the live capability table |
| **Container edition** | [provider-alicloud-container.md](design/provider-alicloud-container.md) | ACS/ACK sandbox-manager, E2B-shaped HTTP, not Express |
| **CubeSandbox** | [provider-cubesandbox.md](design/provider-cubesandbox.md) | CubeAPI control plane |
| **E2B** | [provider-e2b.md](design/provider-e2b.md) | E2B cloud API at api.e2b.app |
| **Provider readiness** | [provider-readiness.md](design/provider-readiness.md) | Logical review of CubeSandbox, E2B, and the container edition before a live backend exists |
| **Repository layout** | [repository-layout.md](design/repository-layout.md) | Layout review of the `python-sdk` and `cli` repositories |

---

## Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| SDK core (Sandbox, files, commands, code) | **Implemented** | |
| MCP Server (STDIO) | **Implemented** | 7 P0 tools |
| MCP Server (Streamable HTTP) | **Implemented** | `mcp_http.py` |
| FC deployment artifact application | **Implemented** | `agent_sandbox.agent.mcp_http:asgi_app`; the artifact is generated by `abx mcp deploy` in the CLI. See [mcp-server.md](design/mcp-server.md#7-fc-deployment) |
| Template startup and image preparation | **In the CLI** | Start sources with `abx template launch` and consume with the SDK; advanced preparation uses `abx template build` and `abx template deploy` |
| One environment variable per configuration key (SDK) | **Implemented** | See [Configuration](reference/configuration.md); CLI spec in `cli/docs/design/providers-and-credentials-cli.md` |
| Provider plugins (SDK, `python -m agent_sandbox.providers`) | **Implemented** | See [Providers](guide/providers.md). The CLI loads installed `node`, `exec` and `rest` plugins (`abx provider`, `abx --provider`) |
| Persistent sandbox | **Future** | Requires underlying platform support |
| SandboxPool (warm pool) | **Future** | Requires underlying platform support |

---

## Related Resources

| Resource | Location |
|----------|----------|
| Architecture Decision Records (ADR) | [`.agents/notes/`](../../.agents/notes/README.md) |
| User guides | [`docs/en/guide/`](guide/) |
| API reference | [`docs/en/reference/`](reference/) |
| Chinese (中文) design index | [`docs/zh/DESIGN.md`](../zh/DESIGN.md) |

## Related: the abx CLI

The `abx` CLI (Node.js / TypeScript, npm `@agent-sandbox/cli`) is documented in the [`cli` repository](https://github.com/alibaba-agent-sandbox/agent-sandbox); its design index is [DESIGN.md](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/DESIGN.md). Most relevant to SDK readers: [CLI Architecture](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/architecture.md), [CLI Command System](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/cli-design.md) and [Templates Catalog](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/templates-catalog.md).
