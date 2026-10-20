# Verification: Optional application runtime

- Date: 2026-10-20
- Change: proposed ADR `2026-10-20-agent-application-runtime`; owner issue https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/74
- Result: PARTIAL; full FC acceptance remains BLOCKED
- Package under test: client/server 0.3.0 source checkout with uncommitted application runtime changes, based on `bb83123b31ecf3bafaa7818ddea0fc7c856b1dc7`
- Environment: Linux, CPython 3.11.15; PostgreSQL verification uses pgserver 0.1.4 and psycopg 3.3.6; official FC SDK 4.8.3. Credentials supplied in memory from a gitignored environment file; values are not recorded.

## What was verified

Durable application acceptance, immutable snapshots, ownership, scopes, outbox,
conditional claims, cancellation races, lease fencing and verified cleanup were
tested locally. Real PostgreSQL locking and transaction behavior were exercised.
Separate gateway, worker and dispatcher processes drove actual SandboxServer file
APIs over SDK HTTP with a deterministic model fixture. A new real-cloud test drove
the external application loop against an actual AsyncSandbox, including remote
shell, files, artifact capture, durable result and confirmed deletion. No real
LLM or deployed FC application is implied by deterministic model tests.

## Commands run

```bash
pip install -e ./server-sdk -e './client-sdk[dev]'
pip install 'psycopg[binary]>=3.2,<4' alibabacloud-fc20230330 alibabacloud-credentials
pip install pgserver==0.1.4
make test
make lint typecheck
cd client-sdk
pytest tests/ -q
pytest tests/test_applications -q
pytest tests/test_applications/test_postgres.py -q
cd ..
python -m pytest e2e/test_10_application_runtime.py -q --tb=short
make build dist-check
bash scripts/check-repo-health.sh --quiet
```

The real-cloud command was launched by a wrapper which loads only existing
sandbox configuration keys into memory; no credential values were printed or
written into this record. An untouched `git archive HEAD server-sdk` export was
used for baseline comparison of unrelated server HTTP framing failures.

## Results

| Scenario / test | Result | Notes |
| --- | --- | --- |
| Application lifecycle/fault/HTTP/PostgreSQL suite | PASS | Latest complete local run before final review: 25 passed; subsequent review corrections require the final follow-up run |
| Real PostgreSQL concurrency | PASS | Four simultaneous schema startups, 24 idempotent creates, 24 claims with one attempt, cancel/success, restart and event ordering |
| Three-process HTTP and actual local SandboxServer | PASS | Restart persistence, auth, remote file operations, artifact retrieval, SSE reconnect and terminal cancel |
| New real-cloud external application runtime | PASS | 1 passed in 12.09 seconds; actual remote shell/files/artifact; deterministic model |
| Full server suite, initial run | FAIL | 852 passed, 1 skipped, 3 failed; details below |
| Untouched server baseline comparison | FAIL | 2 same HTTP failures reproduced; pip inventory passes after environment setup correction |
| Full client suite, initial run | FAIL | 2225 passed, 3 skipped, 15 missing sibling-provider fixture failures; follow-up recorded separately |
| Full lint/typecheck | PASS | Both distributions; 56 server and 115 client source modules at that checkpoint |
| Build, twine, typed wheels, combined installation | PASS | Both distributions install/import together; no release was published |

## Cleanup

The real-cloud application test uses the existing metadata tag and tracker. Its
executor destroys its sole owned sandbox. A second `AsyncSandbox.kill(id)` returns
False, proving that ID is absent; the test finally block and tracker also attempt
cleanup. No cloud sandbox leak was observed. Local subprocesses are terminated
and temporary PostgreSQL instances stopped by their test finalizers.

## Problems found

Independent review identified and fixed an incorrect local endpoint discovery ID,
execution inputs missing from immutable snapshots, unsafe assumptions about FC
forwarding custom headers, an outbox stale-ack race, unbounded cooperative cleanup,
and the lack of a trusted resolution path for uncertain runs. The implementation
now uses role-scoped HMAC body envelopes, run/outbox lock ordering plus conditional
lease acknowledgements, bounded cleanup and trusted proof-based resolution.

The unchanged server baseline returns 501 instead of 400 for a malformed
WebSocket upgrade and 502 instead of 400 for a chunked-framing rejection in this
environment. These exact failures reproduce in an untouched source export.
The initial uv environment lacked pip, causing the package-inventory test to
report an empty list; installing pip corrected that setup issue. Initial client
provider-engine tests lacked sibling catalog fixtures in the isolated checkout;
the root task supplied a source link before the targeted follow-up.

## Not verified

Full FC application deployment, image execution, actual cloud PostgreSQL binding,
function-role IAM, timer delivery, FC cancellation and actual LLM calls remain
BLOCKED: there is no Docker binary or configured managed application PostgreSQL
binding in this session. The FC SDK request structure and body-authentication
contract are tested, but no mocked SDK response is counted as a cloud pass.
Managed B publishes final output; full local progress-event relay, TTL pruning,
checkpoint/resume and object-store artifact offload are not implemented.

## Follow-up verification

Final runtime suite: 26 passed in 10.88 seconds, including HMAC timer/body invocation,
core real-server discovery and trusted incident resolution. Strict mypy passes all
11 application source modules; Ruff passes. Repository health reports 107 passes,
1 existing missing-release-guide warning and zero failures. Final full lint/typecheck/format gates pass (56 server and 116 client source modules),
with both wheel builds and combined installation passing again. The provider-engine
follow-up completed with 13 engine-start timeouts and 26 passes, after adding the
missing sibling fixtures. These remaining integration failures are not counted as
passes. The E2B lifecycle/data-plane engine timeout also reproduces with untouched
Python source exported from the base commit (1 failed in 32.88 seconds), sharing
the same companion CLI/environment. This isolates it from the optional Python
application module; it does not establish that the current companion CLI is fault-free.
