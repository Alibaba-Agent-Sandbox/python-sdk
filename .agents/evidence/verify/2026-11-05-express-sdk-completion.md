# Verification: Express SDK completion

- Date: 2026-11-05
- Change: implemented/feature/2026-11-05-express-sdk-completion;
  https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/152
- Result: PARTIAL
- Package under test: client/server 0.4.0a6 source pair on task branch, based on
  daabf3cc12fbbc877cb2942c35578d8424f6cc3b; no release or remote merge claimed.
- Environment: Linux, CPython 3.11.15; isolated editable client/server installation with
  declared dev extras and build/twine. No Python dependency lock exists in this repository.
  Initial implementation checks used no cloud credentials. The later explicitly authorized
  real-service diagnosis below used existing project credentials only in child processes.

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

## Independent review follow-up

The runtime reviewer found three concrete gaps: fallback session construction still selected
the generic lifecycle adapter; cloud creation failures could reflect newly supported network
header credentials through both messages and the raw HTTP exception chain; and the new
ProviderSandbox.invoke convenience method could not authenticate a normal application service.
Five regressions failed before correction and one ordinary-error control passed. After the
fixes, the focused model/protocol suite plus actual local HTTP suite passed **34 tests**.
The authenticated local server rejects an omitted application token with HTTP401 and accepts
the explicit token without consuming a business field named application_token.

A further actual-HttpClient HTTP401 regression first failed: authentication conversion
precedes the creation adapter and still retained the raw HTTP request through its cause.
The targeted correction now reconstructs any SDK SandboxError when network header secrets
exist, including InvalidAPIKeyError, preserving its typed class and status. The expanded
focused suite passed **35 tests**, and mypy/lint/format passed again. Ordinary nonsecret
errors remain unmodified.

Creation errors with network-header credentials retain their existing typed class, HTTP
status and safe cloud detail. Known literal/Bearer/replacement values are removed, and the
new exception is raised outside the handler so no raw __cause__ or __context__ retains the
credential-bearing HTTP request. Ordinary nonsecret error details and behavior stay intact.

Final review source checks passed: mypy **103 files**, complete client lint and **246**
formatted files. The repeated complete client non-integration suite passed **2390 tests**,
with **26 skips and 10 deselections**, in 189.86 seconds. Repository health remains
**106 PASS / 1 existing WARN / 0 FAIL**; diff and manual-script lint checks pass.

## Real private application diagnosis

The coordinator's initial application failure was preserved. Independent source inspection
showed its fixture discarded an unconsumed background StreamReader: the lazy envd Start
request had not run. Health alone therefore did not identify the registered fixture service.
The corrected manual fixture uses an owned listener on port9017, actively consumes the
stream and first verifies the current command over localhost through native envd.

An independent owned sandbox run then passed: localhost command discovery/invocation,
public direct HTTP command discovery/invocation, Python SDK discovery/invocation with
distinct application/traffic credentials, anonymous gateway HTTP403, and DELETE followed
by independent GET404 with zero remaining resources. Safe result summaries live in the
coordinating artifact private-app-diagnosis.jsonl; no token or raw cloud response was logged.

The combined CLI-binary/Python/Node acceptance is recorded separately. Its first attempt
preserves a remaining controller assertion and intermittent network-command E8020 rather
than reporting all cloud APIs passed. Storage append still needs a real supplied mount fixture.

The second combined run used the actual standalone CLI binary (SHA256
`12279a0bbeee72ceb35185e9a097eb5e314cef6e1a9ab0e22a9adcf1284fdfc2`). Private creation,
same-object pause/resume with subsequent exec/files, localhost application registration,
direct HTTP, ProviderSandbox.invoke with explicit application authentication, read-only
attach with explicit traffic credentials, anonymous HTTP403, provider network replacement
and clearing, and provider timeout all passed. Independent owned deletion was confirmed
by GET404 with **zero remaining**. The optional Node subprocess controller did not return
its expected JSON summary; that is recorded as a separate unresolved cross-component
check, not a Python failure or proof of a Node product defect. No storage backend fixture
was supplied. Earlier network E8020 results remain recorded and are not relabelled as stable.

The final combined real-service run also passed the optional Node application's actual
command list/invoke through the same private gateway, with result equality checked by
deep value comparison. Its prior connection failure was independently reproduced with
raw Node fetch as `UNABLE_TO_VERIFY_LEAF_SIGNATURE`: the controller's minimal child
environment had dropped the project's configured NODE_EXTRA_CA_CERTS/SSL_CERT_FILE.
Inheriting only those trust settings fixed the controller; TLS verification was never
disabled. Python native exec/files, typed lifecycle, explicit authenticated invoke,
read-only attach, anonymous HTTP403 and owned cleanup GET404 passed in this run as well.

Moving network replacement immediately after lifecycle excluded the independent app
scenario's duration from that test. The service still returned **HTTP409** on that run;
this is preserved as a service/state failure, not reinterpreted as TTL expiry or a 204
parsing defect. A prior real run passed replacement and clearing. Stable network mutation
acceptance and storage-append backend evidence remain separate unresolved gates.

## Coordinating acceptance and remote checks

The initial product commit 1aef5f67ab54131ab1e6a060034a3c1f8b5c6e5d passed the complete GitHub Python3.10/3.11/3.12 client/server matrix, public runtime Docker fixtures, pinned E2B contract, provider engine and documentation workflows in [CI run 41992672991](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/41992672991). This separately resolves the environment comparison; the local malformed-WebSocket failure remains recorded above.

Final independent review confirmed normal/fallback protocol construction, credential rebinding, explicit application authentication, legacy keyword compatibility and STS propagation. It found the reflected network-rule error path also needed to handle authentication errors and JSON-escaped/short header values. Actual HttpClient regressions failed first, then passed. Secret-bearing create failures now use fixed safe diagnostics while preserving typed code and numeric status, with no raw exception chain/request/response; ordinary errors retain their diagnostics. The focused final set passed all 36 cases. The complete client run including authentication coverage passed 2391 tests, with 26 skips and 10 deselections; the extra escaped-value regression passed in the focused set and is included in the subsequent complete/remote checks.

The implemented decision concerns SDK lifecycle, application calls and configuration. Real mount data access, stable cloud network mutation and cache template admission belong to the companion CLI acceptance. This record does not turn their partial or blocked results into passes. The final follow-up head must pass its own required remote checks before merge. No package release is included.
