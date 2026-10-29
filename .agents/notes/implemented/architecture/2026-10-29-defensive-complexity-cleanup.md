# Decision: Reduce redundant interaction and execution branches

Status: implemented

## Problem

Source review found duplicate paths, hidden failures and misleading examples that increase maintenance cost and surprise callers. Removing defensive code indiscriminately would also remove real compatibility and authorization guarantees.

Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/150

## Decision

Use one lazy background event loop for synchronous calls and reuse it from decorators. Cancel submitted work when the waiting caller is interrupted and reject synchronous callback re-entry before self-deadlock. Close borrowed/retained decorator clients. Parse command input once, preserve quoted literals and explicit background shell execution. Propagate lifecycle failures; retain the session record when remote deletion fails.

Correct English and Chinese guides to describe supported user workflows. Keep verification history in engineering records. Independent opposing review required a concrete counterexample before deleting a safety or compatibility branch.

## API Design

Existing ProviderSandbox *_sync signatures remain. Calls block on a shared loop; one client must use a consistent execution style. run(..., background=True, shell=True) preserves shell expansion. is_running propagates authentication/network/service errors. SessionManager.stop propagates kill errors and preserves the local record for retry. Root standard Sandbox/AsyncSandbox interfaces are unchanged.

## Alternatives considered

- Delete all broad catches, capability checks or low-frequency compatibility branches: rejected without proof of the actual underlying contract.
- Replace provider routing or deploy locally registered functions implicitly: deferred; these change public architecture and ownership semantics.
- Treat full-suite environmental failures as passing: rejected; preserve baseline comparisons and keep this proposal pending gates.

## Dependencies

No new runtime dependencies. CLI and SDK share command semantics but remain independently installable. Companion: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/215.

## Test Strategy

Behavior regressions cover shell quoting, background execution and lifecycle errors. Exercise actual built components, real Express instances, independent absence verification, bilingual examples, static checks and full suites. Distinguish failures, skips and targeted successes.

## Acceptance criteria

- Redundant branches are removed without new provider capability requirements.
- Quoted operators stay literal and background shell execution expands variables.
- Unknown lifecycle state is not reported as absence; failed deletion remains retryable.
- Bilingual guides, CHANGELOG and verification evidence match actual behavior.
- Full required CI and repository checks pass before merge.

## Evidence

[Verification](../../../evidence/verify/2026-10-29-defensive-complexity-cleanup.md).
