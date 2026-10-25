# Decision: Enforce the documented command execution deadline
Status: proposed

## Problem

The public 0.4.0a1 provider client only converted HTTP read inactivity to a typed
timeout. A process printing every 0.3 seconds ran 6.46 seconds and exited normally
with `timeout=1`. Browser installation also exceeded its requested command limit.

## Decision

Apply one monotonic execution deadline while consuming the existing envd stream.
Wait for each frame only for the remaining time. On expiry, keep the existing
best-effort SIGKILL of the known owned PID and raise `CommandTimeoutError`. Close
the stream on completion or error. Transport close failures do not mask the
original typed error. HTTP read timeout remains a separate transport limit.

## API Design

No new public option, timeout type, retry or compatibility alias. Existing positive
`timeout` values now bound total execution, regardless of stdout/stderr activity.
Owned-process cleanup can add up to its existing request limit before return.

## Alternatives considered

- Increase installation timeouts only: rejected because continuous output still
  defeats the documented execution limit.
- Add another timeout parameter or worker/watchdog subsystem: rejected; the stream
  consumer can enforce the existing deadline directly.

## Dependencies

Python 3.10+ asyncio wait_for and monotonic time; the existing owned PID signal RPC.
No provider control-plane or standard E2B API changes.

## Test Strategy

Bounded continuing-output and silent-stream regressions check typed errors, stream
closure and the exact owned PID signal. Existing short-success and HTTP error tests
remain. The real-cloud regression confirms a one-second limit, process absence and
subsequent usable execution. Full owner CI and cloud gates precede publication.

## Acceptance criteria

- Continuous output cannot extend the execution deadline.
- Only the owned known process is signaled; failure to signal preserves typed timeout.
- Existing command success/error behavior and required tests pass.
- Fresh public patch installation reproduces the corrected behavior.

## Evidence

- [Execution deadline verification](../../../evidence/verify/2026-10-25-command-execution-deadline.md)
- [Issue 113](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/113)
