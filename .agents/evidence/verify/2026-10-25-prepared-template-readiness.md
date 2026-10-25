# Prepared-template readiness verification

Date: 2026-10-25
Result: PARTIAL

Scope: prepared-reference Python `ready_cmd` polling, four regressions, bilingual
launch documentation and the lockstep 0.4.0a3 version/dependency metadata. Base is
main cdf807a4a40079e7d215c0d299b061f0c895a8cb. No provider implementation changes.

## Original failure and cause

OpenSandbox run [40206364834](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/actions/runs/40206364834)
failed in the public a2 Python prepared launch with readiness-command-failed.
Default source CLI build/push/launch, named application command, direct/proxy
authentication probes and independent Node proxy call had passed. Final runner
cleanup passed. This was not a failed image build or push.

Installed public a2 was reproduced on an actual Express `base` reference. A stdlib
HTTP server delayed its listener five seconds. Its first ready probe returned exit 1
(connection refused) after 0.524s. The exact owned server PID was alive before and
after the same port became healthy 5.364s later, inside the 15s budget. A diagnostic
observer returned the original failed result unchanged; a2 still rejected launch.
Independent typed NotFound confirmed cleanup. An earlier diagnostic incorrectly
assumed process-list membership for a child PID and failed its own assertion; its
sandbox was also confirmed absent. Both original receipts remain preserved.

## Executed checks

Python 3.11.15, new isolated editable candidate pair 0.4.0a3 (not a public package),
no source-path injection into public a2. Candidate runtime bytes and sanitized
cloud results are in the adjacent JSON receipt.

- New regression baseline against a2: 3 FAIL, 1 PASS (cancellation already cleaned).
- Focused `pytest tests/test_api/test_template_launch.py -q`: PASS, 25 tests.
- `make lint typecheck`: PASS for both packages.
- `make hygiene`: PASS.
- `make format-check build dist-check`: PASS; all four distributions built,
  both wheels installed together in a clean environment, imports and pip check
  passed. The built client wheel's runtime bytes match the cloud-tested source.
- Full client suite: 2,275 PASS, 26 explicit skips.
- `make test` server suite: 877 PASS, 3 FAIL. Two raw-HTTP tests observed 501/502
  instead of expected 400, matching the earlier local-environment failures. The
  package-list test initially lacked pytest because the new uv environment had
  no pip. Installing pip in that environment and rerunning that test passed.
  The original failures remain recorded; no assertion or fixture was weakened.
- Final repository health after record insertion: 106 PASS, 1 WARN, 0 FAIL.
- Actual candidate cloud: delayed listener initially returned five nonzero probes,
  then exit 0 and successful launch; exact server PID remained alive. Permanent
  unready launch used a 1s budget and raised the existing phase error after 1.174s
  including cleanup. Cancellation after the first probe preserved cleanup.
  All 3 owned sandboxes were independently typed NotFound; no recovery was needed.
- Independent read-only review of runtime/tests: no blocking finding. Budget is
  per ready-command phase, not a new whole-launch deadline.

The full existing OpenSandbox T4 passed in
[run 40208641347](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/actions/runs/40208641347),
provider source b78ea200ba7ccb30cd868ae609cad9c7b5031e31 and exact SDK candidate
2ad2a482571bc030a7be298217cf7956bd164da4. All job steps succeeded, including
default/portable/proxy launch, CLI and Python application calls, independent Node
proxy call and final owned-container absence. Adjacent JSON records exact inputs.
This is a candidate host pair; the actual guest server remained public a2.
The final follow-up changes only this evidence, not the tested runtime bytes.

Latest-head remote CI, final review,
normal merge and public a3 release/readback remain pending. There is no Docker on
this local host. No public a3 or whole-catalog acceptance is claimed.

Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/121
