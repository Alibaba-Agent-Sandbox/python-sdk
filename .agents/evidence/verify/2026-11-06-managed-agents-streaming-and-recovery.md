# Verification: Managed streaming and process recovery

- Date: 2026-11-06
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/156; continuation of `5061fd3b6ad5b3fea6f641daf49f62efd55acc22`.
- Result: PARTIAL — the recorded local regressions and real process faults passed; latest CI artifacts and FC/model delivery remain separate gates.
- Package under test: matching client/server 0.4.0a7 candidate, not published by this verifier.
- Environment: CPython 3.12.13, real local PostgreSQL 16.2, SQLite, actual private HTTP, owned PID namespaces and deterministic CLI subprocesses. No credential values recorded.

## What was verified

The [FC streaming reference](https://help.aliyun.com/zh/functioncompute/does-function-compute-support-sse-streaming-response)
identifies chunked response encoding as the Web function's streaming signal. The former Gateway
wrote bare SSE bytes with connection-close framing. Independent review accepted real HTTP/1.1
chunk framing for every event and heartbeat, a normal zero terminator, and connection closure
without another HTTP status when an exception occurs after streaming headers. Existing PostgreSQL
subscription records and the cross-process event/deletion gates are unchanged.

Separately, actual FC argument validation rejected the earlier single CA argument with a maximum
length of 2048. The runtime option now accepts one or more Base64 segments, bounds their total
encoded length before joining, and validates canonical ASCII Base64 once. Certificate validation,
the 64 KiB decoded bound, environment-source conflict and temporary-file cleanup are unchanged.
The consumer splits arguments to satisfy the observed per-argument limit; the runtime bound does
not promise that FC accepts every possible total argument size.

## Commands run

- Client Ruff/format and `mypy src/agent_sandbox/`.
- `pytest tests/test_managed_entrypoint.py tests/test_managed_agents.py tests/test_providers/test_managed_import_boundary.py -q` in an owned PID namespace.
- Task-only `pytest_generate_tests` plugin: add real PostgreSQL only to otherwise unparameterized `components` cases; retain every product assertion and existing explicit SQLite/PostgreSQL parameterization.
- Actual local PostgreSQL stop/restart against a warm HTTP Gateway, without a Worker/model.
- Independent observer SIGKILL and bridge SIGKILL/restart probes using persistent PostgreSQL and the actual private bridge/CLI parser.

## Results

| Scenario | Result | Evidence boundary |
| --- | --- | --- |
| Combined managed/argument/import regressions | PASS | 66 cases, zero skipped, 27.68s. Includes single/multiple CA segments, combined-size and padding rejection, real raw-socket streaming and existing HTTP decoder behavior. |
| Live chunk framing | PASS | Raw HTTP/1.1 headers have chunked encoding without Content-Length; Unicode uses byte lengths, heartbeat chunks decode, and normal revocation ends with a zero chunk. The actual CLI Turn is still in progress when bytes arrive. |
| Midstream exception | PASS | Real socket receives no second HTTP response or false normal terminator; its durable subscription is removed. |
| Real PostgreSQL expansion | PASS | Before this streaming change: 40 cases, 24 real PostgreSQL, 3 explicit SQLite, 13 without components, zero skipped, 40.46s. Includes 19 original default-SQLite scenarios newly executed on PostgreSQL. Provider/model remain fixtures. |
| Database unavailable before admission | PASS | Stopping only the owned PG yields four 503 results: readiness, existing Session read, old-key replay and fresh-key creation. Restarting the same database restores the warm Gateway's original Session/state identity; object and idempotency counts do not increase. Cleanup confirmed. |
| Observer process killed | PASS | Actual SIGKILL after the CLI side effect and persisted acceptance; a new process waits for the real two-second lease and observes the original receipt. Public Turn completes; CLI counter, real submission POST count and backend create count all remain one. 12.175s. |
| Guest bridge process restarted | PASS | Actual bridge SIGKILL followed by the same journal/workspace/port and a new epoch. Native gap and uncertain host outcome are visible; queued successor remains frozen. Original CLI is allowed to continue until after the assertions. Counter/POST/create counts remain one. 12.07s. |
| Initial fault-probe topology | FAIL, harness | The first two attempts placed replacement host observers inside the guest PID view, correctly causing conservative stop uncertainty. No duplicate execution occurred. The corrected fixture gives the guest its own PID namespace and fixed supervisor, matching the intended topology; assertions were not relaxed. |
| Latest complete CI and exact artifacts | PENDING | Previous CI wheels do not contain this additional transport/argument continuation. |
| Real FC live streaming/model workflow | PENDING | Source/official-contract evidence and local sockets are not claimed as cloud reproduction or complete FC qualification. |

## Cleanup

Fault probes own all bridge/observer subprocesses and their guest namespace. The parent tracks
PID creation identity, kills/reaps only its own tree after assertions, and removes its exact PG
data. The database stop/restart probe verifies HTTP thread termination and PG-data removal.
No cloud resource, management Key or real model request is created by these extra component probes.
Failed and corrected attempts are retained separately without credentials or cloud resource IDs.

## Problems found

The former close-framed SSE response did not supply FC's documented streaming signal, and a
single public CA argument exceeded the observed platform limit. Both narrow corrections were
independently reviewed before implementation. The guest process observer correctly rejects
unknown same-UID processes, which requires an appropriately isolated test topology.

Final source review also identified that the previous late-event exception handler classified
every `ManagedError` as a normal slice ending. Only authentication/resource removal now ends
normally; a service-unavailable error propagates and truncates the stream. Subscription cleanup
must succeed before the normal terminator is written. The raw-socket failure regression also
exercises an explicit 503 `ManagedError`, without treating it as a successful end.

## Not verified

Local PostgreSQL connection refusal is not a cloud RDS outage or an in-flight transaction failure.
The deterministic CLI is not a real model or cloud Provider failure. No hostile same-UID process
attestation is claimed. Final FC/model/public-package acceptance and its independent cleanup are
coordinated separately; no publication or merge is inferred from these local results.
