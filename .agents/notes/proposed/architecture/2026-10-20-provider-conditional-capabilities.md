# Decision: Register Express conditional operations once for every consumer

Status: proposed

## Problem
Standard clients already implement allowlisted pause/resume and generation2 Snapshots, but these operations are absent from the shared provider command catalog. Duplicating vendor mappings in each consumer would defeat the existing engine architecture.

## Decision
Register six data-plane operations in the bundled Express Provider, reusing provider-commands/1, the generic CLI and authenticated engine, and the existing Python commands client. Keep common typed protocols and the standard compatibility surface stable. The CLI owns backend code; Python adds consumer acceptance and documentation, without a new per-operation dispatcher.

## API Design
The provider owns sandbox.pause, sandbox.resume and snapshot.create/list/restore/delete descriptors, bounded inputs/outputs, effects, a360-second outer deadline and data-plane API-key authentication. Snapshot create defaults to300-second requests. Resume uses connect; Snapshot deletion uses the verified template endpoint with UUID-only input. No schema protocol revision or cloud/model Actions workflow is introduced.

## Alternatives considered
Separate CLI/Python cloud adapters duplicate authentication and lifecycle semantics. Dynamic generation of every typed method would break language tooling and standard compatibility. Promoting service admission failures to unsupported flags confuses registration with runtime readiness.

## Dependencies
Owner Issue: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/78
Python generic-client tracking: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/34
Engine contract: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/reference/engine-api.md
No catalog plugin, shared UI or registry schema changes are required. Aggregated docs remain upstream-owned.

## Test Strategy
Provider wire/schema/error regressions, actual CLI/Python engine discovery, owner full source gates, a fresh standalone binary and local real generation2 acceptance in both directions with memory/file preservation, Snapshot clone isolation and independent cleanup. Record environment-specific failures separately; no mock result substitutes for backend acceptance.

## Acceptance criteria
- Both consumers discover identical descriptors and invoke one registered backend implementation.
- All six operations pass local real Express acceptance with zero owned residuals.
- Authentication domains remain separate; no silent retries or template-name deletion.
- Bilingual guides, README, changelog, contributor boundary, owner evidence and required CI pass before merge.
