# Decision: Explicit template workflows and operation contracts

Status: proposed

## Problem
Template application services, provider interpreter APIs and consuming clients were conflated. A code feature could incorrectly block an otherwise executable application, while shell fallback could conceal a missing interpreter.

## Decision
Use template specification 4 and shared operation contract 1. The canonical JSON in `contracts/` defines independent workflows, startup/input constraints, exact interpreter operations, static three-state plans and non-removable verification profiles. Package byte-identical copies for standalone Python installations. Reject retired capability and hand-written coverage inputs.

## API Design
`validate_workflow_manifest(manifest)` validates the shared portion. `plan_workflow(manifest, provider, workflow_id, consumer)` returns deterministic per-operation requirements and T/F/U without loading plugins or contacting a platform. Content identity helpers hash exact manifest bytes, eligible immutable source snapshots and canonical string-only bindings.

## Alternatives considered
- Infer execution support from a broad code capability: cannot distinguish application HTTP, persistent contexts, streaming and stateless execution.
- Accept previous schema inputs: unnecessary before first release and makes readiness ambiguous.

## Dependencies
CLI consumers: https://github.com/alibaba-agent-sandbox/agent-sandbox ; template producer: https://github.com/alibaba-agent-sandbox/awesome-templates ; provider producer: https://github.com/alibaba-agent-sandbox/awesome-providers ; catalog consumer: https://github.com/alibaba-agent-sandbox/registry . Standard pinned E2B clients remain a separate contract.

## Test Strategy
Canonical cross-language vectors cover valid services, input/startup mismatches, strict rejection, exact context operations and consumer boundaries. Identity regressions cover content, paths and local untracked inputs. SDK runtime and endpoint regressions plus repository CI validate integration.

## Acceptance criteria
Python and CLI pass the same vectors. Package copies match canonical bytes. Current consumers use exact operations and never silently fall back to shell. Runtime and real-component checks are recorded separately; design acceptance does not certify execution.
