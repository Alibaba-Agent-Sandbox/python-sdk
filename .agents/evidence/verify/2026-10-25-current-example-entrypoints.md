# Verification: current example entry points

- Date: 2026-10-25
- Change: [Issue 111](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/111)
- Result: PARTIAL; final cloud, CI and publication gates are in progress.
- Public package under test: `agent-sandbox-client[all]==0.4.0a1`, automatically
  paired with `agent-sandbox-server==0.4.0a1`, installed from PyPI in a clean venv.
- Candidate package: paired 0.4.0a2, same runtime APIs; example/docs/version fixes.
- Environment: Linux, public-example Python 3.13.13, owner checks Python 3.11.15.
  Express credentials supplied through process environment; values not recorded.

## What was verified

Actual scripts were executed with public installed packages. The current local
runner passed all local executable scopes: agent loop, file/session client,
complete case, python-hello server/client, agents-cli server/controller and both
hosted clients, plus quickstarts 01 and 02 through the local-process provider.
Those Codex/Qwen programs are controlled protocol executables, not model calls.

Cloud quickstarts, statistics/data/compatibility examples and real model code
creation have been executed. Final per-entrypoint results and cleanup counts are
being reconciled below before this record can report completion.

## Commands run

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client[all]==0.4.0a1'
python examples/run_examples_e2e.py
# Cloud scripts: exact individual commands are listed in docs/en/guide/cloud-examples.md.
make ci
make e2e
```

## Results

| Scope | Result | Notes |
| --- | --- | --- |
| Fresh PyPI public pair installation | PASS | Client and automatic server both 0.4.0a1 |
| Current local examples | PASS | Real HTTP/files/process; controlled agent protocol programs |
| Standard import-migration example | PASS | File bytes, persistent interpreter 41 to 42, one independently absent sandbox |
| Current capability example | PASS | Exit status, binary round trip, JSON workflow, remote decorator; two owned sandboxes independently absent |
| Real model sorting example | PASS | Real compatible model; five cases checked against independent local `sorted()`; one owned sandbox independently absent |
| Data-analysis oracle additions | PASS | CSV/Decimal reference totals and product ranking; five owned sandboxes independently absent across two scripts |
| Browser external-page earlier attempt | FAIL | Page did not expose expected h1; cleanup confirmed. No browser-engine success inferred from this attempt |
| Default browser owned-page candidate rerun | PASS | Candidate SDK; real Chromium 156, owned HTTP/title/link, PNG 11,473 bytes, HTML 172 characters; 280.36s; one owned sandbox independently absent |
| Initial owner `make ci` | FAIL | Server 872 passed, 3 failed, 1 skipped; remaining targets did not run |
| Package-list failure investigation | PASS | Installing pip in the uv-created check venv resolved its missing-pip prerequisite; focused test passed |
| Raw HTTP environment probe | PARTIAL | Actual chunked request returned expected 400. Malformed WS upgrade was intercepted by host network audit with 501/plaintext, not the server's HTTP response |
| Required `make e2e` | PASS | 126 passed, 9 skipped, 2 deselected; 239.24s pytest; janitor dry-run 0 candidates |
| Initial source head clean-runner CI | PASS | All 11 checks at 39d09af, before the additional execution-deadline fix |
| Candidate full client unit suite | PASS | 2240 passed, 27 skipped, 10 deselected before the two new deadline regressions |
| Candidate distribution checks | PASS | Four 0.4.0a2 distributions, twine, py.typed and fresh combined installation |
| Additional runtime deadline fix | PASS (focused/cloud) | Issue 113: 24 protocol tests; full real-cloud suite now 127 passed, 9 skipped, 2 deselected; janitor 0 candidates |
| Final-head CI and release | IN PROGRESS | Not inferred from the initial head or candidate passes |

## Cleanup

A fresh public `ProviderSandbox.connect` checked each observed owned cloud ID after
example completion. Standard sync creates were also observed and checked. All
completed successful example scopes recorded above were already absent before any
harness cleanup. Interrupted runs retain their incomplete verdict; no pass is
inferred from resource TTL or a missing local process.

## Problems found

Old `api_key` keywords in the provider API, contradictory credential documentation,
retired upload/download endpoints, invalid protocol fixtures, ignored session
workspace/adapter fields, obsolete registry fallback, swallowed exceptions and a
simulation branch. These are removed rather than supported through aliases.
The E2B cloud verifier also had a doubled-prefix credential-name typo, corrected
to the actual provider configuration name.

## Not verified

The final published 0.4.0a2 installation and reruns, plus final-head owner CI gates
remain pending. Cloud skips were missing OpenSandbox/Cube/E2B/container
plugins/backends, explicit volume opt-in, the optional CLI named-array configuration,
and platform-enabled pause/snapshot accounts. None was counted as a pass. Provider accounts not configured for this run do not
receive Express credentials and do not count as passes.

## Independent review corrections

A separate agent found one remaining implicit adapter selection and the local
provider test installer using the user's HOME with `--force`. Both were removed:
use the explicit public adapter selector and an owned temporary HOME without force.
The local HTTP examples additionally assert actual upload/download bytes. The
complete local runner was executed again with all local scopes passing.

The intermediate public-SDK owned-browser run exceeded the harness 900-second
limit and remained TIMEOUT; the exact owned sandbox was independently confirmed
absent afterward. That attempt is not overwritten by the later candidate pass.
