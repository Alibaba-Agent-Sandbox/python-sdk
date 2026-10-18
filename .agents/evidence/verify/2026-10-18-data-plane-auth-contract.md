# Verification: explicit sandbox API-key contract

- Date: 2026-10-18
- Result: PARTIAL; local and configured cloud acceptance pass, latest-head hosted gates pending
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
- Full client Ruff, format and mypy: PASS; 86 typed source files.
- Both sdist/wheel pairs, twine, py.typed and combined installed imports: PASS.
- Combined accepted replay/main source 42d4449: auth plus replay regressions87 PASS.
- Fresh full configured real-cloud repeat against this combined source:115 PASS /4SKIP /1XFAIL /2DESELECTED, exit0 in349.39s. Janitor exit0:zero candidates,zero total sandboxes. Skips are unconfigured vendors, not provider passes.
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

Accepted replay main was merged with an ordinary commit, preserving both owner
records. The configured cloud suite and cleanup passed on combined source.
Final hosted Python3.10/3.11/3.12 full suites, build/links/hygiene and review
remain required before merge. Native unconfigured vendors are not passes.
No credential resource was minted by the investigation or tests.
