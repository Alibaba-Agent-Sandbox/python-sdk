# Decision: Check native PTY before terminal context or wire access

Status: proposed

## Problem
The native Express terminal implementation did not enforce its declared PTY
feature before touching the supplied session and wire adapter. The fix was trapped
in the larger conditional migration branch.

## Decision
Apply the provider declaration check at the start of open_terminal. Preserve the
existing native public API and available Express behavior independently of migration.

## API Design
Undeclared PTY raises ProviderFeatureNotSupportedError before context or network
access. Valid declared terminal calls continue through the existing adapter.

## Alternatives considered
Waiting for unrelated snapshot/standard frontend prerequisites leaves the defect
on main. Failing later with attribute or transport errors loses the typed contract.

## Dependencies
Current accepted main5a99f0fa. Related owner migration issue:
https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/36
Companion CLI issue https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/33.

## Test Strategy
Observe failing unguarded access, verify the feature error, run all maintained client
checks and real available Express lifecycle/terminal/server coverage and cleanup.

## Acceptance criteria
Regression, maintained client checks and real available backend acceptance pass;
latest full hosted matrix passes before normal merge. No conditional feature is enabled.

## Evidence
[Verification](../../../evidence/verify/2026-10-18-provider-preflight.md).
