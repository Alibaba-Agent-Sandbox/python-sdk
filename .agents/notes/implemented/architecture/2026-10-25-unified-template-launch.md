# Decision: Launch a complete template without workflow selection

Status: implemented

## Problem

A template exposes several services, but selecting a workflow reduced launch to one
operation and made callers choose source/image/native execution types.

## Decision

Specification 5 removes workflow declarations and retains the complete `provides`
map plus the existing startup/readiness commands. `contracts/launch-v1.json` and
`launch-vectors.json` define the shared static launch plan. Old receipt contracts
remain immutable historical inputs and do not certify specification 5 launches.

## API Design

`launch_template(manifest, provider=..., reference=...)` starts a previously prepared
reference, checks SandboxServer protocol v2 services and returns all declared endpoints. Python does
not acquire source building or bare-name catalog resolution: the input is a manifest
mapping or local YAML path. Catalog callers resolve a manifest before launching it.
The static planner returns `supported`, required/missing
operations, all services and an optional unsupported-combination reason.

## Alternatives considered

- Hide the workflow flag while retaining selectable manifests: preserves the source
  of conflicting behavior and incomplete service exposure.
- Infer an old default workflow: hides migration and continues selecting a subset.

## Dependencies

- https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/107
- CLI consumer: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox
- Template owner: https://github.com/Alibaba-Agent-Sandbox/awesome-templates

## Test Strategy

Shared cross-language vectors, SDK model and launcher regressions, full package CI,
and real provider startup/cleanup. Five new startup scenarios passed; all 11 checks
for implementation head `66c86f2` passed. The separate CLI acceptance rerun has an
unconfirmed file-transfer failure tracked in
https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/109.
The final PR, merged main and release-tag CI passed; client/server 0.4.0a1 were
published and independently installed. The public v3 catalog base manifest passed
launch, exec and independently confirmed cleanup through that installed release.
See [publication](../../../evidence/verify/2026-10-25-python-040a1-public-release.md)
and [public catalog integration](../../../evidence/verify/2026-10-25-python-public-catalog-base.md).

## Acceptance criteria

- No workflow argument or current manifest workflow selection remains.
- All declared services survive launch; no unrelated interpreter requirement blocks it.
- Required tests, real-component validation, bilingual docs and changelog are recorded.
- CLI and template consumers migrate together; current v5 receipts are not fabricated.
