# Decision: Remove verified unused code and record candidate dispositions

Status: implemented

## Problem

The private _a alias-construction wrapper has no repository caller. The older audit example-import findings are already resolved on main.

Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/146.

## Decision

Remove only the unused private configuration wrapper. Preserve Alias, public exports, schema generation, package versions, callback signatures and compatibility arguments.

## API Design

No supported command, option, public export or runtime protocol is removed. This is scoped maintenance; scanner reachability is not an external-usage proof.

## Alternatives considered

- Delete every scanner finding: rejected because callbacks, dynamic registration, public exports and side-effectful expressions need semantic review.
- Patch the old workspace checkout: rejected because accepted main already resolves some findings and unrelated local changes must remain intact.
- Keep all unused private bindings: retains unnecessary code and, for TypeScript, lets new unused declarations accumulate.

## Dependencies

No runtime dependency or version changes.
Each owning repository has its own Issue, branch, record and validation. No package release or manual deployment is part of this task.

## Test Strategy

Run both packages through required lint, formatting, type, test and distribution checks; existing real-component acceptance and current-head CI remain required.
Initial failures, missing prerequisites and later reruns remain separate evidence. Existing behavior tests are reused for deletion-only cleanup; no tests merely assert that source text disappeared.

## Acceptance criteria

- Verified unused bindings are removed while initialization and observable behavior remain.
- Public interfaces, attribution, generated-source ownership and historical evidence are preserved.
- The candidate review below distinguishes removed, upstream-resolved and retained cases.
- Applicable verification and current-head remote CI/review gates pass before merge.

## Consequences

StreamReader.buffer_size explicitly preserves its signature contract. Unreachable yield statements in test async generators determine their function kind and must remain. _cleanup_browser is definition-only in the inspected server tree, but resource teardown ownership needs a lifecycle-specific decision and tests; this patch does not remove it or claim a resource leak. No server runtime implementation is changed.

## Evidence

- [Verification](../../../evidence/verify/2026-10-27-dead-code-cleanup.md)

## Implementation

The scoped implementation merged through https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/147 at `c7a66351127731132fb94937a1ba45aa70bf71fa`. The original verification checkpoint is preserved as history; the acceptance receipt below records the actual remote result.

- [Acceptance receipt](../../../evidence/verify/2026-10-27-dead-code-cleanup-acceptance.md)
