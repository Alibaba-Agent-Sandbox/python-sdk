# Decision: Clarify SDK target identities and lifetimes

Status: proposed
Date: 2026-11-25
Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/179

## Problem

The Client SDK entry guide conflates Provider transport with the optional application Server SDK, and does not explain the different target identities or the deleting ProviderSandbox context manager.

## Decision

Document actual Python entries and inputs, default/explicit Provider selection, local close versus remote kill, borrowed connection handling, managed acceptance versus completion, and the boundary between CLI OpenAPI aliases and SDK methods. Keep changes documentation-only.

## API Design

ProviderSandbox.connect takes an actual Sandbox ID. ServerClient takes an application HTTP URL. Managed Agents API uses its Gateway URL with the separate business token. ProviderSandbox.__aexit__ attempts kill even for a connected handle; close leaves the sandbox running.

## Alternatives considered

Do not introduce generic style adapters, rename server routes/decorators, or claim unmerged Provider runtime drafts are available. Do not release packages for prose-only clarification.

## Dependencies

Existing ProviderSandbox and ServerClient source signatures and lifecycle behavior; the managed API already documents idempotency, durable acceptance, files, cancel and delete. CLI journey: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/276 .

## Test Strategy

Audit method signatures and implementations; run repository document/link/record health and content hygiene. No cloud operation or SDK runtime change is required for this documentation correction.

## Acceptance criteria

Both languages explain identifiers and resource ownership without claiming CLI aliases become SDK methods. No runtime behavior changes. Existing source documentation and managed runtime limits remain explicit.
