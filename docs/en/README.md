# Agent Sandbox SDK — Documentation

Agent Sandbox is a sandbox SDK with pluggable providers. The default provider is Alibaba Cloud Express (Function Compute). The same API also has a Modal-style `@sandbox` decorator, and an in-sandbox Agents API for Codex and Qwen Code. Those CLIs are installed only when you use them.

> **Scope:** this repository documents the Python SDK (`agent-sandbox`) and the container-side runtime (`agent-sandbox-server`). The `abx` CLI is a separate Node.js project with its own documentation set; see [Related: the abx CLI](#related-the-abx-cli).

## Sites

| Site | URL |
|---|---|
| Official site | https://www.agent-sandbox.com |
| Provider registry | https://registry.agent-sandbox.com |

The installer fetches the catalog index at `https://registry.agent-sandbox.cn/providers/index.json`. `ABX_PROVIDER_REGISTRY` overrides that URL.

---

## Two parts

| | Client SDK | Server SDK |
|---|---|---|
| Where it runs | Your machine | Inside the sandbox image |
| What it does | Create a sandbox and use it | Build the HTTP service the sandbox keeps running |
| Package | `agent-sandbox` | `agent-sandbox-server` |
| Import | `agent_sandbox` | `agent_sandbox.server` |
| Start | [Client SDK](guide/client-sdk.md) | [Server SDK](guide/server-sdk.md) |

## User Guides

### Client SDK — use a sandbox

| Guide | Description |
|-------|-------------|
| [Client SDK](guide/client-sdk.md) | What this side is, and how the guides below fit together |
| [Getting Started](guide/getting-started.md) | Install, configure, first sandbox |
| [SDK Usage](guide/sdk-usage.md) | Commands, files, the code interpreter, named commands |
| [SDK skill](guide/sdk-skill.md) | What a coding agent loads before writing a client or a template |
| [Cloud end-to-end practice](guide/cloud-examples.md) | Run the quickstart and compat demos on the default provider |
| [Authentication](guide/authentication.md) | API key / AK-SK |
| [Declarative usage](guide/declarative-usage.md) | `@sandbox` decorator |
| [MCP integration](guide/mcp-integration.md) | Hand sandbox operations to an IDE |
| [Session persistence](guide/session-persistence.md) | Local session storage |
| [Migrate from E2B](guide/migrate-from-e2b.md) | Move from the E2B SDK |
| [Providers](guide/providers.md) | Choose, install, and write a provider |
| [Environment variables](guide/environment-variables.md) | Injection and reads inside the sandbox |
| [Troubleshooting](guide/troubleshooting.md) | Common failures |
| [Comparison](guide/comparison.md) | Next to E2B, Modal, and Docker Sandbox |
| [Command and SDK map](guide/command-map.md) | Commands and methods next to E2B and OpenSandbox |

### Server SDK — build the service inside the sandbox

| Guide | Description |
|-------|-------------|
| [Server SDK](guide/server-sdk.md) | What this side is, and how `commands.py` starts |
| [Authoring templates](guide/authoring-templates.md) | `template.yaml`, capabilities, registered commands, Dockerfile |
| [Template server HTTP API](guide/template-server-api.md) | Routes `commands.py` actually serves |
| [Best practices](guide/best-practices.md) | The server carries no provider; turn groups on only when needed |
| [Fine-grained capabilities](guide/fine-grained-capabilities.md) | Enable routes one endpoint at a time |
| [File and command controls](guide/file-and-command-controls.md) | Limit paths and commands |
| [Agents API](guide/agents-api.md) | Codex and Qwen Code HTTP sessions inside the sandbox |
| [Hosted agents](guide/hosted-agents.md) | How those routes refuse and what they return |
| [Build and deploy](guide/build-and-deploy.md) | `abx template build` and `abx template deploy` |

How a change counts as tested: [Testing and the Definition of Done](guide/testing-e2e.md).

### [`reference/`](reference/) — API / Configuration Reference

| Document | Description |
|----------|-------------|
| [API Reference](reference/api-reference.md) | Client SDK public API |
| [Configuration](reference/configuration.md) | Client SDK environment variables, config files, credential resolution |
| [Error Codes](reference/error-codes.md) | E1xxx–E8xxx error code index |
| [Template YAML Spec](reference/template-yaml-spec.md) | Server SDK template definition (`template.yaml`) |
| [Server HTTP API](reference/server-http-api.md) | HTTP API of the Server SDK inside the sandbox |
| [Agents API reference](reference/agents-api.md) | Parameters and responses for each Agents route on the Server SDK |

### [`explanation/`](explanation/) — Concepts & Architecture

| Document | Description |
|----------|-------------|
| [Architecture Overview](explanation/architecture-overview.md) | Layered architecture concepts |
| [E2B Compatibility](explanation/e2b-compatibility.md) | What the E2B-shaped API shares with E2B, and where it differs |
| [Sandbox Lifecycle](explanation/sandbox-lifecycle.md) | Create → Run → Hibernate → Destroy |

## Design Documents

Start here only when you are changing the product. Day-to-day use is in the guides above. The user-facing Agents API is [Agents API](guide/agents-api.md).

| # | Document | Description |
|---|----------|-------------|
| 1 | [Architecture Design](design/architecture.md) | Layered architecture overview |
| 2 | [SDK API Design](design/sdk-api-design.md) | SDK public API specification |
| 3 | [Sandbox Types](design/sandbox-types.md) | Sandbox type taxonomy |
| 4 | [MCP Server](design/mcp-server.md) | MCP tool server design (Python server, HTTP app, FC artifact) |
| 5 | [Template System](design/template-system.md) | Template resolution, versioning and registry |
| 6 | [Server API](design/server-api.md) | In-sandbox HTTP server endpoints |
| 7 | [Providers and Credentials](design/providers-and-credentials.md) | Canonical configuration names, provider plugins, EPP/1 |
| 8 | [OpenSandbox provider](design/provider-opensandbox-mapping.md) | Current adapter and the live capability table |
| 9 | [Container edition](design/provider-alicloud-container.md) | `alicloud-container` |
| 10 | [CubeSandbox provider](design/provider-cubesandbox.md) | `cubesandbox` |
| 11 | [E2B provider](design/provider-e2b.md) | `e2b` |

Other maintainer notes are indexed in [DESIGN.md](DESIGN.md).

## Archive

These pages are reviews or target design, not the current specification.

- [Server SDK v2 target design](archive/server-sdk-v2/README.md)
- [Agents API review](archive/agents-api-review.md)
- [Fine-grained capabilities review](archive/fine-grained-capabilities-review.md)
- [Providers and credentials review](archive/providers-and-credentials-review.md)
- [OpenSandbox research](archive/provider-opensandbox-research.md)
- [OpenSandbox end-to-end notes](archive/opensandbox-e2e-adversarial.md)
- [CLI follow-ups](archive/cli-followups.md)

## Project Planning

| Document | Description |
|----------|-------------|
| [Design Document](DESIGN.md) | Design topic index and implementation status |

---

## Quick Navigation

### By role

- **Use a sandbox (Client SDK)**: [Client SDK](guide/client-sdk.md) → [Getting Started](guide/getting-started.md) → [SDK Usage](guide/sdk-usage.md)
- **Build the service inside the sandbox (Server SDK)**: [Server SDK](guide/server-sdk.md) → [Authoring Templates](guide/authoring-templates.md) → [Template server HTTP API](guide/template-server-api.md)
- **Architect**: [Architecture](design/architecture.md) → [Server API](design/server-api.md)

### By feature

- **MCP integration (Cursor/Claude)**: [MCP Integration](guide/mcp-integration.md#configure-an-ide) | [MCP Server](design/mcp-server.md#5-installation-and-cli)

### Other resources

- **Template source of truth (awesome-templates):** [alibaba-agent-sandbox/awesome-templates](https://github.com/alibaba-agent-sandbox/awesome-templates) — the single source of truth for official & community template content, the index (`awesome-templates.yaml`), and publishing
- **中文文档**：[Chinese docs](../zh/README.md)

## Related: the abx CLI

The `abx` CLI (npm `@agent-sandbox/cli`) is documented in the [`cli` repository](https://github.com/alibaba-agent-sandbox/agent-sandbox): [documentation index](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/README.md), [Getting Started](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/getting-started.md), [CLI Reference](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/cli-reference.md), [CLI Architecture](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/architecture.md), [CLI Command System](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/cli-design.md), [Templates Catalog](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/templates-catalog.md), [Deploy & Build](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/deploy-and-build.md), [Agent Skill Installation](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/agent-skill-installation.md).
