# Verification: Application runtime main integration

- Date: 2026-10-20
- Change: merge current main into the feature branch for https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/75
- Owner issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/74
- Result: PARTIAL; conflicts resolved and application regressions pass, provider-engine integration remains failing
- Feature parent: `d9a7676b2ea537e61eef21dd8aecc0463e7bb829`
- Main parent: `e166e411e7724f54f126af058de29bb978e4e677`
- Environment: Linux, CPython 3.11.15, existing isolated verification environment; no credential values recorded

## What was verified

Fetched public main before merging. The only conflicts were the final documentation
links in `README.md` and `README.zh-CN.md`. Both the application runtime guide and
the incoming provider command guide remain linked. The changelog retains both
changes. Incoming Provider ownership instructions, acceptance tests, engineering
records and bilingual guides were preserved. Application runtime source is
unchanged from the feature parent.

## Commands run

```bash
git -c core.filemode=false fetch origin main
git -c core.filemode=false merge --no-commit origin/main
git diff --cached --check
pytest client-sdk/tests/test_applications client-sdk/tests/test_providers/test_commands_engine.py -q
ABX_COMMAND_TEST_BIN='node ../cli/dist/bin/abx.js' pytest client-sdk/tests/test_providers/test_commands_engine.py -q --tb=short
make lint typecheck format-check
bash scripts/check-repo-health.sh --quiet
bash .githooks/check-secrets.sh
```

The built CLI command was supplied with its resolved checkout path during the run;
the portable relative command above identifies the same entrypoint without
recording a machine-local path.

## Results

| Scenario / test | Result | Notes |
| --- | --- | --- |
| Application regressions | PASS | 26 passed in 11.23 seconds, including local subprocess HTTP and real local PostgreSQL |
| Provider command tests without explicit binary | SKIPPED | 2 skipped because `ABX_COMMAND_TEST_BIN` was unset; not counted as passes |
| Provider command tests with actual built CLI | FAIL | 2 failed in 60.98 seconds, both E8020 provider-engine startup timeouts |
| Lint | PASS | Both client and server packages |
| Strict typecheck | PASS | 56 server and 116 client modules |
| Format check | PASS | 91 server and 245 client files |
| Repository health | PASS | 107 passes, zero failures; one existing missing release-guide warning |
| Merge whitespace/conflict check | PASS | No conflict markers or whitespace errors remain |

## Cleanup

The merge and validation created no cloud resources. Local application subprocess
and PostgreSQL tests use their existing finalizers. No remote application was
deployed, and the Draft PR was not merged.

## Problems found

The explicit Provider command run still cannot start the companion engine in this
environment. This is the same E8020 startup category recorded during the original
feature verification. This run does not establish a successful incoming Provider
integration and does not relabel the failed checks as passes. The two README
conflicts are resolved without dropping either repository change.

## Not verified

Full FC application deployment, cloud database binding and real LLM execution
remain blocked as recorded in the
[original feature evidence](2026-10-20-agent-application-runtime.md).
The prior real remote-sandbox E2E was not repeated for this documentation-only
conflict resolution; runtime code is unchanged. Remote CI and review remain
required before this Draft PR can merge.
