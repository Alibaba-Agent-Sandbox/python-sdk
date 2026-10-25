# Decision: Launch a complete template without workflow selection

Status: proposed

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
reference, checks all SandboxServer services and returns their clients. Python does
not acquire source building. The static planner returns `supported`, required/missing
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
and real provider startup/cleanup. Current runtime verification is pending.

## Acceptance criteria

- No workflow argument or current manifest workflow selection remains.
- All declared services survive launch; no unrelated interpreter requirement blocks it.
- Required tests, real-component validation, bilingual docs and changelog are recorded.
- CLI and template consumers migrate together; current v5 receipts are not fabricated.
