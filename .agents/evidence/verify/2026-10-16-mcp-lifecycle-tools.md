# Verification: Python MCP lifecycle tools

- Date: 2026-10-16
- Change: SDK issue 31; lifecycle ADR in proposed/feature
- Result: PARTIAL
- Package under test: local editable agent-sandbox-client/server 0.3.0
- Environment: Linux, Python 3.13.13, Alibaba Cloud Express existing base template.
  Authorized configuration supplied through environment; no values recorded.

## What was verified

The Python MCP handlers create, inspect, list, renew, execute, read/write and destroy
real Express instances. Inspection/renewal through a separate manager does not
adopt the instance, and observer shutdown preserves it. Metadata is allowlisted;
new lifecycle errors and logs omit raw exception messages, query URLs, validation
inputs and dynamic SDK suggestions. This is the Python lifecycle subset, not the
complete MCP/Skills roadmap or an IDE deployment acceptance result.

## Commands run

```bash
cd client-sdk
pytest tests/test_agent -q
pytest tests -q
cd ..
pytest e2e/test_09_mcp_lifecycle.py -q --tb=short
make lint format-check hygiene
```

The real-cloud invocation inherited the authorized environment and used a unique
per-process in-process engine socket. No credential files or permission settings
were changed. Cross-review also ran client mypy and complete make typecheck.

## Results

| Scenario / test | Result | Notes |
|---|---|---|
| Agent/MCP unit and transport coverage | PASS | 194 tests; includes 33 error/log privacy regressions |
| Real Express MCP E2E | PASS | 2 tests, 13.71 seconds; creation with CPU/memory options, metadata, TTL, commands, files, cleanup |
| External metadata/TTL ownership | PASS | Temporary clients closed; observer shutdown preserves the running owned instance |
| Real list visibility | PASS | Existing documented eventual-consistency window: up to 40 seconds, 2-second polling; creation never retried |
| Initial immediate list assertion | FAIL | Two diagnostic runs returned an empty page immediately after creation; retained as failed runs, not silently counted as passing |
| Complete client suite | PASS | 1967 passed, 21 skipped, 251.19 seconds; skips are not acceptance |
| Both-package lint/format and repository hygiene | PASS | Final changed tree |
| Client mypy | PASS | 83 source files |
| Repository health | BLOCKED | 105 PASS, 1 WARN, 1 existing English/Chinese archive mismatch |
| Complete repository typecheck | BLOCKED | Existing server routes_browser.py unused-ignore after Playwright dependency became available |

Both-package lint and format-check pass; repository hygiene passes. The full
client suite passes with the explicit skips recorded above.
The earlier full server suite had 843 passes, 7 failures and 1 skip, including a
platform HTTP 501 denial (`项目网络审计已关闭`). Denied raw-HTTP paths were not
retried or bypassed. See the workspace-source and command-loader evidence.

## Cleanup

All diagnostic resources were destroyed in explicit kill/finally paths. The new
real E2E tracks created IDs with the repository cleanup fixture; owned-manager
shutdown and fixture cleanup run on assertion failure. Observer sessions own no
resources. No existing templates or other users' sandboxes were deleted.

## Problems found

Cross-review found exception-based credential disclosure and corrected it before
cloud verification. Initial list tests assumed immediate consistency; existing
cloud lifecycle tests document the delayed visibility, now respected by the new
E2E. The unsuccessful diagnostic results remain separate evidence.

## Not verified

Full make ci remains open because of the previously recorded server suite,
optional-import typing and document-health gates. No Docker build, new template
image deployment, IDE session, other provider or complete Skills product acceptance
is claimed. The implementation belongs in a draft PR until those gates pass.
