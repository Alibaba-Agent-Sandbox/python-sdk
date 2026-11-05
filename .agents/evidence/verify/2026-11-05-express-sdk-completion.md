# Verification: Express SDK completion

- Date: 2026-11-05
- Change: proposed/feature/2026-11-05-express-sdk-completion;
  https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/152
- Result: PARTIAL
- Package under test: client/server 0.4.0a6 source pair on task branch, based on
  daabf3cc12fbbc877cb2942c35578d8424f6cc3b; no release or remote merge claimed.
- Environment: Linux, CPython 3.11.15; isolated editable client/server installation with
  declared dev extras and build/twine. No Python dependency lock exists in this repository.
  No cloud credentials were read or cloud mutations performed by this implementation agent.

## What was verified

Regressions exercise explicit application argument objects, retained private traffic
credentials, read-only attach, STS resolution and engine handoff, network creation wire
values, documented typed lifecycle routes and rebinding previously used provider objects.
Existing standard clients and unrelated provider behavior retain their own contracts.

## Commands run

From the client package:

```sh
python -m pytest tests/test_api/test_express_completion.py -q
python -m pytest tests/test_api/server_e2e/test_server_client_e2e.py::TestCoreAndDiscovery -q
python -m pytest tests/test_api/test_express_completion.py tests/test_api/test_volume_mounts.py tests/test_api/test_lifecycle_without_connect.py tests/test_providers/test_managed_api_key.py tests/test_providers/test_commands.py tests/test_providers/test_sandbox_provider.py -q
python tests/fixtures/generate.py
mypy src/agent_sandbox/
python -m pytest tests/ -m 'not integration'
```

From the owning repository:

```sh
make ci
make build dist-check
bash scripts/check-repo-health.sh --quiet
```

## Results

| Scenario / check | Result | Scope |
| --- | --- | --- |
| Initial candidate behavior regressions | FAIL, preserved | Missing APIs/fields/gates demonstrated before implementation; candidate alias expectations were later rejected in favor of the existing single-env contract. A mistaken test cleanup call was corrected before counting product failures. |
| Focused related suite | PASS, 133 tests | Local model/protocol/provider adapter checks, not cloud acceptance |
| Expanded compatibility suite | PASS, 220 tests; 5 skipped | Corrected owning protocol mock targets and current contract expectations; skip is absent sibling CLI checkout |
| Real local HTTP command suite | PASS, 7 tests | Running SandboxServer, including business timeout/request_timeout/arguments/name fields |
| Final explicit API regressions | PASS, 21 tests | Includes private create through application-client credentials without hidden POST |
| Final complete client suite | PASS, 2383 tests; 26 skipped, 10 deselected | Complete non-integration suite after compatibility corrections; the additional final private-create regression passed separately |
| Build and distribution checks | PASS | Both wheels/sdists, twine, py.typed and clean combined installation |
| Client mypy | PASS, 103 source files | Correct package configuration; an earlier repository-root invocation did not load that configuration and is not the gate result |
| Client lint / format | PASS | No broadened formatting changes |
| Health | PASS, 106 passes, 1 existing warning | Missing optional release runbook remains a warning |
| First full client run | FAIL: 2365 passed, 15 failed, 26 skipped, 10 deselected | Stale protocol mocks, fixtures and old contract assertions plus refresh URL derivation; these findings were corrected and the complete run repeated |
| First make ci server suite | FAIL: 878 passed, 2 failed | Existing malformed-WebSocket request intercepted locally; missing pip in the fresh uv environment |
| Exact fixed-HEAD server comparison | PARTIAL | Same malformed-WebSocket 501 on untouched source. Installing pip fixed the package-inventory prerequisite case. |

The independent raw socket response for the malformed WebSocket request was HTTP501 with
`Content-Type: text/plain` and the body meaning "project network auditing is disabled".
This is not the server's expected JSON error. The unchanged server implementation explicitly
returns HTTP400 for this handshake. No product assertion was weakened to accept the local
network-layer response. Required remote gates remain independent.

Final full-suite/build and real Express results are appended by the coordinating task when
completed. These local results do not certify all cloud APIs or service admission.

## Cleanup

Local SandboxServer fixtures own and close their listeners. No cloud sandbox, template,
Volume or API Key was created by this agent. Cloud cleanup evidence belongs to the separate
coordinated real-service run.

## Problems found

Complete the final independent review, containing CLI compatibility and real Express
same-object pause/resume/private-application verification. Existing official descriptions
of conditional network/metrics behavior are not resolved by local unit tests.

## Not verified

No complete cloud E2E, credential creation/renewal, storage backend or package publication
was performed in this local implementation slice. The ADR remains proposed pending the
coordinating task's required acceptance and merge gates.
