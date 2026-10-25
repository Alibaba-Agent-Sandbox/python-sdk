# Decision: use installed public imports in template help

Status: implemented

## Problem

Public a4 exports Template, AsyncTemplate and readiness/logger helpers but 24
docstrings still display `from e2b import ...`. A normal installation does not
install e2b, so following this first-party help raises ModuleNotFoundError.

## Decision

Correct only these imports in the five maintained template modules. Execute
each displayed import in regression tests and compare it with the actual public
exports. Prepare minimum lockstep client/server a5 using the existing release
pipeline. Keep current install recommendations at actually public a4 until
official a5 publication is verified. Preserve upstream notices, original hashes,
standard ApiParams and all callable behavior. Save later public-a4 example
acceptance separately without rewriting historical failures or calling it a5.

## API Design

No runtime, signature, export or alias changes. Only help imports and three
paired version/dependency declarations change; no e2b runtime dependency is added.

## Alternatives considered

Adding e2b would conceal incorrect namespace examples and duplicate an owned
source port. Mechanically replacing standard API names or upstream attribution
would damage valid contracts. Editing immutable a4 artifacts is not permitted.

## Dependencies

- https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/128
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/127
- The existing paired publication workflow and maintained standard source port.

## Test Strategy

Run 24 actual help-import regressions before and after the correction. Verify
execution AST equality excluding docstrings, unchanged notices and signatures,
paired builds and full owner checks. After normal review/CI/merge/publication,
compare four public artifact digests and perform fresh non-all installation,
12 Provider help checks, all 24 Template help imports and real HTTP/files with
independent owned-process absence. Public-a4 cloud/local results remain a4 facts.

## Acceptance criteria

All 24 first-party help imports resolve without e2b; API contracts and ownership
notices are preserved. Required exact-head CI/review passes before normal merge.
Publication and public readback must complete before recommending a5. No runtime
feature, alias, new framework or additional publication retry mechanism is added.

[Candidate verification](../../../evidence/verify/2026-10-25-template-help-imports.md).

## Implementation

PR129 was normally merged as c7b4a55ff930753eb35866b161184f946b04d46c; immutable public a5 publisher40222172993 succeeded on attempt1. All 24 Template help imports passed actual public installation. Four remaining class-help errors were separately found and fixed by PR131/public a6; this does not expand the original a5 evidence.

[Subsequent public-a6 delivery](../../../evidence/verify/2026-10-25-public-a6-delivery.md)
records the actual public results. This installation-guidance follow-up has its
own pending CI/review/merge; no later tag or package is created for it.
