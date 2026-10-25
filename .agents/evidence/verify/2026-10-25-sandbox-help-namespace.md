# Verification: exhaustive Sandbox help namespace follow-up

- Date: 2026-10-25
- Result: PARTIAL — source candidate only; local server failures are retained, and exact-head CI, final review, merge and publication remain pending.
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/130
- Base: immutable public a5 source `c7b4a55ff930753eb35866b161184f946b04d46c`.
- Environment: Linux, Python 3.11 development; independent public-a5 negative reproduction used official non-all packages on Python 3.13.13.

## Actual defect and bounded scope

The [public-a5 observation](2026-10-25-public-a5-sandbox-help-negative.json) records
four class-help imports actually failing with ModuleNotFoundError. The correct
existing root and code_interpreter exports resolve to the exact inspected classes.
These are ordinary first-party Examples; no migration/comparison label excuses
the imports. Standard API names and upstream attribution are preserved.

The candidate changes four docstrings and three paired version/pin declarations
to a6. All 390 shipped Python files were inspected, covering 2358 module/class/
function docstrings: four import residues before and zero afterward, no upstream
runtime imports. Removing docstrings leaves identical execution AST in all four
changed modules. NOTICE, both MIT licenses and original SOURCES remain identical.
The [complete audit](2026-10-25-sandbox-help-namespace.json) includes actual file
hashes and all retained Markdown contexts.

All 174 maintained Markdown files, including both Skills, were checked. The ten
remaining upstream-import statements are explicitly previous-import columns in
EN/ZH migration tables (eight) or labeled third-party product comparison rows
(two). They remain correct and unchanged. The older engineering note's quoted
bug description is evidence, not a live tutorial. Historical merged receipts,
design/decision history and upstream provenance are not mechanically rewritten.

## Commands and results

```bash
python -m pytest client-sdk/tests/test_api/test_template_help.py client-sdk/tests/test_api/test_standard_contract.py client-sdk/tests/test_api/test_provider_docstrings.py -q --no-cov
make lint format-check typecheck
make build dist-check
bash scripts/check-repo-health.sh
make hygiene
```

Before correction: four new class-import failures plus exhaustive source audit
failure, with all previous 24 Template cases passing. After correction: 54 focused
PASS, including all 28 real help imports, exhaustive source audit, existing
standard contract checks and 12 Provider docstrings. No cloud build is invoked
by these tests. Both-package ruff/format/mypy passed. Full package outcomes and paired builds
are recorded below, including the actual local server failures.

Full client: 2318 PASS, 26 skipped (127.41s). Both wheel/sdist pairs built; twine,
both py.typed markers and fresh combined installation passed. Installed candidate
wheels passed all 28 real help imports, all 390 source files / 2358 docstrings with
zero upstream import residue, 12 Provider docstrings and pip check. Real local
HTTP health, shell/file roundtrip and independent owned-process absence passed:
[candidate HTTP](2026-10-25-sandbox-help-candidate-http.json). The exhaustive unit
guard asserts both source roots exist and each scan is nonempty, without a fixed
file-count assumption. Health: 106 PASS, one existing runbook WARN, zero FAIL;
hygiene passed.

The local server full suite returned nonzero: 878 PASS / two FAIL (314.43s).
`test_upgrade_without_a_key_is_a_400_not_a_hang` returned 501 rather than 400;
`test_transfer_encoding_rejected_in_policy_mode` returned 502 rather than 400.
These same low-level assertions also failed in earlier a4/a5 local runs. They
remain failures, with no test or gate weakened; the required exact-head remote
matrix must independently pass. No unverified root cause is asserted.

## Preserved publication and real-component scopes

Public a5 publisher run [40222172993](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40222172993)
succeeded on attempt1. Original artifact12610066901 contained four files matching
official metadata and actual download bytes. Fresh official non-all a5 installed
matching server5; pip check, standard/Provider/server imports, 24 Template help
imports, 12 Provider docstrings, reviewed source bytes and real local HTTP/files/
owned-process absence passed. This established that exact scope, not all public
help: the later four-class negative observation is preserved separately above.
[Preserved scoped a5 delivery](2026-10-25-public-a5-scoped-delivery.json) contains
its actual four hashes, package installation, help subset and HTTP receipt.

The [public-a4 examples](2026-10-25-public-a4-examples.md) remain 14 actual cloud
examples with 29 typed-not-found checks and the separate 10-check local runner.
They are not a5/a6 cloud evidence. Original browser failure remains unchanged.

## Cleanup and outstanding gates

Help regressions create no cloud resources. Candidate installed-wheel HTTP and
owned-process checks passed as recorded above. Required current-head CI,
independent review, normal merge, immutable a6 tag and official publisher/readback
remain pending. Maintained installation guidance still selects public a4 until
a6 publication is verified; no unpublished package recommendation is introduced.
