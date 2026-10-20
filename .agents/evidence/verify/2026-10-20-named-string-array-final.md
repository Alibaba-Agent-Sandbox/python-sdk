# Verification: native string-array final runtime

- Date:2026-10-20
- Result:PASS
- Runtime source:fd72d3210b85079d93dcf08e19bfded73643162b, both packages0.3.0.
- Scope: named string-array behavior and the six native E2E prerequisite repairs.

## What was verified

Exact native JSON arrays work through the real Express Python client and native
CLI0.3.0. The test uploads and SHA256-checks this checkout's server source into
fresh tracked sandboxes. Spaces/Unicode/literal shell metacharacters remain array
elements; mixed types/null/JSON strings fail400. Default arrays are copied per
call. Python3.10implicit Optional widening is corrected consistently in both
registrations and invalid None defaults are rejected on every supported version.

## Commands and results

`make e2e`:121PASS/8SKIP/2deselected/1known platform XFAIL,246.51seconds.
The skipped catalog providers and opt-in Volume/pause/snapshot are not certified;
KI-009remains the actual Jupyter-unavailable platform xfail. See
[full results and runtime hashes](2026-10-20-named-string-array-final-cloud.json).

All10[remote runtime checks](2026-10-20-named-string-array-runtime-ci.json) PASS:
client/server Python3.10/3.11/3.12lint/format/type/unit matrix, built distributions,
pinned public E2B contract, hygiene and Markdown links. These run the unrelaxed
raw HTTP tests on real CI hosts. Local lint/typecheck/hygiene, distribution checks,
repository health and focused server15/client12array cases pass. An actual isolated
Python3.10.20[before/after proof](2026-10-20-string-array-python310.json) independently
reproduces the initial new regression and verifies its correction.

## Cleanup

`python scripts/e2e-cleanup.py --all-tagged` ran as a dry-run:0candidates.
The independent[own-run readback](2026-10-20-named-string-array-cleanup.json) found
0remaining sandboxes. Every created resource was tracked and finalized; no
other actor's sandbox was deleted.

## Problems and limitations

The original6cloud failures, Python3.10CI failure and local501/502boundary behavior
remain in the[initial verification](2026-10-20-named-string-array.md) and its linked
immutable reports. The independent authored service proves local raw HTTP response
changes without importing the SDK; no assertion was weakened to accept them.
The complete remote matrix passes those cases. Skips and the known xfail remain
explicit. The final record/state-only commit must pass its own latest-head CI
before the PR becomes ready and merges; no merge is asserted here.
