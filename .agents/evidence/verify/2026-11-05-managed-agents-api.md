# Verification: Managed Agents API runtime

- Date: 2026-11-05
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/155
- Result: PARTIAL — implementation and local component verification; full repository, cloud/model and release gates remain in progress.
- Package under test: isolated feature-branch source; distribution versions remain 0.4.0a6. This does not describe the public 0.4.0a6 artifacts.
- Environment: CPython 3.12.13 on Linux; isolated PID namespace component runner uses CPython 3.12.16. Real PostgreSQL supplied by pgserver 0.1.4; psycopg 3.3.8. No credential values recorded.

## What was verified

New managed Gateway, durable resources, Worker and private bridge behavior was exercised through
actual loopback HTTP, disk state, real PostgreSQL and real CLI fixture subprocesses. The fixture
implements deterministic Qwen stream events; it is not a real model or cloud acceptance claim.
Legacy public in-sandbox routes are unchanged.

## Commands run

- `python -m pytest client-sdk/tests/test_managed_agents.py -q --disable-warnings --maxfail=1`, inside an isolated PID namespace with source packages and the task virtualenv mounted read-only where appropriate.
- `mypy src/agent_sandbox/server/`, from `server-sdk`.
- `mypy src/agent_sandbox/`, from `client-sdk`.
- `ruff check` and `ruff format` over the new runtime and regression files.

## Results

| Scenario / test | Result | Notes |
| --- | --- | --- |
| Managed component regressions | PASS | 29 tests, 17.76 seconds at the recorded checkpoint; later review changes require rerunning |
| Frozen V1 HTTP inventory | PASS | Every one of 39 operations actually called successfully, plus unauthorized rejection per protected operation, on SQLite and real PostgreSQL |
| Files, two turns, independent artifact bytes, close/delete | PASS | Real bridge HTTP, filesystem and CLI subprocess; one reused resource and independent local absence |
| Exact cancellation and durable target replay | PASS | First cancellation never targets the next turn; queued and creation-time cancellation stop submission |
| Cooperative process stopping | PASS | Leader exits while a detached child continues writing; domain cleanup stops it. Unknown host processes force conservative whole-resource cleanup |
| Observed tool deadline | PASS | Real sleep subprocess, start without done, and completed-tool control |
| Limits and retention | PASS | Small output limit, partial HTTP body deadline, bounded GC/pending attachment protection, uncertain resources and more than 10,000 closed tombstones |
| Lost guest response | PASS | Original durable receipt inspected; exactly one input POST and one filesystem effect |
| Type checking | PASS | Server 58 source files and client 112 source files at the earlier checkpoint; rerun required for latest stream changes |
| Full repository checks | IN PROGRESS | Required before merge |
| Real Express/model deployment | IN PROGRESS | Coordinated separately; no success inferred from fixture tests or source-only installation |
| Public package/template installation | NOT RUN | Public 0.4.0a6 lacks the new modules; a new actual release is required |

## Cleanup

Every local fixture resource is closed in teardown. PostgreSQL handles stop/delete their temporary
clusters. Detached regression children are explicitly killed in `finally`. The isolated runner is
removed after exit. Cloud resources and independent absence belong to the separate cloud evidence;
no cloud cleanup success is inferred from this local report.

## Problems found

Adversarial reviews identified output-limit propagation, cancellation at the final dispatch fence,
heartbeat during preparation, uncertain Session freeze, artifact ancestor traversal, depth scanning,
retention and SSE deletion races. The implementation includes focused regressions; full latest-head
checks and independent stream-gate review remain pending. Early shared-host process-domain tests
correctly refused reuse when unrelated same-UID contributor processes appeared; production behavior
was preserved and coexistence tests moved to an isolated PID namespace.

## Not verified

OpenAI SDK interoperability, arbitrary providers, hostile same-UID integrity, steering, functions,
arbitrary MCP/subagents and dynamic Session settings are outside the supported V1 subset. Full
repository CI, real cloud/model business completion and public release/install are not yet complete.
