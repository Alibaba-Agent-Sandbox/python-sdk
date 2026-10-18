# Decision: Preserve native provider contracts under standard public clients

Status: proposed

## Problem
The standard client branch predates accepted session/authentication/provider ownership
changes. Globally renaming native configuration keys silently replaces those contracts.

## Decision
Pin live source installation recipes to a tested standard implementation revision,
so the documented entry shape matches installed code. Keep standard synchronous Sandbox and asynchronous AsyncSandbox plus explicit
ProviderSandbox. Retain canonical ABX configuration for native APIs; standard
ConnectionConfig alone reads E2B settings. Compose provider-owned session adapters
at the lower-level registration seam. Keep active standard protobuf but retire gRPC
engine dependencies. Gate native PTY before wire work.

## API Design
The pinned public354 callable signatures and sync/async shape remain unchanged.
Native provider clients preserve explicit ownership and typed qualified-reference failures.

## Alternatives considered
A global E2B key rename breaks accepted native providers; restoring whole old modules
would undo accepted authentication, data plane and cleanup fixes.

## Dependencies
Accepted SDK38 and subsequent provider metadata follow-up; CLI40 is separate.
https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/40

## Test Strategy
Canonical native fixtures, native imports and feature guards, full maintained
checks, separately installed pinned reference, paired package installation, actual
Express standard lifecycle/files/process/interpreter/network scenarios and cleanup.

## Acceptance criteria
Latest-head matrix passes and required real component/artifact checks are recorded.
Conditional pause/snapshot success needs an enabled fixture and remains outstanding.

Accepted native preflight integration: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/68.

## Evidence
[Verification](../../../evidence/verify/2026-10-18-standard-provider-convergence.md).
