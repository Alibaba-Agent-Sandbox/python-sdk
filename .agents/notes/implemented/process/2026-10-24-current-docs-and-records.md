# Decision: Synchronize current documentation and accepted records
Status: implemented

## Problem
Current user guides and engineering entry points still contain stale installation, usage or pending-status descriptions after recent delivery.

## Decision
Update only this owner's current guides and index the actual release, implementation and verification boundaries. Reconcile dated notes with verified merged PRs. Preserve merged evidence verbatim and keep source/provider/consumer versions explicit.

## API Design
N/A — documentation only; no runtime API, package version or publication changes.

## Alternatives considered
Do not copy a whole cross-repository report or rewrite historical failures into passes. Do not infer broad platform support from an unrelated passing test.

## Dependencies
The already-merged owner PRs and dated receipts linked in this repository's engineering index. Related repositories own their own documentation and records.

## Test Strategy
Run document/record/link checks and the normal remote CI gates. Check examples against the current public API and existing real-component evidence. No cloud rerun is needed for this documentation-only synchronization.

## Acceptance criteria
Current English/Chinese instructions agree with implemented entry points; accepted notes match their state directory; local links resolve; old evidence is unchanged; required latest-head CI and independent review pass before merge.

## Evidence
[Verification](../../../evidence/verify/2026-10-24-current-docs-and-records.md).
