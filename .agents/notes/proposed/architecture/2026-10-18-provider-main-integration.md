# Decision: Preserve accepted contracts during provider isolation integration
Status: proposed

## Problem

The provider isolation branch conflicted with accepted authentication, dependency
layering and orphan retirement changes. Choosing either entire side would restore
retired implementations or discard provider-neutral dispatch.

## Decision

Use an ordinary merge and reconcile the active paths. Providers own backend
selection, wire/session adapters and specialized operations. Core transport consumes
structural contracts. Preserve explicit sandbox API key authentication, custom-only
AK/SK exchange and single-attempt mutation behavior. Distribution configuration
metadata is pure data consumed below the provider composition root.

## API Design

Keep historical import paths as aliases of the active implementation. Use one
canonical envd authentication implementation, preserving class identity and defaults.
No retired metadata-only template factory or Python gRPC engine is restored.
Unavailable backend operations remain E8004 rather than falling back to Express.

## Alternatives considered

Taking the old branch wholesale restores retired code. Taking main wholesale loses
provider isolation. Parallel compatibility implementations diverge and break class
identity. Importing the provider registry from transport reintroduces a cycle.

## Dependencies

https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/38 integrates accepted main;
paired contracts are reviewed in https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/35
and https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/38.

## Test Strategy

Run full local suites, focused provider/authentication/compatibility regressions,
typecheck, formatting/lint, health/hygiene and package checks. Exercise Express
against real components locally. Required hosted checks must pass on this exact
head. Preserve host-dependent failures as failures with exact causes.

## Acceptance criteria

No retired implementation returns. Explicit credentials and mutation safety remain.
Provider-isolated dispatch, compatibility imports, lifecycle cleanup and neutral
configuration pass their behavioral regressions. English/Chinese docs and contributor
instructions describe the same current ownership. Required CI/review gates pass.

## Evidence

[Verification](../../../evidence/verify/2026-10-18-provider-main-integration.md).
