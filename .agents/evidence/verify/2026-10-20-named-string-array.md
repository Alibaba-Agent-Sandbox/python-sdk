# Verification: native named-command string arrays

- Date:2026-10-20
- Change: [Issue76](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/76),
  [gate prerequisites Issue77](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/77).
- Result:PARTIAL — actual changed-feature Express acceptance passes; current-head remote CI pending.
- Packages: client/server0.3.0, editable workspace installation; changed server source
  uploaded and SHA256-checked in fresh owned sandboxes, independent of the installed template server.
- Environment: Debian operator/Python3.11.15; real Alibaba Express, native CLI0.3.0.
  Credentials only in the existing environment; captured output redacted before storage.

## What was verified

Real HTTP preregression returned a Python string representation instead of an array.
Strict native JSON arrays now preserve exact elements through Python and native CLI,
reject mixed/string/null inputs, and copy caller/default arrays. Existing scalar tests pass.
The new E2E regression uses this checkout's server, not an assumed cloud package.
The full initial run also exposed existing native-vs-standard entry mistakes and
uninstalled-provider refusal assumptions; the recorded follow-up repairs those tests.
Installed providers still require the original strict credential errors.

## Commands run

`make test`; `make ci`; `make lint typecheck hygiene`; client pytest with
`-m 'not integration'`; focused server/client regressions; `make build dist-check`;
`bash scripts/check-repo-health.sh --quiet`; `make e2e`;
`python scripts/e2e-cleanup.py --all-tagged` (dry-run).
The native CLI executable is supplied through documented `ABX_BIN` and new optional
`ABX_E2E_CLI` for the array regression. Neither command skips assertions.

## Results

| Scenario | Result | Notes |
| --- | --- | --- |
| Real HTTP preregression | Expected FAIL | String instead of native array |
| Initial scoped server/client regressions | PASS |76and115tests |
| Final server array cases | PASS |15real HTTP/registration cases |
| Final client array cases | PASS |11cases, including declarative default metadata |
| Full client non-integration suite | PASS |2198passed,24skipped,10deselected |
| Local full server suite after pip bootstrap | FAIL |867passed,2failed,1skipped; raw HTTP boundary below |
| Lint/typecheck/hygiene | PASS | Both packages;56server/105client typed source files |
| Distribution build/check | PASS | Both wheels/sdists, py.typed and combined install/import |
| Repository health | PASS |106PASS/0FAIL/1existing missing-release-guide recommendation |
| First full real Express run | FAIL |115passed/6failed; immutable initial report retained |
| Full real Express after gate corrections | PASS |121passed/8skipped/2deselected/1known xfail,248.70s |
| Named-array actual Python and native CLI | PASS | Both new cases pass in the full run |
| Cleanup | PASS | Janitor dry-run0candidates; independent own-run list0remaining |
| Current-head remote matrix | Pending | Required before ready/merge |

## Cleanup

[Independent cleanup](2026-10-20-named-string-array-cleanup.json) and
[full cloud results](2026-10-20-named-string-array-full-e2e.json).
Existing fixture finalizers delete all known sandbox IDs, sweep only their run tag,
and the final dry-run found no tagged resources. No other actor's resources were deleted.

## Problems found

The local environment changes two malformed HTTP cases: missing WebSocket key
returns501 instead of native400, and chunked framing returns502 instead of400.
An independent authored HTTP service, with no SDK imported, reproduces these exact
responses while ordinary HTTP preserves its400/marker. The chunked response loses
the owned marker; the invalid upgrade does not reach the handler.
See [boundary proof](2026-10-20-local-http-boundary.json).
An unchanged main worktree also reproduces the WebSocket failure. No assertions
were relaxed. The initial package-list failure was resolved by bootstrapping pip
into the uv environment, as required by the Makefile's developer setup.

The forwarded cloud health route can answer before the owned server catalogue;
the new regression explicitly polls the known asynchronous catalogue readiness.

## Not verified

Current-head remote CI remains pending. Other catalog providers and opt-in
volume/pause/snapshot scenarios are skipped with their actual reason, not certified.
KI-009 remains an expected platform failure. Arbitrary JSON/numeric/nested arrays
are outside the implemented public string-array contract.
