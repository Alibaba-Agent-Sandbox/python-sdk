# Easy Sandbox SDK — Documentation

Easy Sandbox is a cloud sandbox SDK built on Alibaba Cloud Function Compute, providing E2B-compatible APIs, Modal-style decorators, and built-in AI Agent paradigms.

> **Scope:** this repository documents the Python SDK (`easy-sandbox`) and the container-side runtime (`easy-sandbox-server`). The `ebx` CLI is a separate Node.js project with its own documentation set; see [Related: the ebx CLI](#related-the-ebx-cli).

---

## Design Documents

| # | Document | Description |
|---|----------|-------------|
| 1 | [Architecture Design](design/architecture.md) | Layered architecture overview |
| 2 | [SDK API Design](design/sdk-api-design.md) | SDK public API specification |
| 3 | [Sandbox Types](design/sandbox-types.md) | Sandbox type taxonomy |
| 4 | [MCP Server](design/mcp-server.md) | MCP tool server design (Python server, HTTP app, FC artifact) |
| 5 | [Template System](design/template-system.md) | Template resolution, versioning and registry |
| 6 | [Built-in Agents](design/built-in-agents.md) | Agent module (`commands.run()` sugar) and per-Agent dedicated templates (BYO) |
| 7 | [Server API](design/server-api.md) | In-sandbox HTTP server endpoints |
| 8 | [Providers and Credentials](design/providers-and-credentials.md) | Canonical configuration names, provider plugins, EPP/1 |

English-only maintainer documents (agents API, fine-grained capabilities, client/server alignment, base image, server SDK v2, OpenSandbox research, repository layout) are indexed in [DESIGN.md](DESIGN.md).

## User Guides

### [`guide/`](guide/) — Tutorials & How-to Guides

| Guide | Description |
|-------|-------------|
| [Getting Started](guide/getting-started.md) | Install, configure, first sandbox |
| [Best Practices](guide/best-practices.md) | Provider-free server, capability groups, agents opt-in, secrets not echoed |
| [File and command controls](guide/file-and-command-controls.md) | How a template limits paths and commands |
| [Hosted agents](guide/hosted-agents.md) | Codex and Qwen Code on the local Agents API |
| [Authentication](guide/authentication.md) | API Key / AK-SK authentication |
| [SDK Usage](guide/sdk-usage.md) | Python SDK complete usage, including the agent workflow pattern |
| [Authoring Templates](guide/authoring-templates.md) | `template.yaml`, capability declarations, custom commands, Dockerfile |
| [Template server HTTP API](guide/template-server-api.md) | Routes the template's `commands.py` server actually serves |
| [Build & Deploy](guide/build-and-deploy.md) | `Sandbox.deploy`, the chained `Image` API, the Docker build process |
| [Declarative Usage](guide/declarative-usage.md) | `@sandbox` decorator |
| [MCP Integration](guide/mcp-integration.md) | Python MCP server, IDE configuration, Streamable HTTP, FC artifact |
| [Session Persistence](guide/session-persistence.md) | Local / OSS session storage |
| [Migrate from E2B](guide/migrate-from-e2b.md) | Migration guide from E2B SDK |
| [Providers](guide/providers.md) | Choose a sandbox provider, install provider plugins, write your own |
| [Environment Variables](guide/environment-variables.md) | Sandbox env var scopes, injection, and direct-exec semantics |
| [Troubleshooting](guide/troubleshooting.md) | Common issues and solutions |
| [Testing & Definition of Done](guide/testing-e2e.md) | Real-cloud E2E suite (`make e2e`) and the Definition of Done |
| [Migrating from 0.2.x](guide/migrating-from-0.2.md) | Upgrade to 0.3.0: client/server split, `easy-sandbox-server`, in-place upgrade repair |
| [Comparison](guide/comparison.md) | Easy Sandbox compared with E2B, Modal and Docker Sandbox |

### [`reference/`](reference/) — API / Configuration Reference

| Document | Description |
|----------|-------------|
| [API Reference](reference/api-reference.md) | Complete SDK API documentation |
| [Configuration](reference/configuration.md) | Environment variables, config files, credential resolution |
| [Error Codes](reference/error-codes.md) | E1xxx–E8xxx error code index |
| [Template YAML Spec](reference/template-yaml-spec.md) | Template definition format (the `template.yaml` contract) |
| [Server HTTP API](reference/server-http-api.md) | In-sandbox server HTTP API reference |

### [`explanation/`](explanation/) — Concepts & Architecture

| Document | Description |
|----------|-------------|
| [Architecture Overview](explanation/architecture-overview.md) | Layered architecture concepts |
| [E2B Compatibility](explanation/e2b-compatibility.md) | Protocol compatibility |
| [Sandbox Lifecycle](explanation/sandbox-lifecycle.md) | Create → Run → Hibernate → Destroy |

## Project Planning

| Document | Description |
|----------|-------------|
| [Design Document](DESIGN.md) | Design topic index and implementation status |

---

## Quick Navigation

### By role

- **SDK user**: [Best Practices](guide/best-practices.md) → [SDK Usage](guide/sdk-usage.md) → [API Reference](reference/api-reference.md)
- **AI Agent developer**: [Hosted agents](guide/hosted-agents.md) → [File and command controls](guide/file-and-command-controls.md) → [MCP Integration](guide/mcp-integration.md)
- **Architect**: [Architecture](design/architecture.md) → [Server API](design/server-api.md)

### By feature

- **Natural language sandbox creation**: [SDK API](design/sdk-api-design.md)
- **MCP integration (Cursor/Claude)**: [MCP Integration](guide/mcp-integration.md#configure-an-ide) | [MCP Server](design/mcp-server.md#5-installation-and-cli)

### Other resources

- **Template source of truth (awesome-templates):** [Easy-Sandbox/awesome-templates](https://github.com/Easy-Sandbox/awesome-templates) — the single source of truth for official & community template content, the index (`awesome-templates.yaml`), and publishing
- **中文文档**：[Chinese docs](../zh/README.md)

## Related: the ebx CLI

The `ebx` CLI (npm `@easy-sandbox/cli`) is documented in the [`cli` repository](https://github.com/Easy-Sandbox/easy-sandbox): [documentation index](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/README.md), [Getting Started](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/getting-started.md), [CLI Reference](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/reference/cli-reference.md), [CLI Architecture](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/design/architecture.md), [CLI Command System](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/design/cli-design.md), [Templates Catalog](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/design/templates-catalog.md), [Deploy & Build](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/deploy-and-build.md), [BYO Agent Integration](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/byo-agent-integration.md), [Agent Skill Installation](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/agent-skill-installation.md).
