# Verification: Integer named-command booleans

- Date: 2026-10-21
- Change: [Issue 80](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/80)
- Result: PARTIAL
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
