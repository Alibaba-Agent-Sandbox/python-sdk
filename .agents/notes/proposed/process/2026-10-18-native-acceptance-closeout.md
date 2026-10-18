# Decision: Record accepted native transport delivery and Droid reproduction
Status: proposed

## Problem

Three accepted source changes still have proposed ADRs. The original held-handle
Droid installation case needs its own real runtime reproduction after migration.

## Decision

Move only the accepted replay/auth/native ADRs to implemented and update current
indexes. Preserve all merged evidence. Add the fresh Droid follow-up with an
immutable link to template-owned proof, keeping source runtime separate from
image deployment/model acceptance.

## API Design

No API or code behavior change.

## Alternatives considered

- Treat a generic background worker as the Droid reproduction: incomplete.
- Rewrite earlier evidence as passed: loses the actual point-in-time result.

## Dependencies

https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/54
https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/56
https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/57
https://github.com/Alibaba-Agent-Sandbox/awesome-templates/pull/109

## Test Strategy

Droid pinned install/short polls/external SDK and HTTP/owned cleanup, independent
readonly reconciliation; record/link/health and required hosted checks.

## Acceptance criteria

- Existing evidence unchanged, accepted ADR status matches its directory.
- Current bilingual architecture docs link the exact acceptance scope.
- Droid source-runtime passes and no owned resources remain.
- Required record/hosted gates pass before merge and issue closure.
