# Decision: Retryable MCP cleanup and accurate harness preparation

Status: proposed

## Problem

[Issue181](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/181) records a real ownership bug: manager shutdown cleared handles before cleanup, suppressed errors, and HTTP DELETE discarded the session first. Explicit kill and create-resource rollback also discarded failed handles. A backend failure could therefore be reported as successful termination with no retry path.

[Issue182](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/182) records a separate false recovery instruction: the Agents runtime suggested a module installation command which does not exist.

## Decision

Stop resource admission when shutdown starts; track admitted create/connect/kill operations until their returned handles are registered. Register acquired handles without an intervening await. Serialize cleanup, continue after individual failures, and forget only the exact successfully cleaned handle. Preserve owned, borrowed and retained-task distinctions; failed duplicate borrowed closes retain their own handle.

HTTP DELETE shares a shielded cleanup task. Failure returns a sanitized 503 and keeps the closing session counted against capacity. POST on the closing session returns409. Explicit DELETE retries immediately; idle cleanup retries at most once per existing TTL. Shutdown-all attempts every session. No new background scheduler, persistence layer or API endpoint is introduced.

Missing harness guidance directs authors to prepare a pinned upstream CLI in the image and verify its PATH/version as the server user before deploying. No runtime download or new installer is added.

Round2 found that the actual SDK Sandbox.kill closed its provider in a finally block even when deletion failed. It now leaves that connection usable on failure, records remote acknowledgment independently from completed local cleanup, and does not repeat an acknowledged delete merely to retry a failed close.

[Issue183](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/183) adds the missing explicit MCP-Protocol-Version guard. Origin and auth run first; an unsupported or empty supplied version returns400 before session expiry, dispatch or DELETE. Exact2025-06-18 and absent-header existing behavior remain supported; health is unchanged.

## API Design

Successful requests retain their current shapes. Incomplete DELETE returns HTTP503; closing-session POST returns409. Python manager shutdown raises a sanitized MCPCleanupError when handles remain. Existing kill acknowledgments are accepted by manager cleanup; the separate resource-verification rollback retains its independent absence check and recovery ID.

## Alternatives considered

- Clear ownership and log failures: rejected because successful termination would lose recovery.
- Hold the state lock across provider I/O: rejected because shutdown and late acquisitions could deadlock.
- Shield provider creation itself: rejected because it would alter cancellation semantics. Only returned handle registration is synchronous; HTTP cleanup sharing is shielded.
- Persist all MCP sessions or wait for every running tool: outside this focused correction. Recovery lives in the running MCP process; platform TTL still bounds owned resource lifetime after process loss.
- Add a public harness installer: unnecessary for correcting an invalid hint; existing templates already use pinned image installation.

## Dependencies

Existing Sandbox provider handles, Starlette/uvicorn optional MCP transport, and Agents runtime. Companion CLI correction: [Issue278](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/278). This change does not alter OpenSandbox or Express provider mappings.

## Test Strategy

Failure injection at provider-handle cleanup, late acquisition, canceled/concurrent DELETE, retry capacity, bounded expiry retry and exact-handle rollback. Exercise the real HTTP server over a local Unix socket; exercise actual missing-binary process launch through Agents routes. Full SDK checks and focused real-provider acceptance are recorded separately.

## Acceptance criteria

Failed ownership remains retryable; successful sibling cleanup proceeds; borrowed resources are never implicitly killed; late returned handles cannot disappear; HTTP failure is observable and retryable; no raw provider exception or secret is returned; missing-binary guidance names an actual supported preparation path.

## Evidence

- [Verification](../../../evidence/verify/2026-11-25-mcp-cleanup-retry.md)
