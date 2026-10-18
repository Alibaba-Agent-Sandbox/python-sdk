# Verification: Explicit provider routing through the native engine

- Date: 2026-10-18
- Change: follow-up to commit `6149076`, PR #38 and Issue #52; ADR `2026-10-18-provider-portability-updates`.
- Result: PARTIAL — client regression and real cloud pass; the previously recorded server aggregate remains blocking.
- Environment: Python 3.13.13, Linux, source client/server 0.3.0, real Express cn-hangzhou. Credentials were supplied through an ignored environment file; no values are recorded.

## What was verified

The Express adapter now forwards its selected provider into its internal engine-create
call. An unrelated ambient default cannot redirect an explicitly selected native create.
The core remains provider-neutral; the fix is entirely in the owning lifecycle adapter.

## Commands run

```sh
cd client-sdk
pytest tests/test_providers/test_complete_isolation.py -k native_engine -q
ruff check src/ tests/ --output-format concise
ruff format --check src/ tests/
mypy src/agent_sandbox
pytest tests/ -q --tb=short
cd ..
make build dist-check
bash scripts/check-repo-health.sh
bash scripts/check-no-local-paths.sh
```

A task-local real-component runner set `ABX_PROVIDER=not-installed-provider`, explicitly
created and listed with `provider="alicloud-express"`, executed a command, round-tripped
a file, connected/disconnected a borrowed client and deleted its owned sandbox.
It emitted assertion names/results only, never provider payloads or credentials.

## Results

| Check | Result | Notes |
| --- | --- | --- |
| Negative control before fix | Expected failure | The new regression observed no forwarded provider; one failed, four deselected; no cloud request |
| Complete client suite after fix | PASS | **2152 passed, 24 skipped**, 147.71 seconds |
| Client lint/format/mypy | PASS | 228 formatted files; 107 source modules typechecked |
| Rebuilt distributions | PASS | Both wheels/sdists, twine, py.typed and clean combined installation/import |
| Repository health/hygiene | PASS | 106 health checks passed; one historical warning; no hygiene failures |
| Explicit native create over invalid ambient default | PASS | Real Express sandbox created through the selected provider |
| Exec/files/connect/list | PASS | All four real-component assertions passed |
| Owned cleanup | PASS | Delete completed and a subsequent explicit-provider list confirmed absence |

## Cleanup

Only the newly created sandbox was deleted. No Team, managed API-key, role, Bucket,
Volume or template management resources were created by this follow-up.

## Problems found

The regression exposed a missing provider argument in the Express wrapper. The fix
preserves the explicit selection rather than modifying the ambient environment or
adding a vendor branch to core. Changelog entries now use the standard Changed/Fixed
groups and describe only Python-owned behavior.

## Not verified

The prior [isolation evidence](2026-10-18-provider-complete-isolation.md) remains historical.
Its seven server aggregate failures are not waived, and unchanged server tests were not
repeated for this client-only follow-up. The full supported Python-version remote matrix
is unverified. The PR remains a draft and is not merged.
