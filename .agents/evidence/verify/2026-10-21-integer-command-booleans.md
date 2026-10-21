# Verification: Integer named-command booleans

- Date: 2026-10-21
- Change: [Issue 80](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/80)
- Result: PASS — runtime/cloud acceptance; final record-only head must pass its own CI before merge
- Package under test: client/server 0.3.0, source base a1217af; isolated editable Python 3.11.15 environment.
- Environment: Linux; model credentials are never used by these checks.

## What was verified
Original shared integer coercion accepts JSON booleans before template guards. Reproduced on actual Express during QM Sandbox acceptance and on current SDK main.

## Commands run
`pytest server-sdk/tests/test_server/test_app.py -k boolean_integer -q` and `pytest client-sdk/tests/test_utils/test_coerce.py -k integer_rejects_json_boolean -q` before changing production.

## Results
Both HTTP boolean cases failed (200 rather than 400); both client parser cases failed (no exception). This confirms execution before validation on the original source. Post-fix and full required results remain pending.

## Cleanup
Initial template attempt independently confirmed owned cloud and OSS absence. SDK-specific cloud verification remains pending.

## Problems found
The HTTP layer converts `true` to 1. No exception or credential data is included.

## Not verified
Current fix, full unit/CI/build and cloud E2E are pending; this is not completion evidence.

## Review checkpoint
Mirrored integer parser now rejects bool before dispatch. Both packages lint/typecheck, hygiene and built-wheel/sdist combined-install checks pass. Existing dated JSON evidence was incorrectly omitted by the health stem index: original main reported six missing records. The scoped correction now passes repository health and a temporary deliberately missing record still fails; see [health controls](2026-10-21-integer-command-health-controls.json). Historical files were not edited.

The first SDK-specific cloud controller used an unavailable `get_host` method on the native Sandbox; it failed before its assertions, and its tracker independently confirmed zero owned sandboxes remaining. It now uses the actual `sandbox.network.get_url` API. The full real Express suite is running on corrected source.

The local full server run reproduces the previously recorded malformed-HTTP boundary responses (501/502) independently of this change. The original [local boundary proof](2026-10-20-local-http-boundary.json) and [prior complete remote verification](2026-10-20-named-string-array-final.md) are preserved. No assertion is weakened; current-head remote CI is required. Other current checks remain in progress, so this record stays PARTIAL.

## Actual post-fix checks
Full `make e2e`: **122 PASS / 8 SKIP / 2 deselected / 1 known platform XFAIL**, 277.12 seconds. The dedicated changed-feature case uses the source-uploaded/hash-checked server, raw HTTP 400 and actual SDK argument errors, checks the command was never entered for either boolean, and verifies real integer/numeric-string and boolean-field compatibility. Existing original array SDK/native CLI cases pass with actual CLI 0.4.1. [Cloud source proof](2026-10-21-integer-command-cloud.json), [initial controller failure](2026-10-21-integer-command-first-cloud.json), and [independent cleanup](2026-10-21-integer-command-cleanup.json).

Full local client non-integration: **2208 PASS / 23 SKIP / 10 deselected**, 139.30 seconds. Full local server: **876 PASS / 3 FAIL**, 314.18 seconds: two previously proven operator HTTP-boundary responses, plus absent pip in the fresh uv environment. Bootstrapping pip with ensurepip fixes the package-list test (**1 PASS**, 0.87 seconds); server coercion and real HTTP command suites separately pass **80/80**, 23.02 seconds. Server parser/HTTP changed-feature assertions pass; no local boundary assertion is relaxed. Current-head remote complete server suites remain required for these unchanged malformed-framing cases.

`make lint typecheck hygiene build dist-check` passes both distributions, including actual wheel combined installation and py.typed. Repository health passes with its real missing-record negative control. Current-head remote matrix is pending, so the PR remains a draft.

## Complete runtime remote matrix
All ten [runtime-source checks](2026-10-21-integer-command-runtime-ci.json) pass at `c6fc4e5efe1c7e13e6301b6ab7ad4812f84e8262`: full server/client Python 3.10/3.11/3.12, lint, formatting, type checking, build/combined installation, pinned public E2B contract, hygiene and Markdown links. These execute the unchanged malformed-HTTP tests on CI hosts, resolving the local boundary limitation without relaxing assertions. Actual cloud acceptance and independent cleanup pass as recorded above. Earlier PARTIAL/pending descriptions document preceding checkpoints, superseded for runtime acceptance by this section.

No model/account provider, opt-in Volume, pause or snapshot acceptance is inferred. The final evidence/state-only revision changes no executable source or tested controller; its own current-head matrix and normal merge/readback remain required.
