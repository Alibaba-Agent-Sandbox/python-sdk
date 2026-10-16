# Verification: MCP external metadata and timeout avoid connect/resume

- Date: 2026-10-16
- Change: follow-up to `bb7881dc703ccdc3b97ff5ad67bcb129c4ea80ea`, SDK issue 31.
- Result: PARTIAL — scoped tests and real Express workflow pass; existing server
  typecheck/test and repository documentation gates remain blocking.
- Package: local editable client/server 0.3.0; Python 3.13.13 on Linux.
- Credentials: authorized environment configuration only; no secret values,
  raw provider payloads or sandbox IDs are recorded.

## Problem and correction

Independent CLI cross-review found that external metadata/TTL operations used
`Sandbox.connect`. Catalog E2B/Cube connect adapters invoke resume routes, so
inspection could wake a paused instance. Earlier Express acceptance did not
exercise that provider behavior and cannot establish cross-provider acceptance.

`Sandbox.get_info_by_id` and `Sandbox.set_timeout_by_id` now select the provider
and dispatch directly to its `get_info` / `set_timeout` protocol methods. Temporary
control-plane infrastructure closes in `finally` after success or failure.
MCP external-ID operations use these APIs, never connect/create/resume, and never
adopt external resources for session shutdown. Managed TTL completion after
shutdown also cannot restore renewal state. Sync variants follow the existing
classmethod bridge convention.

## Commands and actual results

| Command / scope | Result |
| --- | --- |
| Focused MCP lifecycle and direct control-plane tests | PASS: 84 tests including shutdown race, built-in/provider failures and actual sync aliases |
| Both-package `make lint format-check` | PASS |
| Client `mypy src/agent_sandbox` from client directory | PASS: 83 source files |
| `make typecheck` | FAIL: existing server `routes_browser.py` unused-ignore; client checked separately |
| `pytest e2e/test_09_mcp_lifecycle.py -q --tb=short` | PASS: 2 real Express tests in 13.51 seconds |
| Full client suite | PASS: first run 1973 passed, 21 skipped; final race-inclusive run is captured below |
| `make build dist-check` | PASS: both wheel/sdist pairs, twine, py.typed, combined isolated install/import |

An initial mypy invocation from the repository root did not load the client
package configuration and reported 27 errors. That invocation is not the client
CI gate; the correctly scoped command passed. A newly introduced cast spelling
was corrected to satisfy Ruff; final lint/format results are shown above.

## Behavioral evidence

Provider protocol spies model paused metadata and a connect method that raises
if called. Direct get and timeout succeed without reaching connect/create/kill;
provider operation failures still close infrastructure. Built-in control-plane
regressions likewise assert direct dispatch and HTTP cleanup. These regressions
exercise actual SDK dispatch, rather than mocking the new classmethod boundary.

The real Express tests exercise CPU/memory creation, safe metadata refresh,
external inspection and renewal, observer shutdown preserving the owned sandbox,
managed timeout policy, files, commands and eventually consistent list visibility.
Only list visibility retries; creation is never retried.

## Cleanup

E2E uses the existing owned-resource tracker and manager `finally` shutdown.
Every created sandbox is cleaned up on assertion failure. Arbitrary account
instances and existing templates are not deleted. The separate CLI counterpart
also reran 14 real STDIO checks, including owned-ID destruction and readonly
absence confirmation; that evidence belongs to the CLI repository.

## Not verified

The original full server run remains 843 passed, seven failed, one skipped,
including a platform HTTP 501 denial. Denied paths were not retried or bypassed.
Existing server typecheck and documentation-health failures remain unresolved.
No E2B/Cube cloud run, Docker build, new-template deployment or IDE acceptance is
claimed. Provider spies establish no connect side effect in the host dispatch;
they do not establish external cloud/provider acceptance. PR 33 stays draft.

## References

- [Issue 31 cross-review follow-up](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/31#issuecomment-6206718953)
- [PR 33](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/33)

## Additional review validation

Both built-in and provider success/failure cases close temporary infrastructure.
Actual sync classmethod calls exercise dispatch and cleanup, rather than checking
only that aliases exist. The compatibility `sandbox_domain` argument is explicitly
documented as unused by control-plane-only APIs. The new race regression first
failed because the guard was placed in creation rather than TTL completion; it
was moved to the correct completion point and the focused rerun passed.

## Final results

- Race-inclusive complete client suite: **1974 passed, 21 skipped**, 261.04 seconds.
- Additional focused run with sync-alias and built-in failure cases: **84 passed**.
  Six of those additional tests were added after full-suite collection; they were
  executed separately against the same runtime code. Skips are not acceptance.
- Both-package lint, format and repository hygiene: PASS.
- Correctly scoped client mypy: PASS, 83 source files.
- Both distributions: build/dist-check PASS, including twine, type markers and
  combined isolated installation/imports.
- Repository health: 105 PASS, one warning, one existing EN-only archive mismatch.
- Server typecheck: existing optional-browser unused-ignore remains blocking.
- Configured-secret scan and `git diff --check`: PASS for this task's patch.

This verification was captured before draft delivery. Draft PR publication does
not resolve the server or repository-wide gates; no merge is implied.
