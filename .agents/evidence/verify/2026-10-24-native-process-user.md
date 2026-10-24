# Verification: Native process OS user

- Date: 2026-10-24
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/83
- PR: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/94
- Base: b0407a7; scoped shared envd process adapter, tests, documentation and paired version metadata.
- Result: PASS — scoped real-cloud acceptance and remote CI passed; local environment failures are recorded below.
- Package under test: source candidate client/server 0.3.1a2, isolated editable installation, not a public release.
- Environment: Python 3.12.13, Linux, real Express base in the configured region.
  Credentials supplied through the ignored environment, values not recorded.

## What was verified

The published 0.3.1a1 native caller returned UID 1000 for `user="root"`; a standard
caller on the same owned target returned UID 0. This repeats Issue 83. Before the
fix, new wire regressions failed because `process.user` remained in the request
and invalid principals reached HTTP. After the fix, concurrent request identities,
provider credentials and the default identity remain independent.

## Commands run

```sh
uv pip install -e './server-sdk[dev]' -e './client-sdk[dev]' hatchling build twine pip
python -m pytest tests/test_protocol/test_process_user.py tests/test_protocol/test_process.py tests/test_transport/test_http.py tests/test_api/test_commands.py -q --tb=short
make ci
make lint format-check typecheck build dist-check
python -m pytest tests/ -m 'not integration'
python -m pytest tests/test_version_lockstep.py tests/test_protocol/test_process_user.py -q
python -m pytest e2e -m 'e2e and not e2e_slow' --maxfail=5 -ra --tb=short
python scripts/e2e-cleanup.py --all-tagged
python scripts/check_release.py candidate --tag v0.3.1a2
python scripts/check_release.py preflight
bash scripts/check-repo-health.sh
make hygiene
```

The focused unit commands and standalone full unit run use `client-sdk`; the E2E
and make commands use the repository root. The repository has no lockfile;
installation uses owner CI's declared pyproject dependencies in an isolated
environment. The real E2E observer only records the suite's created resource IDs
and independently queries those IDs after the suite's own finalizers; it does not
replace transport or cloud operations.

## Results

| Scenario | Result | Observation |
| --- | --- | --- |
| Focused process/command/HTTP unit suite | PASS | 106 passed |
| Version-lockstep plus new wire regression | PASS | 9 passed after MCP version correction |
| Real same-ID native/standard root | PASS | Both exit 0, UID 0 |
| Real same-ID native/standard user | PASS | Both exit 0, UID 1000 |
| Native `commands.start(user="root")` | PASS | UID 0 |
| Native nonexistent account | PASS | EnvdRpcError, HTTP 401; no silent fallback |
| Default identity before/after explicit calls | PASS | UID 1000 unchanged |
| Official non-slow E2E | PASS with skips | 121 passed, 9 skipped, 2 slow tests deselected; 242.91 seconds |
| Local lint, format, typecheck | PASS | Both packages; 56 server and 98 client source files checked |
| Build and distribution checks | PASS | Both wheels/sdists, twine, py.typed, combined fresh install/import |
| Local full server suite | FAIL, diagnosed | 877 passed, 3 failed; see below |
| Local full client suite, initial run | FAIL, corrected | 2195 passed, 26 skipped, 10 deselected; one stale MCP version constant |
| Local full client suite, corrected run | PASS with skips | 2196 passed, 26 skipped, 10 integration-marked cases deselected; 160.47 seconds |
| Remote Python 3.10/3.11/3.12 matrix | PASS | Both packages on all three versions; server Python 3.12: 880 passed |
| Remote standard contract, Python-to-Node engine, build, hygiene, docs links | PASS | All required candidate jobs completed successfully |
| Repository health / hygiene | PASS | 106 PASS, 1 recommendation WARN, 0 FAIL; no local paths or secrets |
| Paired release candidate and preflight | PASS | Exact tag matches both 0.3.1a2 distributions; no conflicting public artifacts |

Nine E2E skips are explicit configuration limits: four uninstalled optional
providers, two opt-in volume tests, one CLI named-string-array test without
`ABX_E2E_CLI`, one pause test without the required template/allowlist, and one
snapshot test without its template/allowlist. They are not successful scenarios.
Two slow tests were intentionally excluded by the official non-slow marker.

An independent agent reviewed the implementation, real HTTP-client wire assertions,
same-ID comparison script and exact cleanup checks; no scoped blocker was found.

Candidate c10bfc281672f26dfb5710a7625a88e10d69f512 passed
[full CI](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40062672960)
and [documentation links](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40062672974).
The following evidence-only commit must also pass its own latest-head checks before
merge; that gate is recorded on PR 94 rather than predicted here.

## Cleanup

The focused live run registered its creation ID, killed only that sandbox in
`finally`, and independently read it back as `SandboxNotFoundError`. After the
full E2E suite, all 25 observed owned IDs independently returned that same exact
not-found exception. The required janitor dry run exited 0: zero candidates out
of zero listed, zero deletions. No resources from either run leaked. The exact-ID
readbacks, rather than the potentially eventually consistent list, establish absence.
No resource identity, gateway URL, credential or raw provider response is published.

## Problems found

The initial local `make ci` server run had three failures. Two raw HTTP assertions
received 501/502 rather than 400 in this managed environment. Both failed identically
against a separate unmodified b0407a7 server source checkout; no server request
implementation changed in this PR. The third failure was the isolated uv environment
lacking pip, causing its package-list test to see no pytest package. Installing pip
in that environment made that exact test pass; no product/test assertion changed.

The first local/remote client run caught a real omission in this PR's version bump:
MCP still advertised 0.3.1a1. Its existing regression was preserved, the constant was
updated to 0.3.1a2, and the version regression passed. The initial failure remains
visible in [CI run 40062233616](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40062233616).
Local `make ci` is not represented as a green run. Final remote matrix results are
recorded separately to distinguish the managed-environment failures from the fix.

## Not verified

Public 0.3.1a2 installation/publication is not part of this PR verification. Both exact
PyPI version endpoints returned 404 before preparation; no existing version is replaced.
Optional skipped backends, volume/pause/snapshot admission and slow cloud cases are
not covered by this run. Latest-head remote checks remain required before merge.
