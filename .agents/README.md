# `.agents/` — engineering record of the python-sdk repository

Maintainer and AI-agent facing records of **why** the code looks the way it does. Nothing here is imported or
shipped in a wheel. All new documents are written in English.

## Ownership rule

A record lives in the repository that owns the code the decision changed. Contract pages and ADRs for the SDK,
the server runtime and the `template.yaml` schema live here; ADRs for the Node.js CLI live in
[`agent-sandbox/agent-sandbox`](https://github.com/alibaba-agent-sandbox/agent-sandbox/tree/main/.agents). Records never get copied between
repositories: link to the other repository with an absolute URL
(`https://github.com/alibaba-agent-sandbox/<repo>/blob/main/<path>`), never with `../`, never with a bare slug.

## Layout

| Path | Contents |
|------|----------|
| [`notes/`](notes/README.md) | Architecture Decision Records (ADRs), dated and slugged: `YYYY-MM-DD-<slug>.md` |
| `notes/proposed/<category>/` | Under review (`architecture`, `feature`, `process`) |
| `notes/implemented/<category>/` | Accepted and shipped |
| `notes/rejected/` | Considered and rejected, with the reasoning (flat) |
| `notes/superseded/` | Replaced by a newer ADR (flat); carries a `Superseded-by:` line |
| [`research/`](research/README.md) | Pre-design product and competitor research (E2B, Modal, user scenarios) |
| [`evidence/`](evidence/README.md) | Point-in-time artifacts that back a decision: `evidence/research/` (audits) and `evidence/verify/` (test and E2E runs) |

## ADR states

`Status:` on the second line of an ADR **must** equal its state directory.

1. `proposed` — open for review.
2. `implemented` — accepted and merged; the code matches the text.
3. `rejected` — not adopted; keep it so the question is not re-litigated.
4. `superseded` — replaced; keep the file, add `Superseded-by: <slug>`.

Move the file and edit `Status:` in the same commit. Required sections and the template are in
[`notes/README.md`](notes/README.md).

## Research and evidence

- **Research** answers "what is out there" before a design exists; it is not updated afterwards.
- **Evidence** is immutable once written: audit results, full-suite runs and real-cloud verification logs are
  kept verbatim, including the names (`sbox`, `serverless-sandbox`) that were current when they were captured.
  A newer run is a new file, not an edit. Never paste credentials, tokens or machine-local paths.

`scripts/check-repo-health.sh` enforces ADR naming, the `Status:`/directory match, and that no slug dangles.

## Standard E2B behavior work

The active [proposed contract](notes/proposed/architecture/2026-10-16-e2b-behavior-contract.md) defines the pinned Alibaba migration surface and project extension boundary. Verification evidence is point-in-time; read the latest E2B run before reporting completion.

The [provider-boundary verification](evidence/verify/2026-10-16-provider-boundary-review.md) distinguishes standard E2B clients, provider adapters and pending typed management registration.

The multi-agent review proposes [provider context and availability](notes/proposed/architecture/2026-10-16-provider-context-and-availability.md). Standard protocol clients remain separate from the provider API; CLI operation unification is owned by its companion repository.

See the [multi-agent SDK verification](evidence/verify/2026-10-16-multi-agent-provider-review.md) for explicit-provider regressions, source-port maintenance gaps and remaining acceptance gates.
- [Bounded MCP binary files](notes/implemented/feature/2026-10-16-mcp-binary-files.md) · [verification](evidence/verify/2026-10-16-mcp-binary-files.md)

- [Provider portability and updates](notes/implemented/architecture/2026-10-18-provider-portability-updates.md) · [verification](evidence/verify/2026-10-18-provider-portability-updates.md)
- [Independent template deployment metadata](notes/implemented/feature/2026-10-18-template-deploy-feature.md) · [verification](evidence/verify/2026-10-18-template-deploy-feature.md)

- [Provider isolation verification](evidence/verify/2026-10-18-provider-complete-isolation.md)

- [Explicit native engine routing verification](evidence/verify/2026-10-18-provider-explicit-engine-routing.md)

Auth migration: [explicit sandbox API keys](notes/implemented/architecture/2026-10-18-data-plane-auth-contract.md).

Accepted engine recovery: [avoid uncertain mutation replay](notes/implemented/architecture/2026-10-18-engine-write-replay.md).


Configuration composition: [schema resolver](notes/implemented/architecture/2026-10-18-config-schema-composition.md).

- [Legacy retry compatibility](notes/implemented/architecture/2026-10-18-retry-compatibility.md).
Builtin transport: [direct HTTP](notes/implemented/architecture/2026-10-18-native-builtin-data-plane.md).

- [Distinct local listener ports](notes/implemented/process/2026-10-18-distinct-local-server-ports.md).

- [Current paired source installation](notes/proposed/process/2026-10-18-current-source-installation.md).

- [Provider/main integration](notes/proposed/architecture/2026-10-18-provider-main-integration.md) · [verification](evidence/verify/2026-10-18-provider-main-integration.md)
- [Current-host provider integration](evidence/verify/2026-10-18-provider-current-host-checkpoint.md)

- [Provider port and file URL boundary checkpoint](evidence/verify/2026-10-18-provider-port-url-boundaries.md)

- [Standard/provider convergence](notes/proposed/feature/2026-10-18-standard-provider-convergence.md) · [verification](evidence/verify/2026-10-18-standard-provider-convergence.md)
- [Current provider isolation and Express acceptance](evidence/verify/2026-10-18-provider-isolation-acceptance.md)

- [Final provider convergence acceptance](evidence/verify/2026-10-18-provider-convergence-acceptance.md)

- [Provider-owned metadata follow-up](evidence/verify/2026-10-18-provider-owned-metadata-followup.md)

- [Provider preflight](notes/proposed/feature/2026-10-18-provider-preflight.md) · [verification](evidence/verify/2026-10-18-provider-preflight.md)

- [Conditional Express acceptance](notes/proposed/feature/2026-10-19-conditional-acceptance.md) · [verification](evidence/verify/2026-10-19-conditional-acceptance.md)

- [Dispatch native server startup before readiness](notes/implemented/feature/2026-10-19-server-start-acknowledgement.md) · [verification](evidence/verify/2026-10-19-server-start-acknowledgement.md)

- [Canonical guide links](notes/implemented/process/2026-10-19-canonical-guide-links.md) · [verification](evidence/verify/2026-10-19-canonical-guide-links.md)

- [Express conditional support](notes/implemented/process/2026-10-19-express-conditional-support.md) · [verification](evidence/verify/2026-10-19-express-conditional-support.md)

- [Shared conditional Provider operations](notes/implemented/architecture/2026-10-20-provider-conditional-capabilities.md) · [verification](evidence/verify/2026-10-20-provider-conditional-capabilities.md)
