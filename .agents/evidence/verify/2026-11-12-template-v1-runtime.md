# Verification: canonical template v1 runtime consumers

- Date: 2026-11-12
- Change: `feat/template-v1-runtime-20261112`, stacked on SDK API-contract commit
  `ef61cfebf009ba5ea6783a0a94735cc26e4d0b9b` / [PR163](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/163).
- Result: PARTIAL — targeted local checks pass; final full-suite/CI and real-cloud gates pending.
- Package: matching source client/server0.4.0a7, Python3.11.15 on Linux; no release performed.
- Producer: [e925051](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/commit/e9250512967d4c4abb59672567d68ba3e7d18473),
  [PR310](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/pull/310).
- Tracker: [templates309](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309).

## What was verified

SDK-owned prepared launch/discovery consume v1, and Managed Sessions retain safe instance
snapshots while the Worker alone supplies custom env values. Wire tests use the actual
Express serializer and HTTP client with an HTTP mock; these are component regressions,
not live cloud. SQLite and temporary PostgreSQL are actual local database processes/files.
The tests retain existing startup/readiness and owned-cleanup assertions.

## Commands run

| Check | Result | Scope |
| --- | --- | --- |
| Selected launch/discovery/model/contract tests | PASS101 | Migrated old fixtures, canonical v1 admission |
| Additional registry/discovery/integration tests | PASS81 | Source loading and existing local SDK/server bridge |
| v1 runtime regressions + original Managed tests, first run | FAIL1 / PASS95 | Existing active-cancel test observed resource disposal where it expected reuse |
| That active-cancel test plus new runtime regressions, isolated retry | PASS27 | Does not erase the earlier timing observation |
| Final focused tests, including canonical fixtures and integration | PASS196 | Before full-suite capture; see subsequent gate results below |
| Prefreeze targeted v1/runtime/discovery/catalog/provider-boundary set | PASS230 | Canonical producer e925051; actual schema, plugin callback, HTTP serializer, SQLite/PostgreSQL |
| First `make test` | FAIL8 / Client2566pass26skip; Server875pass1skip | Eight old fixture catalog requirements for retired publication fields/specification5, corrected in fixture tests |
| Corrected fixture/runtime subset | PASS127 | No production schema relaxation; publication keys rejected in resource documents |
| `make lint typecheck format-check hygiene` | PASS | Both distributions, strict typing, formatting and source hygiene |
| `bash scripts/check-repo-health.sh` | PASS106 / WARN1 / FAIL0 | Existing recommended English release-guide warning |
| Final `make test` / `make ci` | PENDING | Frozen product head will be tested; separate evidence update follows |

Intermediate schema-fixture runs exposed missing test Provider contexts and descriptor
callbacks. Those harness errors were corrected by supplying the actual fixture context and
real JSON Schema descriptor, without weakening production validators. First migration run
also contained three stale test expectations (a dropped invalid fixture and illegal
sandbox+deployment combination under the then-current producer schema); they were corrected.

## Cancel timing observation

The failing existing assertion was in
`test_active_cancel_exact_target_replays_without_cancelling_next_turn`: cancellation was
confirmed, one native instance had been created, but the local backend no longer retained
it. Neither `managed_agents/worker.py`, guest managed bridge code nor the cancel test was
changed. The existing Worker deliberately disposes owned compute when a terminal guest
receipt does not confirm stopping, then records confirmed cleanup. That is a possible
explanation, not an established root cause: the first run did not capture that private
receipt. The isolated retry passed. Full-suite outcomes below retain their independent
meaning; no assertion or timeout was weakened to obtain a pass.

## Source freeze

The parent requested an actual complete consumer commit so Templates/CLI/Registry can pin
the SDK-owned generic launch contract. This freeze does not imply merge, release, completed
full CI or cloud acceptance. The source includes the runtime migration, contract/vectors,
bilingual guidance and engineering records together; later validation gets a separate
evidence commit. Final source-lock verification compared actual producer Git object bytes.
The optional Provider callback uses real synchronous schemas; the default unavailable
method and asynchronous returns do not qualify as implementations.

## Cleanup

No cloud Sandbox, FC, database service, image, model operation or other cloud resource was
created. Temporary PostgreSQL instances call their actual fixture cleanup and use isolated
local directories. HTTP mock cleanup checks that only owned Sandbox DELETE occurs; no
Volume lifecycle call occurs. This does not establish live-account Volume behavior.

## Not verified

Real cloud/model/FC integration, remote Python matrix, package publication, merged delivery
and official OpenAI SDK interoperability are not established by these local checks. Required
cloud acceptance remains pending; the record and ADR stay proposed/PARTIAL.
