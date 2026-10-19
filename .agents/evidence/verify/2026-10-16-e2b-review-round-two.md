# Verification: E2B behavior review, second run

- Date: 2026-10-16
- Change: proposed architecture ADR `2026-10-16-e2b-behavior-contract`; https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/36
- Result: PARTIAL
- Package under test: editable client/server from this branch, Python 3.13.13, Linux x64. Separate reference environment contains e2b 2.31.0 and e2b-code-interpreter 2.8.1.
- Credentials: supplied through ignored environment configuration; values omitted.

## What was verified

The root synchronous and asynchronous clients, interpreter namespace, lazy pagination, command exceptions/handles, canonical configuration, network updates and snapshot request shapes were reviewed against the pinned reference. The implementation owns an attributed source port and has no E2B runtime dependency. Node SDK changes are excluded.

## Commands run

- `python -m pytest client-sdk/tests -q`: 1991 passed, 21 skipped (157.93 seconds), before the last two snapshot-state assertions.
- `python -m pytest client-sdk/tests/test_api/test_standard_contract.py client-sdk/tests/test_providers/test_epp.py -q`: 47 passed (26.43 seconds), including final snapshot/state and placeholder-redaction fixtures.
- `python scripts/check_standard_contract.py --reference-python <reference-python>`: 354 public callable signatures and sync/async shapes match. Only the documented optional Alibaba snapshot-name keyword is allowed beyond the reference.
- `python -m pytest e2e/test_standard_contract.py -ra`: 3 passed, 1 skipped (24.75 seconds).
- `make lint typecheck format-check`, `make build dist-check`, `make hygiene`: PASS. Narrow ported/generated source exclusions are recorded in configuration; maintained adapters are checked.
- Built wheels installed into a clean environment; standard clients, shared server namespace, py.typed, both MIT licenses, SOURCES.json and PATCHES.md checked: PASS.
- `make test`: server gate FAIL, 7 failed / 853 passed / 1 error (320.10 seconds). It stops before the client target. This is not a full-suite pass.
- `bash scripts/check-repo-health.sh`: 106 PASS / 1 WARN / 0 FAIL before restoring historical archives. Parent branch now contains the full missing Chinese archive translation; integration and final health rerun remain.

## Results

| Scenario | Result | Details |
|---|---|---|
| Standard synchronous cloud lifecycle | PASS | Create/get_info/list/timeout, text and bytes, WriteInfo, command exit 7 with captured output, background stdin/wait, kill and repeated kill |
| Standard async cloud lifecycle | PASS | Create/connect/files/commands and lazy metadata pagination |
| Interpreter cloud contexts | PASS | Persistent state, callbacks, results/errors, restart/list/remove contexts |
| Runtime network policy | PASS | Public request succeeds, deny-all blocks it, restored allow rule succeeds |
| Snapshot request contracts | PASS | Name filter in sync/async paginators, qualified deletion paths, snapshotting states |
| Snapshot cloud restore | SKIP | No configured MicroVM template with the snapshot allowlist (`E2E_SNAPSHOT_TEMPLATE`) |
| Conditional pause/resume and full cloud capability matrix | NOT VERIFIED | Requires appropriate runtime/account fixtures; no claim inferred from a preserved method |

## Cleanup

The cloud tracker reported `sandboxes_tracked=3 leaked_after_cleanup=0`. Every test uses try/finally kill. Listing/index assertions retry only declared eventual consistency. This evidence does not claim deletion of unrelated account resources.

## Problems found

Fixed the interpreter error-name assumption and metadata-index timing in the initial test harness. The server gate receives managed-network HTTP audit responses on raw loopback tests and has an ambient server-policy assumption plus a bind error; server runtime source was not changed by this feature. The initial missing-pip environment problem was corrected before the reported server run. These failures remain failed, not excluded.

## Not verified

Final integration onto the updated parent https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/33, complete required CI matrix/review, all conditional cloud fixtures, release publication. This record does not close the Issue, accept the ADR or authorize a failing merge. The companion CLI work is tracked at https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/33.
