# Easy Sandbox SDK — Documentation

> **Note:** English translations are in progress. Each page below links back to the Chinese original until translation is complete.

Easy Sandbox is a cloud sandbox SDK built on Alibaba Cloud Function Compute, providing E2B-compatible APIs, Modal-style decorators, and built-in AI Agent paradigms.

> **CLI documentation:** pages marked *(`cli` repository)* below (CLI design, tutorial, reference, templates, deploy, skills, …) live in the `cli` repository, which holds the Node.js `ebx` CLI. This repository documents the Python SDK (`easy-sandbox`) and the container-side runtime (`easy-sandbox-server`).

---

## Design Documents

| # | Document | Description |
|---|----------|-------------|
| 1 | [Architecture Design](design/architecture.md) | Layered architecture overview *(coming soon)* |
| 2 | [SDK API Design](design/sdk-api-design.md) | SDK public API specification *(coming soon)* |
| 3 | [CLI Design](../../../cli/docs/en/design/cli-design.md) *(`cli` repository)* | CLI command structure *(coming soon)* |
| 4 | [Sandbox Types](design/sandbox-types.md) | Sandbox type taxonomy *(coming soon)* |
| 5 | [MCP Server](design/mcp-server.md) | MCP tool server design *(coming soon)* |
| 6 | [Template System](design/template-system.md) | Template resolution and registry *(coming soon)* |
| 7 | [Built-in Agents](design/built-in-agents.md) | Agent module (`commands.run()` sugar) and per-Agent dedicated templates (BYO) |
| 8 | [Server API](design/server-api.md) | In-sandbox HTTP server endpoints *(coming soon)* |
| 9 | [Templates Catalog](../../../cli/docs/en/design/templates-catalog.md) *(`cli` repository)* | Official template catalog *(coming soon)* |

## User Guides

### [`guide/`](guide/) — Tutorials & How-to Guides

| Guide | Description |
|-------|-------------|
| [Agents API](guide/agents-api.md) | HTTP sessions for Codex and Qwen Code. Not the built-in agent sugar. CLIs install on demand. Includes the complete case |
| [Getting Started](guide/getting-started.md) | Install, configure, first sandbox *(coming soon)* |
| [Cloud end-to-end practice](guide/cloud-examples.md) | Run the quickstart and compat demos on the default provider. The Agents API case stays on its own page |
| [Authentication](guide/authentication.md) | API Key / AK-SK authentication *(coming soon)* |
| [SDK Usage](guide/sdk-usage.md) | Python SDK complete usage *(coming soon)* |
| [CLI Tutorial](../../../cli/docs/en/guide/cli-tutorial.md) *(`cli` repository)* | CLI quick start *(coming soon)* |
| [Using Templates](../../../cli/docs/en/guide/using-templates.md) *(`cli` repository)* | Official and community templates *(coming soon)* |
| [Authoring Templates](guide/authoring-templates.md) | Custom templates, including `ebx template init --adopt` for an existing project |
| [Deploy & Build](../../../cli/docs/en/guide/deploy-and-build.md) *(`cli` repository)* | template lifecycle (`template init` / `--adopt` → `deploy` → `create`), `Sandbox.deploy`, Image build |
| [Declarative Usage](guide/declarative-usage.md) | `@sandbox` decorator *(coming soon)* |
| [MCP Integration](guide/mcp-integration.md) | Cursor / Claude Desktop integration *(coming soon)* |
| [Session Persistence](guide/session-persistence.md) | Local / OSS session storage *(coming soon)* |
| [Migrate from E2B](guide/migrate-from-e2b.md) | Migration guide from E2B SDK *(coming soon)* |
| [Providers](guide/providers.md) | Choose a sandbox provider, install provider plugins (`ebx provider ...`), write your own |
| [Environment Variables](guide/environment-variables.md) | Sandbox env var scopes, injection, and direct-exec semantics |
| [Troubleshooting](guide/troubleshooting.md) | Common issues and solutions *(coming soon)* |
| [Testing & Definition of Done](guide/testing-e2e.md) | Real-cloud E2E suite (`make e2e`) and the Definition of Done |
| [Migrating from 0.2.x](guide/migrating-from-0.2.md) | Upgrade to 0.3.0: client/server split, `easy-sandbox-server`, in-place upgrade repair |
| [E2E Template Workflow](../../../cli/docs/en/guide/e2e-template-workflow.md) *(`cli` repository)* | Complete guide from building a template to using sandboxes |
| [Agent Skill Installation](../../../cli/docs/en/guide/agent-skill-installation.md) *(`cli` repository)* | Install the static SKILL.md agent guide into Qoder / Claude Code / Cursor / Qwen Code / Codex |
| [BYO Agent Integration](../../../cli/docs/en/guide/byo-agent-integration.md) *(`cli` repository)* | Bring your own agent CLI inside a sandbox: responsibility boundary, `custom_commands` contract, credential whitelist, version locking, license boundaries |

### [`reference/`](reference/) — CLI / API / Configuration Reference

| Document | Description |
|----------|-------------|
| [API Reference](reference/api-reference.md) | Complete SDK API documentation *(coming soon)* |
| [CLI Reference](../../../cli/docs/en/reference/cli-reference.md) *(`cli` repository)* | All CLI commands quick reference |
| [Configuration](reference/configuration.md) | Environment variables and config files *(coming soon)* |
| [Error Codes](reference/error-codes.md) | E1xxx–E8xxx error code index *(coming soon)* |
| [Template YAML Spec](reference/template-yaml-spec.md) | Template definition format *(coming soon)* |

### [`explanation/`](explanation/) — Concepts & Architecture

| Document | Description |
|----------|-------------|
| [Architecture Overview](explanation/architecture-overview.md) | Layered architecture concepts *(coming soon)* |
| [E2B Compatibility](explanation/e2b-compatibility.md) | Protocol compatibility *(coming soon)* |
| [Sandbox Lifecycle](explanation/sandbox-lifecycle.md) | Create → Run → Hibernate → Destroy *(coming soon)* |

## Project Planning

| Document | Description |
|----------|-------------|
| [Design Document](DESIGN.md) | Consolidated design decisions *(coming soon)* |

---

## Other Resources

- **Template source of truth (awesome-templates):** [Easy-Sandbox/awesome-templates](https://github.com/Easy-Sandbox/awesome-templates) — the single source of truth for official & community template content, the index (`awesome-templates.yaml`), and publishing; consumed via `ebx template search` / `ebx template install`
- **中文文档**：[Chinese docs](../zh/README.md)
