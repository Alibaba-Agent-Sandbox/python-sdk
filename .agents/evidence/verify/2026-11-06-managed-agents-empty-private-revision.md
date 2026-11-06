# Verification: reject empty private control revision

- Date: 2026-11-06
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/156; https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/155.
- Result: PARTIAL — new real HTTP/SQLite/PostgreSQL regressions pass; full current-head CI and final public-package acceptance remain in progress.
- Environment: isolated CPython 3.12.13 environment, Linux PID namespace, SQLite and real local PostgreSQL 16.2 (`pgserver` 0.1.4). No cloud resource or management Key is created by these regressions.

## Problem and review

The private Dispatcher accepted `revision: ""`. Its drain branch treated that value as a global
admission fence, while closing and status filtered it as a specific revision. A caller could
therefore receive zero scoped counts while existing logical Sessions remained open.

Independent runtime and CLI review established that normal deployment controllers omit the field
for global control and use frozen nonempty revisions for retirement. The currently running cloud
source candidate `cd43e9e40ef5c90212b8ea6a1cc293c10f71ad2e` does not exercise this invalid input.
The defect does not reclassify that candidate's valid-input results. It is corrected before the
first public 0.4.0a7 package so trusted custom controllers cannot encounter this ambiguity.

## Change and commands

Only the existing Dispatcher input-bounds predicate changes: an explicitly empty string receives
HTTP 400 `invalid_invocation` before any status, transaction, admission fence, close or dispatch
branch. Omitted/None and all previously accepted nonempty strings retain their behavior; there
is no new revision normalization, character policy or control mode.

```bash
python -m pytest client-sdk/tests/test_managed_agents.py -k empty_private_revision -q --tb=short
python -m pytest client-sdk/tests/test_managed_agents.py -k 'empty_private_revision or private_fc_octet_stream or drain_counts' -q --tb=short
make ci
```

The controller executes these commands with its dedicated development environment and PID
namespace. Exact workstation paths and raw private inputs are not repository documentation.

| Check | Actual result | Meaning |
| --- | --- | --- |
| New regressions before the code correction | FAIL: 4 failed, 48 deselected, 11.07 s | Signed real HTTP empty-revision status/drain each return 200 under SQLite and PostgreSQL, rather than the required 400. The original failure log is retained. |
| New cases plus existing media/global-drain controls after correction | PASS: 9 passed, 43 deselected, 10.34 s | Both databases reject the empty revision. Full control/object/event/idempotency/meta snapshots remain equal, active count remains one and global draining remains false. A nonempty scoped status and omitted-revision global drain still work. |
| Scoped Ruff | PASS | The runtime and regression file pass the existing rule set. |
| Complete local `make ci` | RUNNING | Both packages, types, lint, format, distribution builds and install checks are executing. |
| Latest-head remote CI/distribution | NOT YET VERIFIED | The final independent commit and immutable artifact identity will be recorded after they exist. |

The tests use a blank logical Session. They intentionally prove validation and global-drain
semantics without creating a provider Sandbox or making a model request. They do not claim a new
active-cancellation or complete cloud/model/business result.

## Cleanup and delivery boundary

Every test HTTP server closes its socket and joins its thread in `finally`. The component fixture
removes its owned temporary PostgreSQL server/data directory; the local SQLite directory belongs
to the test's temporary directory. The fixture's provider create counter stays zero. None of the
controller's live cloud applications, databases, receipts, images or original CI wheels is changed.

The previous runtime and CI distribution remain historical source evidence. This continuation
requires a newly frozen CI wheel, normal publication/readback and final public-recipe acceptance;
the old source-only cloud run cannot be relabeled as having used the new package. The ADR remains
proposed pending the complete delivery criteria.
