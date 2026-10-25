# Decision: Wait for prepared-template readiness within its existing budget

Status: implemented

## Problem

Public a2 acknowledges the started process, then runs `ready_cmd` once. A valid
application can still be initializing, so an early nonzero health probe fails
launch before `readiness_timeout` expires. OpenSandbox T4 observed this after
successful default CLI build, push, launch and application calls.

## Decision

Poll nonzero readiness results inside one monotonic `readiness_timeout` budget.
Constrain each command await by its remaining budget and preserve the provider's
positive integer command timeout. Keep the existing failure reason/phase and owned
cleanup, including cancellation. Do not replay creation or startup. Prepare the
immutable lockstep client/server 0.4.0a3 pair; a2 artifacts remain unchanged.

## API Design

No parameters, launch modes, provider declarations or states are added. This budget
covers `ready_cmd` probes; existing startup-acknowledgement and per-service health
budgets are unchanged. Invalid results and transport errors still fail immediately.

## Alternatives considered

Adding a fixed sleep to the provider test would hide the product race. Retrying the
entire create/launch could duplicate resources. A new readiness framework or global
launch-budget redesign is unnecessary for this defect.

## Dependencies

- https://github.com/Alibaba-Agent-Sandbox/awesome-providers/pull/40
- Existing public a2 and CLI readiness semantics; no provider implementation change.

## Test Strategy

Regress delayed success after early failure, bounded permanent failure and hanging
probes, cancellation and owned cleanup. Compare installed public a2 with the exact
candidate against a real prepared sandbox. Run owner checks and complete real
OpenSandbox T4 on the candidate; public a3 installation/readback follows publication.

## Acceptance criteria

Focused/full tests, owner CI, real readiness scenarios and provider T4 pass with
independent owned cleanup. Normal review/merge and lockstep publication/readback
complete before claiming public delivery. Preserve failed and historical receipts.

[Verification](../../../evidence/verify/2026-10-25-prepared-template-readiness.md).

Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/121

## Implementation

PR 122 merged and immutable public a3 publication/readback completed. Real delayed-readiness, bounded failure and cancellation with independent owned cleanup passed; provider PR 40 completed its real Docker T4 and merged. Issue 121 is completed. This did not change the whole-launch budget.
