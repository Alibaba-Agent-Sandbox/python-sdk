# Verification: server command loader

- Date: 2026-10-16
- Change: [SDK issue 30](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/30)
- Result: PARTIAL
- Package under test: agent-sandbox-server 0.3.0, editable from this checkout
- Environment: Linux, Python 3.13.13. No credentials were read by the loader checks.

## What was verified

The command-file loader now exposes its module to dataclass decorators during
execution, imports each canonical file once and cleans up module/search-path state
when execution fails. The companion template agent reproduced the original failure
through the actual CLI, then successfully ran that same startup route after this
fix and exercised the resulting HTTP service. This local runtime verification does
not establish real-cloud template deployment or authenticated model execution.

## Commands run

Commands below use the existing development environment's tools on `PATH`.
The selected CLI tests deliberately exclude the healthcheck test, which is not
part of this fix. Previously denied raw-HTTP suite paths were not retried.

```bash
cd server-sdk
pytest tests/test_server/test_cli_main.py -k 'load_commands or policy_modules' -q
pytest tests/test_server/test_cli_main.py -k 'not healthcheck' -q
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/agent_sandbox/server/
mypy src/agent_sandbox/server/__main__.py
cd ..
make lint format-check
bash scripts/check-repo-health.sh --quiet
make hygiene
```

The companion template agent additionally ran `python -m agent_sandbox.server
serve --port 19053 --commands <template-directory>/commands.py`, using the actual
`codex-agent-api` command file. From the workspace root, it ran
`E2E_BASE_URL=http://127.0.0.1:19053 python awesome-templates/codex-agent-api/e2e_test.py`
against that localhost server.

## Results

| Scenario / test | Result | Notes |
|---|---|---|
| Original real CLI startup, before fix | FAIL | Postponed dataclass annotations caused `AttributeError: 'NoneType' object has no attribute '__dict__'` in the standard-library dataclass module |
| Command-loader and stdlib dependency regressions | PASS | 7 tests |
| CLI tests excluding unrelated healthcheck | PASS | 12 passed, 1 deselected |
| Whole-repository lint and formatting | PASS | Both packages; formatting checked 91 server and 195 client files |
| Repository health | FAIL | 105 passes, 1 warning, 1 pre-existing English/Chinese archive-page mismatch |
| Repository hygiene | PASS | No local paths or credential-like strings found |
| Changed CLI module mypy | PASS | 1 source file |
| Complete server mypy | FAIL | Existing `routes_browser.py:75`: unused `type: ignore` comment, `[unused-ignore]`; that file was not modified |
| Companion template real CLI startup | PASS | The actual dataclass-containing `commands.py` loaded and served HTTP |
| Companion template real HTTP checks | PASS | Agent reported 18 checks; session CRUD, input rejection and secret-artifact rejection covered |
| Authenticated model execution | SKIP | Companion template L3 explicitly skipped; not counted as a pass |

## Cleanup

Unit tests use pytest temporary files and restore generated module entries and
`sys.path`. No cloud resources were created by these checks. No credential files,
permission configuration or system environment configuration were changed.
The companion template agent stopped its real HTTP server after validation
(`Ctrl-C`, process exit 130); no test server remained.

## Problems found

The required complete gate remains blocked. The previous full server run had
843 passes, 7 failures and 1 skip; its raw-HTTP failures include a platform
`HTTP/1.1 501 Not Implemented` denial with body `项目网络审计已关闭`.
Those denied paths were not retried or bypassed. Details and the independently
passing complete client suite are recorded in
[the workspace-source verification](2026-10-16-uv-workspace-source.md).
The optional Playwright dependency is now present in the shared environment,
making its existing import-ignore annotation unused under mypy.

## Not verified

Real-cloud E2E for this fix, a container image build (Docker is unavailable), and
authenticated agent execution remain unverified. The full definition of done is
open; focused tests and successful local HTTP startup are not reported as cloud
verification.
