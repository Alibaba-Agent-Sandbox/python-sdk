# Decision: Docs ownership audit — the `python-sdk` repository documents only the SDK

Status: implemented

## Problem
`python-sdk/docs` kept near-duplicate copies of CLI pages and long `ebx` command walkthroughs in
guides, the README, `AGENTS.md` and `llms.txt`. The design index linked CLI design pages, so an SDK
reader was sent to the CLI repository for SDK material and the other way round. The health check
flagged byte-identical pages shared with `cli/docs`, and the `template.yaml` contract, which the
SDK owns, existed twice.

## Decision
1. **Ownership principle.** Every page is owned by exactly one repository and describes only that
   repository. This repository owns the Python client SDK (`easy-sandbox`), the server runtime
   (`easy-sandbox-server`), the server HTTP API, the SDK architecture, the E2B compatibility layer
   and the `template.yaml` contract. The CLI repository owns the `ebx` command surface and its
   distribution.
2. **Audit.** Classification of every page (en and zh mirrors are in step except the English-only
   maintainer drafts):

| Page (under `docs/{en,zh}/` unless noted) | Class | Disposition |
|---|---|---|
| `design/architecture`, `sdk-api-design`, `server-api`, `sandbox-types`, `built-in-agents`, `template-system` | SDK | kept; CLI sections reduced to a Related: the ebx CLI section |
| `design/mcp-server` | shared concept | kept as the SDK view (`python -m easy_sandbox.agent.mcp`, HTTP app, FC artifact contract); `ebx mcp` commands moved to a pointer |
| `design/agents-api*`, `fine-grained-capabilities*`, `provider-opensandbox-mapping`, `providers-and-credentials*`, `server-sdk-v2/*`, `base-image-and-server-sdk`, `client-server-alignment`, `repository-layout` | SDK | other workers' English-only drafts; not edited (listed in the Maintainer Design Documents table of `DESIGN.md`) |
| `design/agents-api-cli-followups` | CLI | CLI-owned content that lives here; flagged, not moved (another worker owns it) |
| `DESIGN.md`, `README.md`, `docs/README.md` | SDK | rewritten as SDK-only indexes (`docs/README.md` is a short bilingual pointer) |
| `explanation/architecture-overview`, `e2b-compatibility`, `sandbox-lifecycle` | SDK | kept; CLI mentions reduced to pointers |
| `guide/sdk-usage`, `declarative-usage`, `session-persistence`, `migrate-from-e2b`, `migrating-from-0.2`, `comparison`, `providers` | SDK | kept; `sdk-usage` gained the agent workflow pattern |
| `guide/build-and-deploy` | SDK | new (en+zh): `Sandbox.deploy`, `Image` and the build/push flow as a Python API; the `ebx deploy` command stays in the CLI |
| `guide/getting-started`, `authentication`, `authoring-templates`, `mcp-integration`, `troubleshooting`, `environment-variables` | shared concept | kept as SDK views; `ebx` sections removed after confirming the CLI page holds them; Related: the ebx CLI section |
| `reference/api-reference`, `server-http-api`, `template-yaml-spec` | SDK | kept; `template-yaml-spec` is the single owner of the `template.yaml` contract |
| `reference/configuration`, `reference/error-codes` | shared concept | kept as SDK views (client/server config, `E*` codes raised by Python); `ebx config` command sections removed; provider-layer content is others' |
| CLI pages (CLI design, tutorial, reference, using templates, deploy and build command guide, binary installation, BYO agent, Agent Skill, E2E template workflow, templates catalog) | CLI | not present in this repository; the READMEs, `AGENTS.md` and `llms.txt` point to the CLI repository with absolute URLs |

3. **Shared concepts.** See the CLI ADR: view pages in both repositories, with the
   credential-resolution order as the only verbatim shared contract.
4. **Information moves.** Content that existed only here and described the CLI was checked against
   the [CLI docs](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/README.md) before removal (cache and market command notes went to
   `templates-catalog` section 9 there). Content that existed only in the CLI copy and described the
   SDK (`Sandbox.deploy`, `Image`, the agent workflow) was moved here first.
5. **Link policy.** Relative `../cli` links became absolute
   `https://github.com/Easy-Sandbox/easy-sandbox/blob/main/...` URLs (15 files); every page that needs the
   CLI has one "Related: the ebx CLI" section (anchor `#related-the-ebx-cli`, zh
   `#相关ebx-cli`). The READMEs' long `ebx` example blocks were replaced by that section because the
   CLI README holds the same commands.
6. **Indexes.** `docs/README.md`, `docs/{en,zh}/README.md`, `docs/{en,zh}/DESIGN.md`, `README.md`,
   `README.zh-CN.md`, `AGENTS.md` (golden-file evidence and CLI resolution sections removed; they live
   in the CLI `AGENTS.md`) and `llms.txt` describe only the SDK.

## API Design
N/A — this decision does not involve API changes.

## Alternatives considered
- **Keep parallel full copies of every page in both repositories** — rejected: the copies drift
  (several pages already differed) and a reader of one repository is sent to the other for its own
  architecture.
- **Make one repository the single home of all shared-concept pages and link from the other** —
  rejected: credential, configuration, error-code and MCP pages are read in the context of the tool
  in hand (`ebx` commands versus Python calls); a pure link loses that context. Only the contract
  parts are shared (see Decision 3).
- **Create a third documentation repository** — rejected: no tooling or ownership benefit for two
  repositories, and it would split the bilingual page sets again.

## Dependencies
The `cli` repository's matching audit
([ADR](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/.agents/notes/implemented/process/2026-10-12-docs-ownership-audit.md)), so that every
section removed here exists in the CLI repository.

## Test Strategy
- `scripts/check-repo-health.sh`: no relative link escapes the repository, relative markdown links
  resolve, no page byte-identical with `../cli`.
- `scripts/check-no-local-paths.sh`: the edited files add no findings.
- Manual: removed sections were compared with the CLI pages; relative-link checker run over both
  repositories after the edits.

## Acceptance criteria
- `docs/en/DESIGN.md` and `docs/zh/DESIGN.md` index only SDK-owned pages (plus the Related section).
- No documentation page here describes `ebx` commands in depth; only pointers remain.
- `template-yaml-spec` exists here only; the CLI repository links to it.
- The check "no byte-identical doc pages shared with ../cli" passes.
- Every link to the CLI repository is an absolute URL.

## Consequences
- `design/agents-api-cli-followups.md` is CLI content kept here until its owner moves it
  (it is still English-only).
- Remaining health FAILs are in other workers' files (agents-API link and parity, machine-local
  paths in provider and server-sdk-v2 drafts, missing `e2e/README.md`).

## Files changed
New: `docs/{en,zh}/guide/build-and-deploy.md`. Rewritten or pruned: pages marked above plus
`README.md`, `README.zh-CN.md`, `AGENTS.md`, `llms.txt`, `docs/README.md`.
