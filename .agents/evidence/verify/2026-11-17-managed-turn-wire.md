# Verification: Managed Turn wire projection

- Date: 2026-11-17
- Change: [proposed decision](../../notes/proposed/feature/2026-11-17-managed-turn-wire.md)
- Result: PARTIAL
- Package under test: initial editable client/server 0.4.0a7 development source;
  final capability regression uses the coordinated 0.4.0a8 candidate source. Neither
  source run is a published package validation.
- Environment: Linux, CPython 3.12.13; OpenAI 3.52.0; SQLite and local PostgreSQL.
  No cloud credentials or model credentials were used by this verification.

## What was verified

Managed Turn identities, timestamps and lifecycle event payloads now agree across
retrieval, list and durable events. Inline snapshots keep a Session-scoped identity;
saved Agent update/deletion cannot change a frozen Session. Unknown historical start
times remain null and public projection does not rewrite precise private state.

## Commands run

Commands ran from this repository using its dedicated environment:

- `pytest client-sdk/tests/test_managed_wire.py -q`: before fix, four failures;
  after fix and the added real-HTTP exercise, four passes (1.69 seconds). The final
  five-test run including configured-Harness capability timing passed (1.38 seconds).
- `pytest client-sdk/tests/test_managed_agents.py client-sdk/tests/test_managed_entrypoint.py client-sdk/tests/test_managed_wire.py -q`:
  91 passed, eight failed (54.45 seconds). The failures are listed below, not omitted.
- A focused `pytest client-sdk/tests/test_managed_agents.py -q -x --tb=short` independently
  reproduced the first raw-socket oversized-header timeout (32 passed, one failed).
- Final `ruff check` on the three changed Python files passed; `ruff format` applied
  only to those files. Targeted `mypy` checked both changed source files successfully.
- `bash scripts/check-repo-health.sh`: 106 pass, one existing recommended release-runbook
  warning, zero failures. `make hygiene` and `git diff --check` passed.

## Results

| Scenario | Result | Evidence scope |
| --- | --- | --- |
| Missing Turn identity and incomplete in-progress event reproduced | PASS | Four new regressions fail on original implementation |
| Fixed projection, saved-definition mutation, retained old records | PASS | New regression suite |
| Official OpenAI Turn and in-progress/completed event typed parsing | PASS | Local installed OpenAI 3.52.0, no OpenAI network calls |
| Official SDK Turn retrieval and durable SSE terminal consumption | PASS | Actual local authenticated HTTP listener and SDK client |
| Existing managed regressions | PARTIAL | 91 pass; eight raw-socket failures |
| New six-Harness and real cloud publication/upgrade/model acceptance | Not run here | Coordinated delivery gate remains open |

## Problems found

The existing raw-socket tests failed independently of the changed projection:

- Four private-invocation oversized-body header-only probes timed out waiting for 413
  (Dispatcher/Worker, SQLite/PostgreSQL).
- The partial-body/read-timeout probe timed out waiting for connection closure.
- The raw-socket SSE chunk probe and two post-header-failure probes received HTTP 501.

Ordinary local HTTP/SDK requests and real local database scenarios passed. This run
was followed by a [project-independent stdlib control](2026-11-17-raw-http-environment.md),
which reproduced raw GET501 and header-only POST timeout while http.client and urllib
returned200/ok against the same server. This establishes an environment distinction,
without identifying its interception implementation. All eight failures remain FAIL. No assertion was weakened and no product HTTP code was changed
to mask them. Two preliminary commands used an incorrect extra/path; corrected
commands installed `managed-agents` and ran against the intended source paths.

## Cleanup

Temporary databases and listeners were owned by the tests and closed by their cleanup
blocks. No cloud resource, model job or OpenAI-hosted Session was created.

## Not verified

The new recipe's PostgreSQL-backed FC publication, retained Session upgrade, actual
Harness/model behavior and cloud deletion remain separate mandatory delivery gates.
Passing these local resource/event projections does not establish arbitrary OpenAI
SDK compatibility, hosted OpenAI Harness behavior or complete Agents API feature parity.

Commit-time secret hook initially rejected a synthetic loopback test token assignment. The fixture was explicitly named with the documented placeholder marker; no real credential was present. The hook remains enabled and the wire regression was rerun.
