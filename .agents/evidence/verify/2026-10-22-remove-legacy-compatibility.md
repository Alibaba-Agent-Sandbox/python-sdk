# Verification: remove retired project compatibility

- Date: 2026-10-22
- Result: PARTIAL (remote acceptance pending)
- Revision: scoped files in branch `refactor/remove-legacy-20261022`; the containing commit is the reviewable source revision.
- Environment: Linux, Node.js 22.22.2; Python 3.11.15 in an isolated environment.
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/84

## What was verified

Retired project APIs, migration fields and fallbacks are removed rather than forwarded. Tests and bilingual documentation describe one current contract. Historical engineering evidence is preserved.

## Commands and results

- PASS: client `pytest tests/ -q --tb=short` — 2144 passed, 22 skipped on Python 3.11.15.
- PARTIAL: server `pytest tests/ -q --tb=short` — 874 passed, one skipped, one blocked failure. The missing-key WebSocket test receives HTTP 501 with the environment message “project network audit disabled” instead of the application response. A direct reproduction confirmed the intercepted body; it is not counted as a pass.
- PASS: focused shared-config, lifecycle and adapter regressions — 171 passed.
- PASS: `make lint format-check typecheck hygiene`; mypy checked 56 server and 94 client source files.
- PASS: `make build dist-check` — both distributions, typing markers and a combined fresh-environment wheel installation/import.
- PASS: `bash scripts/check-repo-health.sh` — 106 passes, one historical warning, zero failures.
- PASS: real-cloud `python -m pytest e2e/test_01_platform.py e2e/test_02_lifecycle.py e2e/test_03_commands.py -q --tb=short --maxfail=1 -k 'list_sandboxes or wrong_api_key or create_kill or run_echo'` — four passed, 29 deselected. Authentication rejection, inventory and a real sandbox command were exercised with fixture-owned cleanup. Credentials were loaded from the ignored workspace environment file without recording values.

## Outstanding gates

Required remote CI, review and merge are not established by local results. Initial Git invocations had not loaded the ignored workspace credential file; authenticated fetch and GitHub access now succeed. No package release or manual production deployment is requested. Cross-repository consumers must land after their shared contract.

## Cleanup

Local fixtures use owned temporary resources. The Python cloud fixture tracks and cleans its own sandbox resources. No raw credentials or sensitive logs are included. Native checks that did not execute are not passes.
