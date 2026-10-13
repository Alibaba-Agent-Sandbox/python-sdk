# Server SDK v2: target design and implementation status

> Status: archive. Not the current specification.

This set describes the **target design** of the Agent Sandbox server SDK (`python-sdk/server-sdk`, import `agent_sandbox.server`). It is a design, not
documentation of the shipped server: files 01-09 propose an *operation model* (dotted operation IDs, `@op`, `POST /ops/{id}`, allow/deny rules over IDs) that
**the code does not implement**. Read this page first; it says what exists. For how the shipped server behaves, read
[server-api.md](../../design/server-api.md), [fine-grained-capabilities.md](../../design/fine-grained-capabilities.md) and the guides.

## 1. What is implemented

| Area | Shipped form |
|---|---|
| One declaration table | `server/endpoints.py` `ENDPOINTS`: every endpoint (118, 70 of them Agents API; the PTY WebSocket is the virtual endpoint `pty_connect`) has an id, method, path, group, scopes and limits. The route table, the policy, the audit log, `/capabilities` and the client all use these ids. |
| One policy engine | `ServerPolicy` + `PolicyEngine`: layers default < code < preset < policy (`template.yaml` `server:` / `ServerPolicy`) < env (`ABX_SERVER_ENABLED_GROUPS`, enable only). A group is an alias that expands to endpoint ids; the most specific selector (exact id > glob > group > `@defaults`) wins and every denial names the rule. |
| One dispatch pipeline | `SandboxRequestHandler`: match, authenticate (Bearer or `X-Access-Token`), admit (404 `endpoint_disabled`, 403 `missing_scope`, 429), duplicate-query check, body limit, handler, audit. v1 HTTP paths are the bindings of the table. |
| Guards | Path boundary (`/home/user` by default, `ABX_SERVER_BASE_DIR`, policy `base_dir`, per-endpoint `paths`) on every path-taking endpoint including shell `cwd`; command allow/deny params (`command_not_allowed`); size limits; rate limits and concurrency caps; audit. |
| Discovery | `GET /capabilities` (per-endpoint state, rule, scopes, derived group summaries), `POST /capabilities/check`. |
| Named commands | `CommandRegistry`, the module-level `command` decorator, `GET /commands`, `POST /commands/{name}`. |
| Agents API | 70 routes, all real, table-driven test per route; local backends for `codex` and `qwen-code`; `claude-code`, `cursor` and `command` are declared adapters without a local backend (`implemented: false` in `GET /v1/agents/runtimes`). |
| CLI | `python -m agent_sandbox.server serve | healthcheck | check-config | version`. |

## 2. What is not implemented

| Proposed in the design | Status |
|---|---|
| Dotted operation IDs (`files.download`), the `@op` decorator, `ops` attribute tree, the `Registry` | Not implemented. Endpoint ids (`files_download`) are the only identity. A second id space was rejected: it would need a mapping layer next to the table. |
| `POST /ops/{id}` RPC, `GET /ops`, `core.describe`, `core.check`, `GET /openapi.json` | Not implemented (no `/ops` route exists). Discovery is `/capabilities`. |
| `Policy().allow(...)` / `deny(...)` builder, `PathScope`, `CommandScope`, `UrlScope`, `AgentScope` | Not implemented. Rules are `ServerPolicy` data: `groups`, `endpoints` selectors with `enabled`, `scopes`, `paths`, `limits`, `params` (including command and URL lists) and `audit`. |
| Veto-only hooks, per-principal `role:`/`id:` rule matching | Not implemented (principals exist for audit and scopes only). |
| Hot reload, `explain`, `describe`, `prepare`, `doctor` subcommands | Not implemented (`serve`, `healthcheck`, `check-config`, `version` exist). |
| Lazy, checksum-verified installation of agent CLIs (06) | Not implemented. |
| Host/Origin allowlists, socket timeouts, single-use PTY tickets (03 section 15) | Not implemented. |
| Generated client mirror (`ServerClient`, `operations.json`, TypeScript client) (07) | Not implemented. |
| Agents API tiers (05): local backends for `claude-code`, `cursor`, `command`; `/v1/responses` | Not implemented. |
| LLM key proxy (`llm.proxy`) | Not implemented. |
| `legacy_compat` preset | Will not exist: the project is unreleased and has no compatibility layer. |

## 3. Index

Every file below is target design. Where it conflicts with section 1, section 1 and the shipped docs are right.

| File | Content |
|---|---|
| [01-principles.md](01-principles.md) | Rules, scope, vocabulary |
| [02-operation-model.md](02-operation-model.md) | Operation IDs, `@op`, bindings, request pipeline, discovery, custom operations |
| [03-policy-and-permissions.md](03-policy-and-permissions.md) | Allow/deny policy model, scopes, hooks, limits, config layers, errors, threat model |
| [04-builtin-modules.md](04-builtin-modules.md) | Catalog of built-in operations |
| [05-agents-api.md](05-agents-api.md) | OpenAI Agents API served by CLI-agent adapters |
| [06-lazy-install.md](06-lazy-install.md) | Install of agent CLIs after authorization |
| [07-client-mirror.md](07-client-mirror.md) | Client generated from the same catalog |
| [08-template-building-ux.md](08-template-building-ux.md) | `server:` block, build injection, journeys |
| [09-ai-codegen-usability.md](09-ai-codegen-usability.md) | Reference card for AI-written server configuration |

## 4. Decisions that changed the design on the way to the code

* The endpoint table is the only declaration; there is no operation registry beside it.
* Capability switches have one layer (the endpoint policy). `enable_builtin`, `disable_builtin` and `ABX_SERVER_DISABLED_GROUPS` were deleted; a group is an alias for its endpoints.
* There is one dispatcher. The v1 paths are the HTTP bindings; nothing else dispatches.
* An endpoint that the server declares is implemented; what a runtime cannot do is reported by data (`implemented`, `installed`), not by a separate code path.
