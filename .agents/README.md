# `.agents/` — engineering record of the python-sdk repository

## Published specification 5 alpha — 2026-10-25

Client/server **0.4.0a1** are public. [Release verification](evidence/verify/2026-10-25-python-040a1-public-release.md) records immutable tag identity, required CI, four public artifact hashes matched to the preserved candidate, and fresh exact-version installation. The [public catalog integration](evidence/verify/2026-10-25-python-public-catalog-base.md) verifies the released SDK against the live specification 5 base manifest. This host release does not update existing sandbox images or imply whole-catalog production certification.

## Specification 5 migration — 2026-10-25

The [implemented unified startup design](notes/implemented/architecture/2026-10-25-unified-template-launch.md)
removes workflow selection and preserves all template services. The
[contract foundation](evidence/verify/2026-10-25-unified-template-contract.md) records
local shared-vector checks only. [Runtime checkpoint](evidence/verify/2026-10-25-unified-template-runtime.md) records
real native-template acceptance and retained environment failures. The
[cloud follow-up](evidence/verify/2026-10-25-unified-template-cloud.md) verifies all five
startup scenarios including two HTTP services. The [CLI diagnostic follow-up](evidence/verify/2026-10-25-unified-template-cli-diagnostic.md) keeps the separate passing and failing CLI runs, final implementation CI and focused file-transfer results explicit;
the previous 92-case matrix below remains specification 4 history, not v5 evidence.
The [publication preflight](evidence/verify/2026-10-25-python-a1-publication-preflight.md)
records candidate checks and stable installation requirements without claiming publication.

## Previous delivery — 2026-10-24

- Published client/server pair: **0.3.1a5**, with [immutable public artifacts, fresh installation and retained propagation failure](evidence/verify/2026-10-24-python-a5-public-release.md). This is an alpha release; host installation does not update in-image runtimes.
- Standard `Sandbox`/`AsyncSandbox` and `code_interpreter` clients retain their migration contract. Asynchronous `ProviderSandbox` owns provider/server extensions; [SDK usage](../docs/en/guide/sdk-usage.md) now keeps process execution, interpreter calls, application HTTP and resource cleanup separate.
- Python consumes installed Node providers through the CLI engine; exec/rest providers run directly. [Provider guidance](../docs/en/guide/providers.md) owns the language boundary and content-based Git catalog updates.
- [Managed workflow acceptance](evidence/verify/2026-10-24-managed-native-workflows.md) and [proxy application authentication](evidence/verify/2026-10-24-application-proxy-token.md) record their exact operations. Unified interpreter support is not implied by shell execution on an interpreter image.
- The [92-case matrix](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/78c30fbbd186cb59c3a0f0abd9fdf85b10c84b35/.agents/evidence/verify/2026-10-24-public-template-matrix.md) used public client/server host installation 0.3.1a5 and CLI 0.4.16. Dockerfile runtime pins remained their own inputs; real-model, PTY and desktop claims remain outside that matrix.

[Documentation synchronization decision](notes/implemented/process/2026-10-24-current-docs-and-records.md) · [verification and acceptance reconciliation](evidence/verify/2026-10-24-current-docs-and-records.md).

Earlier entries below are a decision history. A remaining proposal is not a current product guarantee; read the linked acceptance scope before treating its full criteria as complete.


- [Native process OS user](notes/implemented/feature/2026-10-24-native-process-user.md) · [verification](evidence/verify/2026-10-24-native-process-user.md)

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

- [Named-command string arrays](notes/implemented/feature/2026-10-20-named-string-array.md) · [verification](evidence/verify/2026-10-20-named-string-array-final.md).

- [Remove retired project compatibility](notes/implemented/architecture/2026-10-22-remove-legacy-compatibility.md) · [verification](evidence/verify/2026-10-22-remove-legacy-compatibility.md)

- [Compatibility cleanup remote acceptance](evidence/verify/2026-10-22-remove-legacy-acceptance.md)

- [Current compatibility-removal documentation verification](evidence/verify/2026-10-22-remove-legacy-docs.md).

- [Explicit template workflows](notes/implemented/architecture/2026-10-23-template-workflow-contract.md) · [canonical vectors](evidence/verify/2026-10-23-workflow-foundation.md) · [provider operations](evidence/verify/2026-10-23-provider-workflow-operations.md) · [independent second-round review](evidence/verify/2026-10-23-workflow-round2-independent.md).
- [Workflow runtime implementation and review](evidence/verify/2026-10-23-workflow-runtime-review.md).
- [Workflow migration real-cloud acceptance](evidence/verify/2026-10-23-workflow-real-cloud.md).
- [Workflow CI follow-up](evidence/verify/2026-10-23-workflow-ci-followup.md).
- [Current workflow documentation and Python matrix](evidence/verify/2026-10-23-workflow-current-docs.md).
- [Workflow YAML base-install correction](evidence/verify/2026-10-23-workflow-base-yaml-install.md).
- [Immutable workflow source installation](evidence/verify/2026-10-23-workflow-source-install.md).

- [Native startup acknowledgment correction](evidence/verify/2026-10-23-native-startup-acknowledgment.md).

- [Native startup identifier wire table](evidence/verify/2026-10-23-native-startup-wire-table.md).
- [Complete OpenSandbox workflow acceptance](evidence/verify/2026-10-23-workflow-opensandbox-acceptance.md).
- [Provider error reference anchors](evidence/verify/2026-10-23-workflow-provider-error-anchors.md).

- [Python alpha release](notes/implemented/process/2026-10-24-python-alpha-release.md) · [verification](evidence/verify/2026-10-24-python-alpha-release.md)

- [Python alpha real-component acceptance](evidence/verify/2026-10-24-python-alpha-cloud.md).

- [Managed native workflows](notes/implemented/feature/2026-10-24-managed-native-workflows.md) · [public a3 verification](evidence/verify/2026-10-24-python-a3-public-release.md).
- [Application proxy token](notes/implemented/feature/2026-10-24-application-proxy-token.md) · [runtime verification](evidence/verify/2026-10-24-application-proxy-token.md).
- [Accurate packaged installation guidance](notes/implemented/process/2026-10-24-package-installation-docs.md) · [public a5 release](evidence/verify/2026-10-24-python-a5-public-release.md).

- [Provider guide accuracy](notes/implemented/process/2026-10-24-provider-guide-accuracy.md) · [verification](evidence/verify/2026-10-24-provider-guide-accuracy.md).

- [Current example entry points](notes/proposed/process/2026-10-25-current-example-entrypoints.md) · [verification](evidence/verify/2026-10-25-current-example-entrypoints.md)

- [Command execution deadline](notes/proposed/feature/2026-10-25-command-execution-deadline.md) · [verification](evidence/verify/2026-10-25-command-execution-deadline.md)

- [Bounded public PyPI readback](notes/proposed/process/2026-10-25-pypi-public-readback.md) · [verification](evidence/verify/2026-10-25-pypi-public-readback.md)
