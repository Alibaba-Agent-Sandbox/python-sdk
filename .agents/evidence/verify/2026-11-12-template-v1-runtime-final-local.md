# Verification: final local v1 runtime consumer gates

- Date: 2026-11-12
- Product source: `1079841307f1f63253ae68fdda6e6d2d1e77e851`, extending
  `ab50ad8e750b15221c25ccf231caffdc3f196983`, stacked on
  [API PR163](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/163).
- Full-suite producer source: [5cf4482](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/commit/5cf448296361b3bcd8341bd8ae8131f2ca703496).
- Final contract source: [fad843f](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/commit/fad843f60881b405cb386537337817e5144892bc).
- Result: PARTIAL — reported local checks pass within their exact source scopes;
  actual final-head remote CI and required cloud acceptance remain pending.
- Packages/environment: matching source client/server0.4.0a7, Python3.11.15, Linux.
  Actual `jsonschema`4.26.0, hatchling1.33.0, psycopg3.3.2 and pgserver0.1.4 were installed.
  No package release was created.
- Tracker: [templates309](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309).

## What was verified

Canonical v1 literals and resolved snapshots reach prepared creation with schema-validated
instance overrides. Actual Express request serialization forwards specs, TTL, env, metadata
and borrowed Volume names. Managed Session snapshots use one TTL source and contain safe
instance values plus environment names; Worker private config supplies custom values without
copying them into settings, plans or ownership receipts. Custom synchronous Provider schemas
are actually invoked, while absent/default/async validators fail before side effects.
Additional ports resolve actual Provider descriptors and gateway headers without inventing
service clients, readiness or native TCP access. Failure retains owned cleanup behavior.

## Isolation and preserved failure evidence

The earlier nonisolated full-suite runs remain failures. An unchanged baseline and the
candidate both reject compute reuse when an unrelated, same-UID unscoped process appears
inside the observed process domain. Both pass when that controlled process is absent.
The controlled child processes were terminated and waited for. This demonstrates a local
shared-host interference condition but does not retrospectively prove the original full
failure's cause, because its scan counters were not captured.

For final full runs, `unshare -Upf --map-current-user --mount-proc` provided a real private
PID/proc namespace while keeping the current non-root UID, allowing actual PostgreSQL.
No process scanner, native receipt, assertion, grace period or cancellation state machine
was patched for the accepted full runs. This environment correction affects only the
validation subprocess and leaves the shared host namespace unchanged.

Correction to earlier summaries in this workstream: both captured v1 failed full runs had
**Server880 passed, zero skips**, not875 passed/1 skip. The older count was copied from an
earlier environment before packaging prerequisites were present. Actual captured Client
outcomes remain2566 passed/26 skipped/8 stale fixture failures, then2586 passed/20 skipped/
1 active-cancel reuse failure. Those histories are retained rather than rewritten as passes.

## Commands and results

| Command | Result | Scope |
| --- | --- | --- |
| Prefreeze focused v1/discovery/catalog/provider-boundary regressions | PASS230 | Canonical source e925051 before ports increment |
| Ports plus existing launch/Sandbox checks | PASS189 | Canonical source5cf448; actual HTTP serializer and endpoint audience |
| Namespace active-cancel + SQLite/PostgreSQL snapshot probe | PASS3 | Actual local components, no cloud |
| `unshare -Upf --map-current-user --mount-proc make test` | PASS | Server880 passed; Client2596 passed,20 skipped |
| `make lint typecheck format-check hygiene` | PASS | Both packages, source formatting/typing/hygiene |
| `bash scripts/check-repo-health.sh` | PASS |106 passed, one existing recommended English release-guide warning, zero failures |
| Source sync `--check` against actual producer Git objects | PASS | Exact normalizer/contract/schema/fixture bytes, immutable source lock |

`unshare -Upf --map-current-user --mount-proc make ci`: **PASS**, exit0 in500.49s.
Server880 passed; Client2586 passed,20 skipped,10 integration cases deselected. Both
sdist/wheels built, all twine checks passed, both `py.typed` markers were present, and a
fresh client-only install performed actual local HTTP plus literal v1 normalization.
The optional local server extra installed and registered commands, and `pip check` passed.
These are local build/install results, not a package publication.

CI retained one `PytestUnraisableExceptionWarning` from the existing
`test_reused_candidate_keeps_real_http_and_pty_listeners_separate[True]`: a websockets
handshake coroutine was finalized after its event loop closed. The test itself passed;
the full `make test` run did not report this warning. No handler or warning filter was
changed to hide it. A targeted retry is recorded separately below; it cannot erase
what the complete CI run actually reported.

The warning case's targeted retry passed1 test without reproducing the unraisable warning;
the complete CI's original warning remains recorded. That retry does not establish a root cause.

After the final producer commit removed the engineering `_skeleton` public-name exception
and tightened shared admission fixtures, the SDK copied its exact normalizer/contract/schema/
fixture bytes and updated the source lock. The final source is **fad843f**, not the5cf448
source from the complete full-suite run above. The final delta suite (owner admission,
launch, discovery, models, offline catalog, application binding/auth) passed **306 tests**.
Final `make lint typecheck format-check hygiene` and actual producer Git-byte comparison
both returned0. No old full-suite result is relabeled as an unexecuted final-head full run;
the actual final head still requires remote CI.

Final staged secret, diff, source-lock and documentation/record checks are recorded below.
The single-interpreter check does not replace the remote Python3.10/3.11/3.12 matrix.

The20 existing Client skips are explicit local-engine prerequisites:2 tests require an
`ABX_COMMAND_TEST_BIN`,5 need the legacy sibling CLI fixture path, and13 engine integration
cases need that CLI/dependency layout (Container4, Cube3, E2B6). The new v1/ports/private-env/
PostgreSQL tests are not skipped. These skips are not missing cloud credentials.

## Documentation and source recipe boundary

Bilingual resource, authoring, launch and API references describe v1 and the new endpoint
method. Parsing prepared literals does not install a CLI; selected Providers may still have
runtime dependencies. The Managed Server must install a matching immutable client source
commit to consume instance/env fields; unchanged version metadata does not turn an older
published0.4.0a7 artifact into this source. Guest bridge/server production code and its
protocol remain unchanged. The template owner verifies that source recipe separately.

## Cleanup and remaining gates

No cloud resources or model calls were created by these checks. Local PostgreSQL fixtures
and controlled probe children were cleaned up. A read-only baseline worktree was used for
comparison; it created no deployment. Staged sources contain no credentials or private logs.

Real cloud/model/FC deployment, actual arbitrary port reachability, remote matrix, official
OpenAI SDK interoperability, package publication and merged delivery are not established.
The local server's saved-Agent plus inline override rejection remains a separately identified
compatibility difference; this patch does not claim to fix every server entrypoint.

Related history: [first freeze](2026-11-12-template-v1-runtime.md),
[ports and cancel comparison](2026-11-12-template-v1-runtime-ports.md),
[decision](../../notes/proposed/feature/2026-11-12-template-v1-runtime.md).

## Final staged review

Only bilingual API/launch guidance, the decision/index links and this independent evidence
were added after the consumer-code freeze. The only runtime-source changes after1079841
are the exact final canonical owner files/source lock described above; no SDK launch,
Provider, Managed or cancellation implementation was modified. Historical
failed records and cancelled-process controls remain available as evidence. Staged secret
scan, `git diff --cached --check`, current repository health/hygiene and actual producer-byte
sync checks are required before the final evidence commit; their actual outcomes follow.

Final outcomes: staged custom secret scan0; staged diff check0; producer source-byte sync0;
health106 PASS /1 existing recommendation /0 FAIL; hygiene0. The repository hook also
runs the custom secret scanner at commit. Its optional pre-commit framework is not installed
in this validation environment; the hook reports that fact rather than bypassing a configured
framework run. Full local CI above separately performed the mandated lint/format/type/test/
build/install checks. Credentials remained in ignored sources and were not staged.
