# Verification: server loader cloud delivery

- Date: 2026-10-16
- Change: [PR 32](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/32),
  [issue 30](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/30).
- Result: PASS for the independent source-wheel cloud scenario and focused tests;
  the final synchronized head still requires the complete remote matrix before merge.
- Package: server 0.3.0 wheel built directly from `e2cb27e` using Python 3.11.15,
  `python -m build --wheel --no-isolation --outdir <temporary-output> server-sdk`.
- Wheel SHA256: `a09a4846fef8b49f3a059d1c65e38d283986aa4fbf879dd09192100c30039fc9`.
- Environment: real Alibaba Cloud Express sandbox; authorized credentials loaded
  only in memory. Native E2B credentials were neither inferred nor used.

## Commands and observed behavior

The exact wheel was uploaded to a newly owned base sandbox and installed with
`python3 -m pip install --disable-pip-version-check <wheel>`, including its declared
runtime dependencies. A new command file used postponed annotations and a
`@dataclass` with a `ClassVar[str]`, reproducing the original loader precondition.
The production entry point ran as
`python3 -m agent_sandbox.server serve --host 0.0.0.0 --port 9000 --commands <file>`.
Real gateway HTTP `GET /commands` returned 200, then
`POST /commands/loader_review` with `{"value":17}` returned exactly
`{"result":{"value":17,"label":"loader-review"}}`. No transport was mocked.

An earlier bare-console launch attempt installed the wheel but did not complete
its acceptance assertion; it was not counted as a pass and its owned sandbox was
destroyed. The successful run above uses the supported module entry point and a
separate owned sandbox. Readiness polling only waits for service startup.

Focused source tests ran as
`PYTHONPATH=server-sdk/src python -m pytest server-sdk/tests/test_server/test_cli_main.py -q`:
**13 passed in 0.63 seconds**, including healthcheck, dataclass registration,
canonical-file caching, distinct basenames and failed-import cleanup.
An initial invocation without the explicit source path resolved the previously
installed workspace branch instead: five loader regressions failed and eight
passed. Correcting the import source produced the result above; this also confirms
that the regressions detect the unfixed implementation rather than silently pass.

## Cleanup and limits

Both owned cloud sandboxes were destroyed in `finally` blocks. Subsequent
`python scripts/e2e-cleanup.py --all-tagged` dry run reported **0 candidates out
of 0 listed**, killed zero and exited zero. No unrelated resources were deleted.
The first cleanup invocation used an interpreter without the SDK and failed;
the explicit development virtual environment produced the successful dry run.

The earlier partial results remain in the original server-command-loader evidence.
The archive-page health failure was independently fixed and merged by
[PR 40](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/40).
The complete cloud harness suite on the lifecycle successor is separately recorded
in [PR 33](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/33): 113 passed,
four unavailable native-backend skips, two slow deselections and one documented
KI-009 expected failure. That successor run is not described as an exact-source
run of this loader branch. Docker image rebuilding, other native providers and
public package publication are outside this loader verification.

## Final synchronized gates

Head `126e4451c5edc79e5ca1b9c9e3c00e2eada5127f` passed all nine GitHub
checks: both packages on Python 3.10/3.11/3.12, package build/distribution checks,
Markdown links and path/secret hygiene. The source-wheel scenario and loader
source remain unchanged after synchronization with the accepted workspace fix.

A fresh local Python 3.11.15 environment installed both editable packages with
87 dependencies. `make ci` passed both-package Ruff, formatting and mypy (client
83 and server 56 files), then stopped at the local server suite: **853 passed,
seven failed in 309.03 seconds**. Six failures are the established restricted
host raw-HTTP framing/upgrade/auth tests (including explicit platform HTTP 501
network-audit denial); the seventh package-list test expects the `pip` executable
in a uv-created environment that has no pip distribution. These are not passing
local tests and were not retried through alternate network paths. The exact-head
normal GitHub matrix passed those same complete server suites on all three
interpreters, establishing the supported environment behavior independently.
The failed local `make ci` stops before client tests/build; those gates passed in
the exact-head GitHub client/build jobs. A final evidence-only update reruns its
own complete matrix before merge; no product code or tests are changed to hide
these host differences.
