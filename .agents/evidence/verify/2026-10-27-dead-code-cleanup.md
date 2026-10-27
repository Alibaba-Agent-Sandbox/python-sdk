# Verification: Scoped unused-code cleanup

- Date: 2026-10-27
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/146
- Base revision: `259cc1ef9b154346bb8d5de0689b4b624d97baff`
- Functional patch SHA256: `4eec7a76ae4dac0d950d18451b75276046622295daa021cb294df8ae02a74d47` (Git binary diff against the base, excluding records/docs/changelog).
- Result: BLOCKED
- Environment: Linux; Node 22.22.2, TypeScript 5.9.3, ESLint 10.12.0; final Python checks use system Python 3.13.13; Ruff 0.17.3.

## What was verified

The scoped deletion preserves observable behavior, public contracts, generator ownership and historical evidence. Work is isolated from pre-existing workspace edits. Scope is the functional patch above plus its bilingual documentation, changelog where applicable, decision and evidence; current-head CI will bind verification to the pushed commit.

## Commands and results

| Command / check | Result | Evidence |
| --- | --- | --- |
| Ruff lint and format checks, both packages | PASS | Isolated development environment. |
| Mypy, both packages | PASS | Client: 101 source files; server completed before its test step. |
| Client `pytest tests/ -m "not integration"` | PASS | 2,345 passed, 26 skipped, 10 deselected. |
| Server `pytest tests/ -m "not integration"` | FAIL locally | 878 passed, 2 raw HTTP transport tests failed. |
| `make ci` | PARTIAL / exit 2 | Stopped at the two server tests; client and distribution steps were executed separately. |
| `make build && make dist-check` | PASS | Both wheels/sdists, twine, py.typed and clean combined installation/imports. |
| `bash scripts/check-repo-health.sh` | PASS | 106 pass, 1 warning, 0 failures before final evidence update. |
| Existing-key service listing | PASS | Read-only CLI preflight against the existing configured service. |
| `make e2e` | IN PROGRESS | Existing service key only; AK/SK not supplied. |

The failing server cases are `test_upgrade_without_a_key_is_a_400_not_a_hang` (501 instead of 400) and `test_transfer_encoding_rejected_in_policy_mode` (502 instead of 400). An independent HTTPServer negative control always sends 400: malformed WebSocket traffic is intercepted before reaching that handler and returns 501; chunked POST reaches the handler but the observed response becomes 502. An ordinary explicit-port request reaches it and returns 400. This isolates local forwarding behavior from the unchanged server implementation. Remote CI must validate the original tests on normal networking; no security assertion was weakened.

Initial environment attempts are not passes: the downloaded Python 3.12 lacks memfd/pidfd support used by process tests; a shared template environment installs Playwright and makes a strict unused-import-ignore check fail. Final SDK checks use a separate system Python 3.13 environment without Playwright.

## Scope and further analysis

Only private `_a()` is removed from runtime source. Public aliases/exports, generated schema, package versions and server source are unchanged. Example-import findings were already resolved upstream. Compatibility parameters and async-generator `yield` statements remain. `_cleanup_browser` needs a lifecycle-specific teardown analysis and regression before any removal; no resource leak is asserted from a definition-only result.

## Cleanup and remaining gates

Cloud acceptance is running with unique test ownership. No cleanup success is claimed at this checkpoint. Required current-head remote Python matrix, reviews and complete real-cloud results remain pending. The PR stays draft while these gates are unmet.
