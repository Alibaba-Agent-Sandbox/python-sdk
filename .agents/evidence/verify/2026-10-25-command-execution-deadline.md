# Verification: command execution deadline

- Date: 2026-10-25
- Change: [Issue 113](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/113)
- Result: PARTIAL; full candidate CI/cloud and public-release reruns pending.
- Baseline: fresh public PyPI client/server 0.4.0a1, real Express base sandbox.
- Candidate: paired 0.4.0a2 source, same documented command API.

## What was verified

The same real command prints and flushes every 0.3 seconds for twenty iterations.
With timeout=1 the public baseline returned exit 0 after 6.46 seconds, with twenty
ticks and no error. The candidate raised CommandTimeoutError after 1.34 seconds.
Each probe used an owned sandbox and cleaned it up through its context manager.
The new cloud test also checks the exact PID's absence and subsequent execution.

## Commands run

```bash
pytest client-sdk/tests/test_known_issues/test_ki003_command_timeout.py client-sdk/tests/test_protocol/test_process.py -q
make lint typecheck
make e2e
```

## Results

- Focused protocol/deadline tests: 24 passed, 2.24 seconds before bounded test-stream refinement.
- Candidate static lint and type checks: PASS.
- Real continuous-output candidate probe: typed timeout at 1.34 seconds.
- Full cloud suite with the new PID-absence test: PASS, 127 passed / 9 skipped /
  2 deselected, 221.22 seconds; janitor dry-run 0 candidate resources.
- Full unit CI and fresh published 0.4.0a2 verification: IN PROGRESS.

## Cleanup

Probes created only their own sandbox. The maintained cloud suite tracks owned
resources, checks process absence and runs its janitor dry-run. No resource IDs,
credentials or raw private endpoints are included here.

## Not verified

Public 0.4.0a2 acceptance remains pending. Mock transport tests alone do not prove
cloud process termination.
