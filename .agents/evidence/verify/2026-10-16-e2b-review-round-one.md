# Verification: E2B behavior review, first full run

- Date: 2026-10-16
- Change: proposed architecture ADR `2026-10-16-e2b-behavior-contract`
- Result: PARTIAL
- Revision: uncommitted scoped implementation on `feat/e2b-behavior-20261016`; not a published release
- Environment: Linux x64, Python 3.13.13, Node 22.22.2. Credentials supplied from ignored environment configuration; values omitted.

## What was verified

This first review found contract regressions and obsolete assumptions after canonical configuration and standard API changes. The task is not complete; subsequent fixes require a new verification record.

## Commands run

- `make test`: FAIL; server 852 passed / 8 failed; make stopped before client.
- `pytest tests/ -q --tb=short` in client-sdk: FAIL; 1980 passed / 8 failed / 21 skipped.
- `make lint`: PASS.
- `make typecheck`: initially FAIL in MCP lifetime bookkeeping; fixed and subsequent run PASS (server 56 files, maintained client 84 files; ported/generated sources excluded).
- Targeted client transport/packaging/standard regression run after fixes: PASS, 256 tests.
- Real cloud `pytest e2e/test_standard_contract.py`: network update scenario PASS (allow, deny all, restore access). Sync/async scenarios exposed test assumptions about query models, metadata index consistency and backend interpreter error names; fixes and reruns in progress. Snapshot skipped because no MicroVM/allowlist fixture was configured.

## Results

The new sync API reached the real cloud and verified lifecycle, file text/bytes/WriteInfo, nonzero-command exceptions, background stdin and interpreter state/callbacks. A later test assertion failed, so the complete sync scenario is not recorded as passing. Async create/connect/files/commands passed before pagination indexing assertion. No mock result is counted as cloud completion.

## Cleanup

Every created standard sandbox used try/finally kill plus the E2E tracker finalizer. Cleanup results must also be captured in the final successful run. Do not infer a global account cleanup from individual kill calls.

## Problems found

Retired-name tests still rejected canonical E2B_* variables. Packaging incorrectly prohibited Rich, now required by the Template API. Full server failures included raw-loopback requests receiving a managed network audit response, ambient server-policy assumptions and a test venv initially lacking pip. These are not counted as passes or silently excluded.

## Not verified

Complete CI matrix, all cloud conditional capabilities, final package/hygiene/health checks, required remote review, PR merge and package publication. This record does not close the Issue or mark the proposed ADR implemented.
