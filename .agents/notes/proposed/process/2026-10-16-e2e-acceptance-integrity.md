# Decision: Require executed checks and correct credentials in cloud acceptance

Status: proposed

## Problem

The complete SDK cloud suite sends an envd token to the unconfigured template
server, preventing its fixture from becoming ready. Separately, provider report
assertions ignore missing expected rows; the CLI helper assumes an obsolete
sibling checkout and can report acceptance without invoking a CLI.
[Issue 41](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/41) and
[issue 42](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/42) record the distinct failures.
[Issue 43](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/43) covers
blind CubeAPI detection from an unrelated default-port listener.

## Decision

Match the production `Sandbox.server_at` credential boundary in the raw server
fixture, require every expected pass/refusal row in provider reports, and resolve
the CLI through explicit `ABX_BIN` or PATH. Require an explicit CubeAPI live target
and probe the selected host/port; accept host E1003 and provider E1001 credential
refusals. Preserve all cloud assertions. Set up
catalog plugins in a throwaway test HOME with normal consent/doctor verification
before credential-refusal acceptance; do not skip those assertions to hide setup gaps.

## API Design

N/A — this decision does not involve API changes. The new CLI resolution helper
is internal to the E2E harness; `ABX_BIN` already supports arguments in the SDK.

## Alternatives considered

- Accept an unrelated blocked row as successful feature coverage: rejected.
- Keep forwarding the envd credential or suppress server assertions: rejected
  because the production template server uses a separate authentication boundary.
- Assume a workspace-specific CLI path: rejected for standalone checkout support.

## Dependencies

Existing SDK, installed/built CLI, catalog provider source and authorized Express
configuration. Other-provider backend credentials are never borrowed from Express.

## Test Strategy

Offline positive/negative regressions cover missing reports, missing refusal rows,
wrong statuses, complete reports and standalone CLI resolution. Restore the old
harness as a negative control, then rerun the complete real cloud suite with the
real CLI and isolated verified catalog installation. Record all failures/skips
and verify cleanup without deleting resources owned by other runs.

## Acceptance criteria

- An empty/partial/blocked-unrelated report fails; complete correct reports pass.
- The real CLI runs without requiring a sibling repository.
- The actual template server is reached without an unrelated envd credential.
- Real cloud results, required repository gates and cleanup are recorded.

## Evidence

- [Verification](../../../evidence/verify/2026-10-16-e2e-acceptance-integrity.md)
