# Verification: explicit sandbox API-key contract

- Date: 2026-10-18
- Result: PARTIAL; final combined-source cloud/hosted gates pending
- Base: Python SDK main 145341d, before accepted replay update 3d4ac95
- Scope: default auth factory and custom callback validation, removed guessed
  exchange/signing implementation, bilingual authentication/config/error and
  architecture guidance, shipped SDK usage guide and owner records.

## Executed checks

- `pytest tests/test_transport/test_auth.py -q`: 44 PASS.
- Full client `pytest tests/ -m "not integration"`: 2052 PASS / 21 SKIP /
  10 DESELECTED, two existing event-loop/subprocess warnings. Retired tests
  exercised a guessed exchange endpoint and are removed with that implementation.
- Ruff check/format: PASS for changed auth source/tests; full client check run.
- Full mypy and final document checks: in progress; no pass claimed yet.
- Repository health: 106 PASS / 1 existing WARN / 0 FAIL.
- Hygiene: PASS. English and Chinese page sets match.
- No server source/test or dependency changes. Accepted main/replay PR54 has
  all six full package interpreter jobs plus build/hygiene/links successful;
  this does not replace this contribution's latest-head CI.

## Verified behavior

AK/SK-only factory calls for two regions reject locally without constructing
an HTTP client. Explicit/canonical API keys keep priority. Custom exchange
adapters retain cache/refresh, reject object/number/empty results without caching,
and normalize valid strings. No credential resource was created in investigation.

Official SDK wire-shape inspection establishes that CreateApiKey exists and
uses a credential-resource POST; it does not establish temporary-token semantics.
The retired guessed RPC implementation is not replaced with an implicit mint.

## Remaining checks and cleanup

Merge accepted replay main without overwriting auth work, then verify the final
combined source. Run configured real cloud and cleanup, all owner required
checks and latest hosted matrix/review before merge. Native unconfigured
providers are not passes. No cloud resource was created by these local checks.
