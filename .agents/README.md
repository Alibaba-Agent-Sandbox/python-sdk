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

- [Bounded MCP binary files](notes/implemented/feature/2026-10-16-mcp-binary-files.md) · [verification](evidence/verify/2026-10-16-mcp-binary-files.md)

- [Provider portability and updates](notes/proposed/architecture/2026-10-18-provider-portability-updates.md) · [verification](evidence/verify/2026-10-18-provider-portability-updates.md)
- [Independent template deployment metadata](notes/implemented/feature/2026-10-18-template-deploy-feature.md) · [verification](evidence/verify/2026-10-18-template-deploy-feature.md)

- [Provider isolation verification](evidence/verify/2026-10-18-provider-complete-isolation.md)
