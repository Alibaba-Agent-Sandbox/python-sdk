# Architecture review: over-design, duplication and experience contradictions

> **Status: review record, not the current specification.** Review date 2026-10-13, covering the `cli` package (`@agent-sandbox/cli`, command `abx`) and `python-sdk` (`agent-sandbox`, `agent-sandbox-server`). The full analysis (evidence locations, P0 to P2 findings, size figures) exists only in Chinese: [zh/design/architecture-review.md](../../zh/design/architecture-review.md). This page carries the status table, matching the Chinese one, and is not a translation. The body of the review is a snapshot from review time; paths and names are unchanged.

## Status after the 2026-10-13 cleanup

| Item | Status |
|---|---|
| P0 1.1-1.4: secret variable name, drop the "E2B-compatible / drop-in" tagline, remove the global `--profile`, `config init` asks only for credentials and region by default | Done |
| P1 2.1: run agents only through the Agents API | Done. `BUILTIN_AGENTS`, `abx agent` and the built-in agent design are deleted |
| P1 2.2: named commands only through the server `CommandRegistry` | Done. Client `Sandbox.custom` and template `custom_commands` are deleted |
| P1 2.3: server migration | Done. One `ENDPOINTS` table, one `PolicyEngine`, one pipeline. The v1 HTTP paths are bound to that table. `/ops` is deleted |
| P1 2.4: one layer of capability switches | Done. A group is only an alias that expands to endpoint ids. `ABX_SERVER_DISABLED_GROUPS` is deleted |
| P1 2.5: OSS / VPC / custom domain that existed only in the README | Deleted. The platform exposes no per-sandbox API for them. `compat` stays as a partial migration helper |
| P1 2.6: CLI command surface | Done. Top-level shortcuts are fixed; `exec` absorbs streaming execution; there is no `sandbox process start` |
| P2 3.1: TypeScript re-implementing click / rich / pydantic | Done. Commands sit on commander (`cli/src/cli/kit.ts`). Models use zod, terminal color uses picocolors, YAML uses the `yaml` package. The Click, Rich and Pydantic ports are deleted |
| P2 3.2: two languages each writing their own copy | Boundary set: the Python SDK is the runtime client; the CLI owns template building and deployment. Build code has been removed from the client |
| P2 3.3: provider plugins | The abstraction stays. OpenSandbox runs from both the CLI and the Python SDK |
| P2 3.4: width of the Agents API | Routes stay. `GET /v1/agents/runtimes` reports `implemented` and `installed`. An adapter with no local execution backend returns a typed 404 |
| P2 3.5: docs reorganisation | Done. Reviews and the server-sdk-v2 target design now live under [archive/](../archive/) |

## Full analysis

Read [zh/design/architecture-review.md](../../zh/design/architecture-review.md) for the findings behind each row.
