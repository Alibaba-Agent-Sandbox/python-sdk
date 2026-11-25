# Verification: MCP PID fixture delivery

- Date: 2026-11-25
- Result: PASS for delivered fixture/PR gates; new-main CI remains in progress
  at this checkpoint.
- [PR #177](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/177) was
  independently read back as normally merged at 2026-11-25T06:34:23Z into
  `a8d57e5b3bf2264d9d4f553b8fa071fa177a25db`.
- All 13 checks passed for final head
  `a8cf082e3ab572833f19f22e4f5d1cf84b63237b`, including actual Python 3.11.
- [Issue #176](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/176)
  was independently confirmed closed. This documentation PR uses `Refs` and
  does not request another automatic closure.

The [original complete local invocation](2026-11-25-mcp-task-pid-local-complete.md)
returned exit 0: server 895 passed in 320.22 s; client 2,471 passed and 29 existing
optional cases skipped in 166.11 s. The final client fixture was collected after
the necessary startup-assertion correction; production/server source was unchanged.

The older [main run 45557866579](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/45557866579)
at `9223362` remains failed: one Python 3.11 fixture read an empty PID marker
before reaching product cleanup assertions, with 2,453 passes, 36 skips and 10
deselections. Its tree equalled the earlier passing PR175 head. The bounded probe
established a fixture publication gap, not that occurrence's exact scheduling/IO
cause. The [initial failure](2026-11-25-mcp-task-pid-publication.md) and
[startup review](2026-11-25-mcp-task-startup-review.md) retain their original facts.

The new actual-main [run 45561605441](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/45561605441)
was independently observed `in_progress` at this checkpoint. Its eventual result
belongs to a later observation; no green main run is inferred from passing PR CI.

This follow-up changes only engineering records: it preserves the complete local
result, moves the accepted [decision](../../notes/implemented/process/2026-11-25-mcp-task-pid-publication.md)
to `implemented`, updates earlier ADR link targets only and records the actual
merge. No SDK source/version, public artifact, cloud resource or publication.

Owner checks executed: `bash scripts/check-repo-health.sh`, `make hygiene` and
`git diff --check`. Health reports 106 passes, one existing release-runbook warning
and no failures; hygiene/whitespace pass. Earlier checkpoint bytes are unchanged
except their relocated ADR link target. This documentation-only PR still requires
normal latest-head CI and review before merge.
