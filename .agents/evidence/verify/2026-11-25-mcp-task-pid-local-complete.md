# Verification: Complete local MCP PID fixture follow-up

- Date: 2026-11-25
- Change: [PR #177](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/177),
  [Issue #176](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/176), and
  [decision](../../notes/implemented/process/2026-11-25-mcp-task-pid-publication.md).
- Result: PASS with 29 existing optional client skips for the complete original
  local invocation. Latest-head normal remote CI/review remains a separate gate.
- Final head: `a8cf082e3ab572833f19f22e4f5d1cf84b63237b`.
- Environment: Linux, Python 3.13.13, existing dev tools; isolated user/PID/network
  namespace, private `/proc`, enabled loopback and a child-reaping PID 1. No cloud
  resource, credential, version change or publication.
- Record status: intentionally uncommitted while the final head runs normal CI;
  PR text reports the completed result without resetting the tested head.

## Command and source boundary

The original `make test` invocation ran both package suites, with this worktree's
source paths selected, and returned exit status 0. Its normalized environment was:

```bash
unshare -Urnpf --mount-proc bash -c 'ip link set lo up && exec python reap-init.py env PYTHONPATH="$PWD/client-sdk/src:$PWD/server-sdk/src" make test'
```

The test-environment reaper is task tooling, not a new product entry point.
The necessary startup-assertion review correction was applied while only server
tests were running. The subsequent client process collected the final corrected
test after that edit; server and product source were unchanged. The final target
module also passed separately after the correction, as recorded in the committed
[startup review](2026-11-25-mcp-task-startup-review.md).

## Results

| Check | Result | Actual original summary |
| --- | --- | --- |
| Full server suite | PASS | 895 passed in 320.22 s |
| Full client suite | PASS with optional skips | 2,471 passed, 29 skipped in 166.11 s |
| Complete original command | PASS | Exit status 0 after both suites |
| Four process-cleanup modes | PASS | Success, nonzero, cancel and timeout remain in the original module |

The 29 optional skips are nine PostgreSQL cases without `pgserver`, two opt-in
real-engine cases without `ABX_COMMAND_TEST_BIN`, five sibling CLI fixture checks
and thirteen sibling catalog-engine cases. They remain skips, not passes. No
assertion, marker, deadline or runtime behavior was weakened.

## Cleanup and limits

Existing fixtures and the namespace reaper shut down/reaped owned local processes
and temporary state. Production source/version files remain unchanged. The
original main Python 3.11 failure and exact-tree comparison remain in the
[initial checkpoint](2026-11-25-mcp-task-pid-publication.md); this local result does
not rewrite that failed command or independently prove its exact scheduling/IO
cause. Actual final-head Python 3.11 CI and normal review/merge are still required.
