# Decision: Keep Provider usage guidance aligned with actual entry points

Status: proposed

## Problem

The active bilingual guide contradicts its own handshake section with an execution-free installation promise. It lists nonexistent CLI commands, mixes process execution with named application commands and claims Python image builds. A partial authoring manifest omits required operation declarations. Mixed public and internal Sandbox names make the provider extension ambiguous.

## Decision

Describe pre-consent static inspection and default post-consent verification accurately. Use the public ProviderSandbox name. Replace the speculative capability-to-command table with six actual task entries and existing reference links. Link the maintained complete example manifest instead of duplicating an incomplete one. Show one owned sandbox with independent kill/close cleanup, and a complete OpenSandbox connection example after CLI preparation.

## API Design

N/A — no runtime or public API changes. Keep exec, rest and node plugins and the standard Sandbox/AsyncSandbox clients unchanged.

## Alternatives considered

- Keep the large table and add more state labels: repeats the mismatch and creates another maintenance source.
- Add missing CLI commands to justify the table: expands product scope without a user requirement.
- Change historical design records: obscures the original decisions; correct the active guide instead.

## Dependencies

Published CLI 0.4.16, Python client/server 0.3.1a5, existing workflow/server/API guides and example provider manifests.

## Test Strategy

Inspect the actual public CLI parser and published SDK exports. Parse Python snippets, check link targets and run existing network/manifest/doctor tests. Require repository health, hygiene, full current-head CI and docs checks. Reuse unchanged real public-package startup/call/cleanup evidence; no new cloud behavior is introduced.

## Acceptance criteria

- No invented URL/timeout command or Python source-build promise in this guide.
- Consent and handshake descriptions agree with the installer.
- Provider examples use the explicit public extension, valid links and cleanup.
- Required checks and independent review pass before normal merge.

## Evidence

- [Issue #104](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/104)
- [Verification](../../../evidence/verify/2026-10-24-provider-guide-accuracy.md)
