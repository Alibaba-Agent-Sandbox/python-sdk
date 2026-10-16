# Verification: real-cloud acceptance integrity

- Date: 2026-10-16
- Result: PASS for corrected Express acceptance; native backends remain unverified.
- Scope: E2E server fixture/provider harness, offline regression, bilingual E2E
  guidance, changelog and these engineering records.
- Environment: Linux; Python 3.11.15, editable SDK distributions 0.3.0, built
  Node CLI. Authorized configuration is loaded in memory and never recorded.

## Initial full run and controlled diagnosis

`make e2e` initially failed: 18 server fixture errors, two catalog credential
refusal failures, four missing-provider skips and the documented Jupyter
trailing-expression KI-009 expected failure. Missing catalogs raise E8001, so
those failures do not prove their authentication boundaries. No original full
suite pass is claimed.

One focused rerun reproduced the 60-second `/commands` readiness timeout and
both missing-plugin errors. A separate owned `python-hello` sandbox started
`/app/commands.py` with exit zero. `GET /commands` with its envd access header
returned 502; without that unrelated header it returned 200 and four commands.
The diagnostic sandbox was explicitly destroyed. This agrees with the existing
`Sandbox.server_at` contract, which deliberately omits the envd token.

Review also found that the obsolete sibling-CLI fallback only produced a
`cli: blocked` row. The report assertion visited recorded rows without requiring
expected rows, allowing unexecuted CLI features to satisfy acceptance vacuously.

## Executed checks

- `pytest tests/test_providers/test_e2e_report_contract.py -q` from client-sdk:
  PASS, 15 regressions including explicit CubeAPI selection and invalid origins.
- Original harness restored temporarily: expected FAIL, six failed and four
  passed; missing-row and obsolete-launcher defects are detected. Fixed source
  restored in `finally`.
- Client `ruff check src/ tests/` and format check: PASS, 198 files formatted.
- Verified local catalog installation in throwaway HOME with `--link --yes`:
  e2b, alicloud-container, opensandbox and cubesandbox each exit zero; doctor
  handshake verification was retained.
- Corrected complete `make e2e`: PASS, 113 passed, four native-backend skips,
  two slow cases deselected and one documented KI-009 expected failure,
  232.56 seconds. The built CLI ran via ABX_BIN; all expected report rows and
  original response assertions were enforced.
- Intermediate isolated full run: FAIL, 111 passed and three failed in 241.68s.
  The E2B host correctly refused with E1003 while the test expected only
  provider-layer E1001; container likewise needed the host refusal type.
  Cube readiness treated an arbitrary local listener as a selected backend.
  All three findings are addressed without changing product defaults.
- Final nonce/docstring follow-up: real CLI plus both credential-refusal tests
  PASS, three tests in 56.17s. Canonical Express settings remained available;
  E2B/container-scoped variables and generic E2B aliases were absent. Neither
  the checkout nor isolated HOME contained dotenv files to refill credentials.
- Both-package `make lint format-check typecheck hygiene`: PASS; server mypy
  checked 56 files and client mypy 83. The isolated dev environment avoids the
  earlier shared environment's optional-Playwright typing mismatch.
- Additional direct lint of E2E files found three pre-existing conftest style
  findings (capitalized helper alias and two long lines). The standard
  both-package lint gate passes; no lint rule was disabled.

## Cleanup and limits

The successful full run's readonly janitor reported zero tagged candidates out
of one listed sandbox and zero deletions; the unrelated resource was preserved.
After the final focused run it reported zero candidates out of zero listed.
Both isolated Node engines stopped before temporary-HOME cleanup. Owned suite
trackers/finalizers handle failure cleanup; no arbitrary resources were deleted.

OpenSandbox skipped for unavailable local backend health; Cube for no explicit
authorized CubeAPI target; native E2B and container edition for missing their own
configuration. These skips are not passes. KI-009 remains the documented platform
Jupyter HTTP 404 trailing-expression limitation; it was not converted to a pass.

## Independent review

Root independently reviewed the three-file harness diff and 15 regressions:
missing report rows, standalone argv without a shell, server credential separation,
explicit Cube origin and host/provider authentication refusal types were accepted.
The requested CLI docstring correction and random socket suffixes were applied,
preserving an explicit per-run socket; the real CLI was rerun afterward.
Exact-head remote CI is checked before merge.

## Documentation integration

The branch now includes the merged archive/workspace documentation through
`42f3ff2`. The only merge conflict was the Unreleased Added list; both the MCP
and Chinese archive entries were preserved. Final health: 106 PASS, one optional
release-guide warning, zero FAIL. Hygiene, changed harness lint and whitespace
checks pass. The import-order correction changes no acceptance behavior.

## Dependency delivery and final integration

The exact harness head `3fd592bc9f1245d2ab49c41a34ba6aea52a03407` passed all
nine normal GitHub checks, including both full package suites on Python
3.10/3.11/3.12 and package build. Dependency PR 29 then merged at
2026-10-16 04:23:38 UTC (merge `0f8a31d`); PR 32 merged at 04:38:26 UTC
(merge `8d22eae`) after its final evidence head independently passed all nine
checks. Both merges were confirmed from actual remote state, and their scoped
Issues closed. This PR is retargeted to main and synchronized with that accepted
history. This last integration changes only verification records and the loader
note; MCP product and harness source remain the tested versions. The final head
still receives and must pass its own complete matrix before normal merge.
