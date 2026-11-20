# Verification: managed Harness protocol re-review

- Date: 2026-11-20
- Change: [Python SDK PR 165](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/165), inspected baseline `d336eb89aa2685ead3d173103b7a6e5c964ed829`.
- Result: PARTIAL
- Package under test: editable `agent-sandbox-client` and `agent-sandbox-server` `0.4.0a8` candidate source.
- Environment: Linux x86_64, CPython 3.11.15 and 3.13.13, OpenAI Python SDK 3.52.0, local embedded PostgreSQL 17 with a locally issued TLS certificate.

## What was verified

Round one compared the managed capability response to native Codex JSONL parsing and followed
the three previously permissive adapters through real subprocess exit to the managed receipt.
Codex, Claude Code and Qwen Code all reported completion for a zero-exit transcript containing
an intermediate message and no terminal record. Three complete-transcript controls passed.
The capability test independently exposed the false `native_partial` claim for Codex.

The correction requires an explicit successful terminal result for the managed bridge and
reports Codex's actual complete-message granularity. Standalone agents retain their existing
default for exit-based adapters. Terminal failures, process failure, timeout, cancellation
and stop confirmation still take precedence. Native parser and business tests retain their
existing expectations.

The shared protocol supports configured saved Agents, text Sessions and initial input, ordinary
continuations, SSE, turns, items, file/artifact operations, cancellation and deletion. OpenAI's
Session create and delete use the same public paths with 201 and 200 respectively. The managed
Gateway uses a stable endpoint while the selected Harness itself runs inside each Sandbox.
OpenAI hosts its Harness in both hosted and self-hosted environment modes. The managed Gateway
returns 409 for a busy ordinary input and exposes an explicit enqueue operation. OpenAI's active
input may steer a running turn. OpenAI's Session update supports agent changes and its service
supports function callbacks, remote MCP and subagents. The managed contract accepts metadata-only
updates, private file staging through extensions, and explicit compute Close. Validation of the
selected official Turn models and SSE client path is evidence for those shapes only.
[OpenAI architecture](https://developers.openai.com/api/docs/guides/agents-api/architecture),
[Sessions](https://developers.openai.com/api/docs/guides/agents-api/sessions),
[Session configuration](https://developers.openai.com/api/docs/guides/agents-api/configuration),
[Create](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/methods/create),
[Delete](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/methods/delete).

## Commands run

- Server: `pytest -q tests/test_server/test_harness_adapters.py`.
- Client: `pytest -q tests/test_managed_wire.py tests/test_managed_harness.py`.
- Client: `pytest -q tests/test_managed_agents.py::test_real_bridge_two_turns_files_artifacts_close_and_delete`.
- Client: `pytest -q tests/test_managed_wire.py 'tests/test_managed_agents.py::test_all_39_http_operations_against_frozen_inventory[sqlite]'` with a fresh user/PID/network namespace, loopback enabled, and the pinned OpenAI SDK installed.
- PostgreSQL variant: use the existing two-turn and frozen inventory test bodies with a temporary copy of the fixture, changing the database URL to the owned local PostgreSQL TLS server, passing its trusted CA and giving each run a new application identity. A `socat` Unix-stream relay forwards the unchanged TCP/TLS bytes between the isolated and host namespaces. `pg_stat_ssl` confirms TLS at the actual database.
- `make lint format-check typecheck`, `make build dist-check`, `bash scripts/check-repo-health.sh --quiet`, `make hygiene` and `git diff --check`.

## Results

| Scope | Result | Scope of proof |
| --- | --- | --- |
| Failure controls before product fix | 3 truncated fixture failures, 3 complete controls passed, 1 inaccurate capability assertion failed | All three truncated cases were wrongly marked complete by the original source |
| Server Harness adapter suite after product fix | 27 passed | Native event mappings and actual local fixture subprocesses, no vendor account |
| SQLite two-turn workflow | 1 passed in a dedicated PID namespace with original assertions | Two turns, retained files, Close and Delete |
| SQLite HTTP inventory and OpenAI SDK | 7 passed in dedicated PID/network namespaces | All 39 managed HTTP operations and supported typed Turn/SSE shapes |
| TLS PostgreSQL end to end through the local Gateway and private bridge | 2 passed in dedicated PID/network namespaces | The two-turn and all-39 operation test bodies passed with real TLS storage, a real local HTTP connection and a fixture Harness |
| Both packages' lint, formatting and type checks | Passed | Local Python toolchain |
| Local candidate builds and distribution checks | Passed | Both wheels/sdists passed Twine, `py.typed` checks, and client-only and paired installation tests |
| Repository health and hygiene | Passed | 106 health checks passed, one existing release-runbook recommendation and zero failures |

## Cleanup

The test harness subprocesses, HTTP services and forwarder were owned by the run. The
temporary PostgreSQL server was stopped with `pg_ctl -m fast -w stop`. Independent `pg_ctl
status` returned exit 3, and the relay socket and `postmaster.pid` were absent. No cloud
resource, vendor account or cloud credential was used or created.

## Problems found

A shared-host run failed the second turn in both SQLite and PostgreSQL variants. A read-only
process scan observed unrelated same-UID Git processes after the turn began. The existing
process-domain policy refused reuse, and the Worker destroyed its owned Sandbox before
publishing the first turn. A repeat in a dedicated PID namespace observed no unrelated new
processes and reused the same Sandbox. The process policy was preserved.

Repository health initially identified unresolved evidence paths in the earlier candidate.
The two cross-repository evidence references now point to the owning repository and the
dated SDK review directory has its own linked index.

Authenticated HTTP cases on the shared loopback network also disconnected on the first
request. The shared-namespace run of the four managed test modules reported 91 passing and
23 failing cases. The isolated loopback test runs above preserve the original HTTP assertions
and show the local response and stream behavior. The failing shared-host run remains evidence
of its environment.

## Not verified

FC hosting, release/image publication, real six-Harness authenticated model/tool runs,
old-Session routing across a cloud revision update, and independently verified cloud cleanup
remain separate release requirements. Local PostgreSQL TLS and fixture work do not qualify
those gates. The SDK's older standalone template YAML consumer is tracked separately from
these managed-protocol corrections.
