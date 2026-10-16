# Decision: Complete the Chinese OpenSandbox research archive

Status: proposed

## Problem

The English OpenSandbox archive lacks its Chinese counterpart. Repository health
fails the required documentation correspondence gate, blocking dependent work.
[Issue 39](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/39) records the failure.

## Decision

Translate the complete archived research into
`docs/zh/archive/provider-opensandbox-research.md`, preserving all numbered sections,
API/configuration/error mappings, limits, historical commands, test proposals,
source references and 2026-10-13 evidence boundaries. The English original remains
unchanged. The page explicitly links the current in-engine adapter and does not
present the old Python sketch or Node exec-plugin results as the shipping path.

## API Design

N/A — this decision does not involve API changes.

## Alternatives considered

- Exempt the missing page from health checks: rejected because it hides the gap.
- Add a redirect-only placeholder: rejected because readers need the archived findings in Chinese.
- Rewrite historical verification as current behavior: rejected because it falsifies evidence.

## Dependencies

The existing English archive, current Chinese adapter mapping and repository
documentation/engineering-record conventions. No runtime dependency changes.

## Test Strategy

Run repository health, hygiene, whitespace, section correspondence and local-link
checks. Verify the original English archive is unchanged. Scan scoped files against
authorized secret values without emitting them. This prose-only change creates
no cloud resources and does not claim a new product E2E result.

## Acceptance criteria

- All archived sections and their technical distinctions are available in Chinese.
- Historical evidence is preserved and distinguished from the current adapter.
- Repository health has zero failures and scoped checks pass.

## Evidence

- [Verification](../../../evidence/verify/2026-10-16-opensandbox-archive-translation.md)
