# Decision: Use verified public a4 and bound metadata visibility waits

Status: proposed

## Problem

Current guidance and fixture pins still select a3 after the verified a4 delivery.
The original a4 publisher exhausted six metadata-404 probes over 50 seconds even
though upload succeeded. Later canonical metadata and original artifacts matched;
normal same-tag retry succeeded without changing public files.

## Decision

Update maintained bilingual installs, two skills and two fixture recipes to exact
public a4 with the official index. Keep actual guest assertions aligned. Record
both publication attempts and four-file comparisons without editing old evidence.
Move only the completed readiness/a3-guidance/provider-docstring notes to implemented.

Give only the existing metadata-404 loop 18 attempts separated by ten seconds
(170 seconds of intervals). Keep fresh-install attempts at six and preserve hard
digest/non-404/auth/pip-check/import failures. This is bounded headroom, not a
promise that every future PyPI delay fits the window. The immutable a4 tag retains
its six-probe workflow; this source change applies to future releases.

## API Design

No SDK runtime, version, alias, export, state or configuration changes. Client/server
remain immutable public a4. Reuse the existing workflow and its shell regression
helper; do not add a new publication framework.

## Alternatives considered

Recommending a4 before publication would have been inaccurate. Retrying hashes or
all release operations could hide real failures. Infinite waits or a new service
are unnecessary; the existing loop needs a modest bounded window.

## Dependencies

- https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/126
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/125
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases/tag/v0.4.0a4
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40215483508

## Test Strategy

Compare both preserved four-file artifact sets with official metadata and actual
bytes; fresh-install exact client a4 with its automatic server dependency and no
source injection. Verify corrected help/signatures, actual old-keyword rejection
and real local HTTP/process cleanup. Execute the maintained shell with controlled
command statuses to prove success beyond the former six-probe boundary, finite
18-probe exhaustion, unchanged installation bounds and immediate hard failures.
Run docs/owner checks and existing actual Docker fixture jobs on public a4.

## Acceptance criteria

Current install/skill/fixture guidance selects actually public a4. Both attempts
and their exact scope remain recorded. The extended metadata loop is finite and
only retries the existing HTTP404-derived exit75. Required exact-head CI, independent
review and normal merge pass; no new SDK publication is performed for this follow-up.

[Verification](../../../evidence/verify/2026-10-25-public-a4-delivery.md).
