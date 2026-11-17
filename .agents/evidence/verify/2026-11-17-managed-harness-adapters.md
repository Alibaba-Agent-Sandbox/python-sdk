# Verification: managed harness adapters

- Date: 2026-11-17
- Change: managed-harness-adapters proposal; client/server a8 candidate source.
- Result: PARTIAL
- Environment: Linux, CPython 3.12.13; initial native probes used Node 22.22.2.

## What was verified

Native invocation/session IDs, terminal outcome parsing and exact per-harness credential
names, plus standalone-server/client descriptor parity. The official DSH package is used.

## Commands run

- Server: `pytest -q tests/test_server/test_harness_adapters.py`: 15 passed.
- Client: `pytest -q tests/test_managed_harness.py`: 13 passed.
- Server: `mypy src/agent_sandbox/server --follow-imports=silent`: 61 files passed.
- Scoped `ruff check` and `ruff format`: passed after correcting import order and explicit zip behavior.
- Installed `@qoder-ai/qodercli@1.1.90`, `opencode-ai@1.19.5`, `@deepseek-ai/dsh@0.2.2-rc.1`
  into an isolated npm prefix. Optional package install scripts were not required for initial probes.
- Real `qoder --version`, `opencode --version`, `dsh --version`: exact versions matched.
- Real Qoder/OpenCode/DSH headless help: passed; Qoder lacks max-turns and plan permission
  flags in this exact version, so the implementation follows actual help.
- Real Qoder headless without credentials: exit 1, authentication required. No model called.
- Reinstalled both editable distributions without dependency changes after lockstep a8 metadata update.

## Results

| Scope | Result | Limit |
| --- | --- | --- |
| Native parser/invocation/credential unit cases | PASS | Fixtures are logic evidence, not model execution |
| Three native package versions/help | PASS | DSH full runtime requires supported Node >=24.9 |
| Qoder missing-authentication failure | PASS | Native PAT execution not verified |
| Full owner checks and post-change reviews | Pending | Recorded separately after execution |
| Real six-harness model/FC/PostgreSQL/upgrade acceptance | BLOCKED | Not established by these local probes |

An initial combined-root pytest invocation failed with package conftest name collision;
the suites were rerun from their owning package directories. An initial direct-file mypy
invocation found the package under two module names; the owning-package command passed.

## Cleanup

No cloud resources created by these checks. Native probes use isolated temporary homes;
their outputs contain no credentials. Installation packages are local verification tools.

## Not verified

No claim of all providers/models, native account permission, successful model task, hosted
upgrade or released a8 is made. Required real-component gates remain explicit.

## Final local validation checkpoint

The first full `make test` server run finished with 887 passed, 1 skipped and 7 failed.
Four failures were expected runtime-directory snapshots still listing five adapters;
the new three entries require explicit eight-entry expectations while the independent
local API's supported-runtime restrictions stay unchanged. One failure was an incomplete
verification environment: uv's venv had no pip, so the package-listing endpoint returned
no pytest package. Installing pip in the verification venv resolved that prerequisite.
Two failures were malformed raw HTTP probes receiving 501/502 instead of the required 400.

Executed full `make ci` after those corrections. Its server checkpoint finished with
**892 passed, 1 skipped, 3 failed** and exit 2. Two failures remained the raw HTTP cases
above. The third was one additional old five-entry default-adapter expectation, corrected
after that full run had imported its test module. The final source was then checked with
`pytest -q tests/test_server/test_harness_adapters.py
tests/test_server/test_routes_agents.py::TestRoutesAgents::test_aliases_unknown_adapter_and_default`:
**22 passed** (including the new permissions and completion-only-tool regressions).
This targeted result does not turn the earlier full-suite checkpoint into a full pass
on the final tree. A previous five-case runtime-directory/pip check separately passed
the other corrected expectations; the broader server run no longer failed them.

The independently executed full client suite finished with **2657 passed, 27 skipped,
8 failed**, exit 1. Failures were four private FC-role octet-stream requests timing out,
one partial-body timeout and three raw HTTP SSE probes receiving 501. The owner retains
the failed assertions and a [project-independent stdlib HTTP control](2026-11-17-raw-http-environment.md)
showing the same raw 501/header-only timeout behavior without importing this project.
These environmental observations do not constitute passing product assertions.

Remaining local gates were executed separately because `make ci` stops at its first failure:

- Final `make lint`, `make format-check`, `make typecheck`: both packages PASS;
  server 99 formatted files/61 typechecked files, client 267 formatted files/118 typechecked files.
- `make build`: PASS for both a8 wheels and sdists.
- `make dist-check`: PASS, including four twine checks, typed markers, fresh client-only
  import/real HTTP, optional-server command registration, combined wheel installation and pip check.
- `bash scripts/check-repo-health.sh`: 106 PASS, 1 existing recommended-release-guide warning,
  0 FAIL. `make hygiene`: PASS. New evidence helper also passes scoped Ruff checks/formatting.
- [Installed OpenCode/DSH two-turn continuation and the failed real-model preflight](2026-11-17-native-harness-components.md)
  are recorded independently from these suites.

No full local CI pass, cloud/model acceptance, PyPI release or image publication is claimed.
