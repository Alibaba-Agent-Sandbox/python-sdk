# Decision: finish owned namespaces in public Sandbox help

Status: proposed

## Problem

Public a5 fixed 24 Template help imports but four ordinary Sandbox class examples
still import unavailable e2b/e2b_code_interpreter packages. The interpreter classes
have a distinct public entry and must not be replaced by root Sandbox classes.

Current bilingual API/lifecycle pages also mix unsupported Provider interpreter
calls, retired configuration names and an unimplemented global cleanup policy.
Their examples must describe actual APIs rather than a speculative type menu.

## Decision

Correct only the four class-help imports and prepare minimum lockstep a6.
Keep immutable a5 and all its scoped results. Correct the two bilingual current
API/lifecycle pages and delete unimplemented persistent/hibernated/global-cleanup
examples and unsupported pricing/startup claims. Do not implement those proposals.
Keep interpreter/application prerequisites separate. Audit every shipped Python source
docstring and every maintained Markdown/Skill import context, preserving explicit
migration inputs, third-party comparisons, valid standard parameters and notices.
Retain public-a4 installation recommendations until a6 is actually public, then
update maintained instructions once. No compatibility alias or new dependency.

## API Design

Root standard classes import from agent_sandbox; interpreter classes import from
agent_sandbox.code_interpreter. Callable behavior, signatures and exports are
unchanged; only help and three paired version/dependency declarations change.

## Alternatives considered

Adding upstream packages would conceal incorrect first-party help. Broadly
renaming E2B references would damage attribution and legitimate contracts.
Changing immutable a5 or recommending unpublished a6 is not acceptable.

## Dependencies

- https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/130
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/129
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases/tag/v0.4.0a5

## Test Strategy

Execute four class-help imports and assert exact identity in the correct namespace.
Retain 24 Template imports and 12 Provider help checks. Audit all 390 source files,
2358 docstrings and 174 maintained Markdown files including both Skills; prove
four source residues become zero without upstream runtime imports or executable
AST changes excluding docs. Run owner checks and required exact-head CI. After
normal merge/tag/publication compare four public artifact hashes, fresh-install
non-all a6 and verify all 28 help imports, Provider help, real HTTP/files and
independent owned-process absence.

Run all six Python block occurrences in the four current design documents as
two byte-identical unique programs using official public packages. Require actual
typed E3001 and independent owned-resource absence. Execute current documented
owned-SDK imports with explicit history/proposal/development exclusions.

## Acceptance criteria

All shipped first-party help imports resolve without upstream SDK dependencies.
Legitimate migration/comparison examples and notices are preserved. Normal CI,
independent review and merge precede the existing paired publisher and official
readback. No new runtime feature, API, alias, dependency or release framework.

[Verification](../../../evidence/verify/2026-10-25-sandbox-help-namespace.md).
