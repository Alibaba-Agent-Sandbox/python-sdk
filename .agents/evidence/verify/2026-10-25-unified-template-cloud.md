# Verification: complete-template candidate and real startup

- Date: 2026-10-25
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/108
- Result: PARTIAL — startup and configured CLI acceptance passed; final-head remote CI is pending.
- Packages: client/server 0.4.0a1, paired editable checkout and clean built-wheel install.
- Environment: Linux Python 3.13.13, real Express account; credentials supplied through
  process environment only. Nothing was published to PyPI during this verification.

## Startup regression and correction

The first real multi-service test was refused before resource creation because the
Python Express Provider's startup metadata omitted `exec`, despite having an existing
process startup implementation. Adding `exec` to that Provider's startup declarations
is verified by the actual startup stream below. No capability checks were bypassed.

`python -m pytest e2e/test_managed_template.py -q -ra`: **5 passed in 22.37 seconds**.
The four native scenarios create `base`/`code-interpreter-v1` using provider name/object,
execute shell commands and confirm deletion. The fifth starts two independent Python
HTTP listeners from one `start_cmd`, executes the template's readiness command, resolves
both Provider endpoints, requests the two declared `/health` routes from the host and
confirms deletion. The journal contains exactly one `started` event. It does not test
an interpreter API or claim arbitrary HTTP protocols have standard health routes.

The final focused launcher suite passed 21 cases, including unknown protocol/version
endpoints without invented health probes. Only SandboxServer protocol v2 receives
built-in health/discovery; an author-supplied ready command checks overall readiness.

## Broader validation

- `make lint`, `make typecheck`: PASS for both packages.
- `make format-check build dist-check`: PASS, including four distributions, twine,
  clean combined installation, imports and both `py.typed` markers.
- `make test`: 878 server passes and two environment-intercepted failures, so make
  stopped before the client target. Separate full client run: **2260 passed,
  20 skipped, 2 failed** (Cube engine HTTP 502). These failures remain recorded.
- A localhost-only `NO_PROXY` rerun retained the invalid WebSocket upgrade HTTP 501;
  chunked HTTP rejection passed alone. No test or server behavior was weakened.
- Remote CI for `ff073167f8993a5c580c78cccccd5779db1f5836`: all 11 checks passed,
  including client/server Python 3.10/3.11/3.12, engine integration, build and docs.
  The later startup metadata/test commit requires its own remote checks.
- Full `make e2e`: **124 passed, 9 skipped, 2 deselected, 1 failed**. The sole failure
  is the CLI scenario lacking `ABX_BIN`; it ran no CLI sandbox operations. Skips are
  missing installed optional providers, opt-in volume tests, CLI named-array setup,
  and account-dependent pause/snapshot prerequisites. A separately configured CLI
  follow-up using the built 0.5.0 CLI passed: **1 passed in 376.63 seconds**.
  It exercised create/info/list, exec/stream, upload/download and repeated deletion.
  The original missing-prerequisite failure is retained above.

## Cleanup

The five new startup scenarios verified owned resources absent after context exit.
The E2E finalizer reported zero leaked tracked sandboxes. The required
`python scripts/e2e-cleanup.py --all-tagged` dry run found zero tagged candidates;
it deleted nothing. The configured CLI follow-up completed its sandbox deletion and repeated-deletion
checks. A second explicitly scoped configuration run is still in progress.

## Limits

There is no new whole-catalog cloud matrix, source-image build test in Python,
PyPI release, or claim that specification 4 receipts verify specification 5. The
standard SDK contract remains independent. Application server behavior is unchanged.
