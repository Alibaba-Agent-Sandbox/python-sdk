# Verification: provider and Python release readiness

- Date: 2026-10-23
- Change: `2026-10-23-release-readiness`; base `fee74e631d9cfc3488fd41f853ca6dafc1277784`.
- Result: BLOCKED (required real-cloud acceptance and remote review are not completed).
- Environment: Linux, CPython 3.12.13; isolated development and public-source environments.
- Package under test: client/server 0.3.0, both editable candidate and separately built wheels.
- No credentials or cloud resources were used.

## What was verified

Catalog checks compare actual content even when display versions match, updates preserve
recorded sources and rollback on verification failure, and runtime load rejects incompatible
SDK requirements. Node doctor waits for actual engine initialization, refuses missing launchers
and old engines, and always closes its client. Real Node fixtures reject invalid JavaScript and
confirm infrastructure close without invoking create/list. Publication checks bind matching
package versions to a version tag and refuse differing existing public artifacts.

## Commands run

- `uv venv --python 3.12` and `uv pip install -e './server-sdk[dev]' -e './client-sdk[dev]' build twine`; no repository lockfile exists. Added pip to the test environment for package-list tests.
- `pytest -c client-sdk/pyproject.toml client-sdk/tests/test_providers/test_node_doctor.py client-sdk/tests/test_providers/test_catalog_update.py client-sdk/tests/test_providers/test_runtime_reliability.py client-sdk/tests/test_release_validation.py -q` — 14 passed.
- `make lint typecheck format-check` — PASS for both packages, including 56 server and 98 client typed source files.
- `make build dist-check` — PASS: both wheel/sdist pairs, twine, py.typed and clean combined wheel install outside the source tree.
- Public paired archive `python -m pip install` using both documented `fee74e631d9cfc3488fd41f853ca6dafc1277784` URLs — PASS; standard sync/async, ProviderSandbox and server imports/API shapes and `pip check` passed outside the repository.
- `python scripts/check_release.py candidate --tag v0.3.0` and `preflight` — PASS. No files were uploaded. Negative tag/hash checks are unit tested.
- Both changed workflow files parsed as YAML; publication now depends on the same-tag reusable CI suite.
- `bash scripts/check-repo-health.sh` — 106 PASS, 1 recommendation WARN, 0 FAIL.
- `make hygiene`, staged secret scan and `git diff --check` — PASS.
- Actual Node doctor integration with companion CLI source commit `a40fab7c4d11824e3a14055af19b6ce0093467b5` — 2 passed, valid factory plus close and invalid JavaScript; no backend operations.

## Results and limitations

The first `make test` server run produced 872 passed, 1 skipped and 3 failed. One package-list
failure was an unseeded pip environment; adding pip fixed it. Removing inherited HTTP proxy
variables allowed the chunked-framing check to pass. The missing-WebSocket-key raw upgrade
still received HTTP 501 instead of the expected application 400 in this managed network environment.
No server source was changed and the rejection expectation was not weakened.

The full cross-language Cube scenario reached the actual Node engine and sandbox fixture but
its envd process RPC was intercepted with HTTP 501 and the message that project network audit
is disabled. Clearing proxy environment did not remove that platform response. This is BLOCKED,
not a cloud or complete interoperability PASS. The strict CI job is retained with immutable public
peer revisions and bounded execution; missing prerequisites fail rather than silently skip.

The complete client suite ran 2,193 passed, 21 skipped and 4 failed. Two failures were
the cross-language HTTP 501/502 restrictions above. Two stale integration fixtures still
expected native Express interpreter RPC success after main deliberately removed that unsupported
implementation. The fixtures now assert E8004 before transport and retain context-manager cleanup;
the whole affected integration module was rerun: 10 passed. The provider-only suite ran 500 passed, 20 skipped
and the same two blocked cross-language failures. No failed run is labeled a full pass.

An initial fixture lacked the new required workflow table; it was corrected before the successful
real doctor run. An exploratory uv install using unnamed identical archive URLs with different
subdirectories hit metadata cache confusion; the documented pip command succeeded. These initial
failures are not counted as successful validation.

## Cleanup

Only isolated local worktrees, virtual environments, package artifacts and loopback test processes
were created. Engine fixtures terminate their owned processes. No cloud sandbox was created and
no cloud cleanup or deployment was attempted.

## Not verified

Real-cloud `make e2e`, all Python versions, Dockerfile image builds (Docker unavailable), remote
CI/review/merge and actual PyPI publication/readback remain unrun. No GitHub write credential is
available for this task. The doctor endpoint is not in public CLI 0.4.10; the candidate must land
with its companion CLI support, and the public source recipe intentionally refers to already
published Git content rather than claiming this patch is released.
