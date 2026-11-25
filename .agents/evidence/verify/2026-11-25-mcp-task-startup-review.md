# Verification: Preserve the MCP fixture's startup assertion

- Date: 2026-11-25
- Change: [PR #177](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/177)
  and [decision](../../notes/proposed/process/2026-11-25-mcp-task-pid-publication.md).
- Result: PASS for this necessary diagnostic correction and targeted checks;
  full local invocation and latest-head normal CI/review remain pending.
- Environment: Linux, Python 3.13.13, existing dev tools. No cloud/credentials.

## Review and correction

Review of initial head `0a66060e0d491d947f4f5ca91fd3d862878d9112` found that
extracting the handle before checking `started['error']` could replace the
original useful assertion with `KeyError` on a rejected start. Restore the
original startup assertion before extracting the handle. No invalid-receipt
branch is introduced. Marker waiting/parsing and later checks retain `finally`
coverage after a valid owned handle is available.

Atomic PID publication, the five-second wait, four modes and all product-state,
descendant-absence and repeated-cancel assertions remain unchanged from the
initial fix. The original
[failure/fixture checkpoint](2026-11-25-mcp-task-pid-publication.md) remains
historical; this record describes the final diagnostic correction.

## Verification

The entire MCP task module passed again: **30 passed in 6.51 seconds** under the
same isolated process/network observation and reaping PID 1. A separate bounded
probe supplied a controlled startup error to the actual updated test function:
the original AssertionError retained the full error dictionary, no KeyError
occurred, and no cancellation targeted a handle that had not been established.

```bash
python -m pytest tests/test_agent/test_mcp_tasks.py -q
ruff check client-sdk/tests/test_agent/test_mcp_tasks.py
ruff format --check client-sdk/tests/test_agent/test_mcp_tasks.py
bash scripts/check-repo-health.sh
make hygiene
git diff --check
```

Targeted tests, lint, formatting, health, hygiene and whitespace checks pass.
The existing release-runbook warning remains. The original complete local run
was still in its server half when this client-test correction was applied; its
client process had not yet collected the changed test. Its final result will be
reported separately, without rewriting these checkpoint results or resetting CI
only for a result update. Normal latest-head CI including actual Python 3.11 is
still required before merge. Production source, versions and public artifacts
are unchanged.
