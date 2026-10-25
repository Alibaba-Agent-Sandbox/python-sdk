# Decision: Clarify template startup ownership

Status: proposed

## Problem

The prepared-reference guide does not explain that ordinary native deployment can retain its own startup command. Combining that reference with a manifest startup can run the same service twice. The SDK Skill also says specification 4 above a specification 5 manifest.

## Decision

Recommend unified CLI source launch followed by SDK connection. Describe Python prepared-reference launch as an advanced path that creates a sandbox and owns the manifest startup; its native entrypoint must not duplicate that service. Correct the Skill prose to specification 5.

## API Design

N/A — this decision does not involve API changes. No new preparation mode, selector, environment alias or package version.

## Alternatives considered

A generic empty-startup flag recipe would hide profile-dependent preparation and does not establish that a service is idle. A runtime modification is unnecessary: the controlled official a6 experiment already passed the documented startup and authentication behavior.

## Dependencies

- https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/133

- https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases/tag/v0.4.0a6
- https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/releases/tag/v0.5.5

## Test Strategy

Preserve the existing bounded real public-package startup/auth/owned-cleanup result, inspect current CLI/SDK startup semantics, and run owner documentation, hygiene and exact-head required CI checks. Do not relabel other preparation paths or the catalog as tested.

## Acceptance criteria

Both languages distinguish CLI connection from Python-owned startup without inventing another user-facing state. Skill prose matches its manifest. No Python implementation, test, dependency or version changes; required checks, review and normal merge complete.

## Evidence

- [Verification](../../../evidence/verify/2026-10-25-template-startup-ownership.md)
