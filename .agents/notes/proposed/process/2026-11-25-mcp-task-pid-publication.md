# Decision: Publish MCP regression PIDs atomically and clean up failed setup

Status: proposed

## Problem

Main's post-merge Python 3.11 client run failed because a regression test read an
empty PID marker after checking only file existence. Its marker producer exposes
a created file before its contents are complete, and the consumer reads/parses
outside `finally`. This is a synchronization gap in the test fixture; the CI
trace did not reach a production process-state or descendant-cleanup assertion.
The exact writer/scheduling cause of that occurrence is not established.

## Decision

In the test child, write the PID to a same-directory temporary file, close it and
publish with `os.replace`. Keep the original five-second wait and all four modes.
Preserve startup validation before handle extraction. Put marker waiting and
parsing inside owned cleanup handling once the handle is available.
On setup/assertion failure, cancel the known task handle before fallback cleanup;
only a parsed child PID greater than one is eligible for the existing kill.

Retain all terminal-state, descendant-absence and repeated-cancel assertions.
Do not ignore empty reads, retry until green, change product code, update a
package version, create cloud resources or publish packages.

## API Design

N/A — this decision does not change a production API. It changes only the local
PID handoff and failure cleanup of an existing regression fixture. User guides
are unchanged; the test changelog entry is bilingual.

## Alternatives considered

- Retry empty PID reads: rejected because existence would remain an invalid
  completion signal and a writer failure could be obscured.
- Increase deadlines or weaken state/cleanup assertions: rejected because neither
  addresses incomplete marker publication.
- Change the production task supervisor: unsupported by the observed trace.

## Dependencies

Existing pytest/asyncio tests, standard-library filesystem/subprocess support and
the existing local sandbox transport substitute. No new dependency or runtime.
Track [Issue #176](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/176)
separately from the already delivered public release.

## Test Strategy

First use a bounded two-process handshake to make the old empty-created-file
window observable, and compare atomic publication. This demonstrates the fixture
protocol gap without claiming it proves CI's exact scheduling. Run all existing
MCP task tests and owner static/record checks before opening the Draft PR; run
the complete normal remote matrix including Python 3.11 and the complete local
suite separately. Preserve initial failures, optional skips and original results.

## Acceptance criteria

- Complete PID contents are published together, with the original wait deadline.
- All four existing modes and original product assertions pass unchanged.
- Setup/assertion failures attempt known-handle cancellation and verified-PID
  fallback cleanup without signaling an unvalidated PID.
- Production source, versions and public artifacts remain unchanged.
- Owner records/checks and the actual latest-head CI/review pass before merge.

## Evidence

- [Post-merge failure and fixture verification](../../../evidence/verify/2026-11-25-mcp-task-pid-publication.md).
- [Startup diagnostic review](../../../evidence/verify/2026-11-25-mcp-task-startup-review.md).
