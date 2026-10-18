# Decision: Keep local HTTP and PTY test listeners on distinct ports
Status: implemented

## Problem

A released ephemeral port can be selected again. The client component fixture
chooses HTTP and PTY separately, so identical candidates cause EADDRINUSE and
misroute a WebSocket handshake to the HTTP listener. Python3.11 CI exposed this.
https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/63

## Decision

Select a different candidate before creating listeners, with32 bounded attempts.
Preserve explicit PTY selection by moving the HTTP candidate when necessary.
Add deterministic default/explicit reuse regressions with actual server listeners
and normal cleanup. No production request retry or transport behavior change.

## API Design

Only the private test fixture changes. Existing product APIs are unchanged.

## Alternatives considered

- Rerun the failed job only: leaves the reproducible fixture race.
- Retry WebSocket requests: masks the wrong listener and does not fix allocation.
- Override an explicit PTY port: violates caller fixture configuration.

## Dependencies

This independently unblocks configuration refactor
https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/61.
No consumer repository or runtime dependency changes.

## Test Strategy

Force the candidate allocator to return the same released port. Both regression
cases fail before the fix, then actual HTTP/PTY listeners and policy cases pass.
Run full client/quality/hosted matrix and required real-cloud acceptance; preserve
initial failures and independently verify cleanup.

## Acceptance criteria

- Default and explicit PTY cases retain distinct live endpoints.
- No HTTP/PTY bind collision in the deterministic regression.
- Existing client/policy behavior and required CI/real cloud remain green.
- English/Chinese testing docs, changelog and owner evidence are complete.
