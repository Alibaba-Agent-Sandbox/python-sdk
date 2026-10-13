# Agent Sandbox SDK — Documentation

Agent Sandbox is a sandbox SDK with pluggable providers. The default provider is Alibaba Cloud Express (Function Compute). The same API also has a Modal-style `@sandbox` decorator, and an in-sandbox Agents API for Codex and Qwen Code. Those CLIs are installed only when you use them.

> **Scope:** this repository documents the Python SDK (`agent-sandbox`) and the container-side runtime (`agent-sandbox-server`). The `abx` CLI is a separate Node.js project with its own documentation set; see [Related: the abx CLI](#related-the-abx-cli).

---

## Design Documents

| # | Document | Description |
|---|----------|-------------|
| 1 | [Architecture Design](design/architecture.md) | Layered architecture overview |
| 2 | [SDK API Design](design/sdk-api-design.md) | SDK public API specification |
| 3 | [Sandbox Types](design/sandbox-types.md) | Sandbox type taxonomy |
| 4 | [MCP Server](design/mcp-server.md) | MCP tool server design (Python server, HTTP app, FC artifact) |
| 5 | [Template System](design/template-system.md) | Template resolution, versioning and registry |
| 6 | [Server API](design/server-api.md) | In-sandbox HTTP server endpoints |
| 7 | [Providers and Credentials](design/providers-and-credentials.md) | Canonical configuration names, provider plugins, EPP/1 |

The user-facing Agents API is [Agents API](guide/agents-api.md) (Codex and Qwen Code, install a CLI only when you call it). Other maintainer notes are indexed in [DESIGN.md](DESIGN.md).

## Archive

These pages are reviews or target design, not the current specification.

- [Server SDK v2 target design](archive/server-sdk-v2/README.md)
- [Agents API review](archive/agents-api-review.md)
- [Fine-grained capabilities review](archive/fine-grained-capabilities-review.md)
- [Providers and credentials review](archive/providers-and-credentials-review.md)
- [OpenSandbox end-to-end notes](archive/opensandbox-e2e-adversarial.md)
- [CLI follow-ups](archive/cli-followups.md)

## User Guides

### [`guide/`](guide/) — Tutorials & How-to Guides

| Guide | Description |
|-------|-------------|
| [Agents API](guide/agents-api.md) | HTTP sessions for Codex and Qwen Code, the one way to run an agent in a sandbox. CLIs install on demand. Includes the complete case |
| [Getting Started](guide/getting-started.md) | Install, configure, first sandbox |
| [Cloud end-to-end practice](guide/cloud-examples.md) | Run the quickstart and compat demos on the default provider. The Agents API case stays on its own page |
| [Best Practices](guide/best-practices.md) | Provider-free server, capability groups, agents opt-in, secrets not echoed |
| [Fine-grained capabilities](guide/fine-grained-capabilities.md) | How to enable routes one endpoint at a time, with every endpoint id, scope, and knob |
| [File and command controls](guide/file-and-command-controls.md) | How a template limits paths and commands |
| [Hosted agents](guide/hosted-agents.md) | Codex and Qwen Code on the local Agents API |
| [Authentication](guide/authentication.md) | API Key / AK-SK authentication |
| [SDK Usage](guide/sdk-usage.md) | Python SDK complete usage, including the agent workflow pattern |
| [Authoring Templates](guide/authoring-templates.md) | `template.yaml`, capability declarations, server-registered commands, Dockerfile |
| [Template server HTTP API](guide/template-server-api.md) | Routes the template's `commands.py` server actually serves |
| [Build & Deploy](guide/build-and-deploy.md) | Building and deploying templates with `abx template build` and `abx template deploy` |
| [Declarative Usage](guide/declarative-usage.md) | `@sandbox` decorator |
| [MCP Integration](guide/mcp-integration.md) | Python MCP server, IDE configuration, Streamable HTTP, FC artifact |
| [Session Persistence](guide/session-persistence.md) | Local session storage |
| [Migrate from E2B](guide/migrate-from-e2b.md) | Migration guide from E2B SDK |
| [Providers](guide/providers.md) | Choose a sandbox provider, install provider plugins, write your own |
| [Environment Variables](guide/environment-variables.md) | Sandbox env var scopes, injection, and direct-exec semantics |
| [Troubleshooting](guide/troubleshooting.md) | Common issues and solutions |
| [Testing & Definition of Done](guide/testing-e2e.md) | Real-cloud E2E suite (`make e2e`) and the Definition of Done |
| [Comparison](guide/comparison.md) | Agent Sandbox compared with E2B, Modal and Docker Sandbox |
| [Command and SDK map](guide/command-map.md) | `abx` and the Python SDK next to the E2B and OpenSandbox commands and methods |

### [`reference/`](reference/) — API / Configuration Reference

| Document | Description |
|----------|-------------|
| [API Reference](reference/api-reference.md) | Complete SDK API documentation |
| [Configuration](reference/configuration.md) | Environment variables, config files, credential resolution |
| [Error Codes](reference/error-codes.md) | E1xxx–E8xxx error code index |
| [Template YAML Spec](reference/template-yaml-spec.md) | Template definition format (the `template.yaml` contract) |
| [Server HTTP API](reference/server-http-api.md) | In-sandbox server HTTP API reference |
| [Agents API reference](reference/agents-api.md) | Every `/v1/agents/**`, `/v1/vaults` and `/v1/responses` route: parameters and responses |

### [`explanation/`](explanation/) — Concepts & Architecture

| Document | Description |
|----------|-------------|
| [Architecture Overview](explanation/architecture-overview.md) | Layered architecture concepts |
| [E2B Compatibility](explanation/e2b-compatibility.md) | What the E2B-shaped API shares with E2B, and where it differs |
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

- **MCP integration (Cursor/Claude)**: [MCP Integration](guide/mcp-integration.md#configure-an-ide) | [MCP Server](design/mcp-server.md#5-installation-and-cli)

### Other resources

- **Template source of truth (awesome-templates):** [alibaba-agent-sandbox/awesome-templates](https://github.com/alibaba-agent-sandbox/awesome-templates) — the single source of truth for official & community template content, the index (`awesome-templates.yaml`), and publishing
- **中文文档**：[Chinese docs](../zh/README.md)

## Related: the abx CLI

The `abx` CLI (npm `@agent-sandbox/cli`) is documented in the [`cli` repository](https://github.com/alibaba-agent-sandbox/agent-sandbox): [documentation index](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/README.md), [Getting Started](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/getting-started.md), [CLI Reference](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/cli-reference.md), [CLI Architecture](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/architecture.md), [CLI Command System](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/cli-design.md), [Templates Catalog](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/templates-catalog.md), [Deploy & Build](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/deploy-and-build.md), [Agent Skill Installation](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/agent-skill-installation.md).
