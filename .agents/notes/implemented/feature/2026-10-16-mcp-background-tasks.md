# Decision: Sandbox-lifetime reconnectable Python MCP background tasks

Status: implemented

## Problem

Synchronous MCP command calls cannot provide a durable background handle. A real
Express probe confirmed native process Start survives stream/client disconnect,
but Connect only delivered subsequent output and an exit event; it did not replay
prior output and another Connect after exit failed. Session shutdown normally
kills session-owned sandboxes. The P0 long-task requirement therefore needs more
than an in-memory stream or a process ID.

## Decision

Add three Python-only shared MCP handlers. A standard-library Linux supervisor
runs inside the authorized existing sandbox, records bounded logs and atomic
status, and owns a new child process group. It observes child completion with
WNOWAIT, kills same-group descendants before reaping the leader, and handles
cancel/deadline with TERM then KILL. A random task ID selects only its own records;
callers cannot signal an arbitrary PID. Task records require no installed runtime
package in the sandbox beyond Python 3, a shell and Linux process APIs.

Explicit background submission retains only that sandbox until its existing
platform TTL on MCP disconnect. Other synchronous resources keep normal cleanup.
Read/cancel connections close without adopting resources or requesting TTL renewal. Commands
sharing a retained sandbox share its retention and OS trust boundary. Results
survive MCP process replacement while the sandbox lives, never sandbox destruction.

## API Design

- `start_task(command, sandbox_id?, cwd?, timeout=300)` requires an existing sandbox
  or session default, returns `sandbox_id`, opaque `task_id`, observed `state`, and
  `retained_until_sandbox_ttl`. Timeout is 1–3600 seconds; encoded requests are
  limited to 96 KiB before remote connection. Ambiguous submission returns the
  actual chosen handle, `unknown` and a static error, never an automatic retry.
- `get_task(sandbox_id, task_id, stdout_offset=0, stderr_offset=0, limit=16384)`
  returns status, exit code, timestamps, bounded log pages, next byte offsets,
  sizes and truncation flags. Limit is at most 65536 bytes per stream. Logs cap at
  1 MiB per stream and are drained after truncation. Maximum 128 task directories
  per sandbox OS user. UTF-8 may split at byte boundaries.
- `cancel_task` takes the same handle/pagination arguments, requests owned-group
  cancellation and waits up to three seconds for a terminal snapshot. Running or
  unknown status does not prove cancellation. Terminal cancellation is idempotent.

No public SDK method signature, platform endpoint, CLI tool registry, provider
capability declaration or package version changes. Existing MCP error transport
semantics apply; failed task exit codes remain observable.

## Alternatives considered

- Native process Connect only: live reconnection works, but observed replay and
  completed-process result retention do not satisfy the requirement.
- Local host database/async collector: adds host persistence and restart recovery
  while still losing native historical output; sandbox files are the smaller slice.
- Hosted durable scheduler, arbitrary PID cancellation or automatic sandbox
  recreation: outside this slice and not inferred from the implemented tools.

## Dependencies

Existing SDK commands and provider connect/close operations; Linux `/proc`,
WNOWAIT, signals, process groups and Python standard library inside the sandbox.
Tasks share the sandbox OS identity and files. The worker masks exact known secret
values from its environment before saving logs; host results receive page-local
masking. Neither is a general DLP guarantee. New sessions need the same authorized
provider/region configuration and saved handle. Independent sessions/groups can
escape a task group; destroy the sandbox for full resource cleanup.

## Test Strategy

Real local subprocess regressions cover normal/nonzero/timeout/cancel leader exit
with TERM-ignoring redirected descendants, bounded busy stdout/stderr, progress
before completion, restart-style manager replacement, pagination, private errors,
expanded Unicode/quote limits, secret values split across reads and both transport
handlers. Run owner CI/checks. Real Express E2E starts work, disconnects, reads saved
exit/logs from fresh managers, cancels another task and destroys the owned sandbox.

## Acceptance criteria

- Handles remain queryable after MCP disconnect/process replacement within sandbox TTL.
- Synchronous shutdown behavior is unchanged and retention IDs clear on kill/shutdown.
- No arbitrary PID or path is accepted; cancel/timeout clean same-group descendants.
- Output/deadlines are bounded and incomplete operations never fabricate success.
- English/Chinese guide, changelog, meaningful tests and real-cloud cleanup evidence.
- Required CI/review/health gates pass before merge; no full P0–P2 completion claim.

## Evidence

- [Verification](../../../evidence/verify/2026-10-16-mcp-background-tasks.md)
- [Issue #44](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/44)
- Stacked on the lifecycle slice, [PR #33](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/33).

- Original roadmap remains open: [Issue #45](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/45).

## Implementation

The scoped task feature passed independent source/process review, actual Express
full-suite and separate-process reconnect acceptance, and all nine GitHub checks
on implementation head `3761d9d3b217d6a6f72a8c5058694d205f8de6c3`. Local baseline
failures and broader product/provider exclusions remain recorded in the evidence.
