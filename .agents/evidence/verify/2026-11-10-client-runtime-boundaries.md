# Verification: Client installation and local runtime boundaries

- Date: 2026-11-10
- Change: [Issue 157](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/157)
- Result: PARTIAL — changed-surface checks pass; existing raw HTTP/SSE failures prevent a green local full-suite result. Cloud E2E remains separate.
- Package under test: local client/server 0.4.0a7 sources and built wheels; no version bump or publication.
- Environment: Linux, Python 3.11.15. No cloud credentials used by the local checks.

## What was verified

Client-only installation imports the standard synchronous/asynchronous clients,
interpreter clients, ProviderSandbox, ServerClient and remote decorator without
a server distribution. It performs a real localhost HTTP health request.
Registration without a local runtime fails with installation guidance and no
partial local registration. Installing the server extra resolves the exact local
runtime wheel, preserves the shared namespace and registers a real function.
Dynamic functions also register without unnecessary source inspection. Instance
execution and actual remote-decorator behavior retain their existing regressions.

## Commands run

Run from the repository root using an isolated virtual environment (pip was seeded for the server package-list test):

```bash
uv pip install -e ./server-sdk -e './client-sdk[dev]' hatchling build twine
python -m pytest client-sdk/tests/test_declarative client-sdk/tests/test_packaging.py client-sdk/tests/test_version_lockstep.py -q
make lint typecheck format-check
make build dist-check
make test
# make stopped after server failures; run the client suite separately:
(cd client-sdk && python -m pytest tests/ -v --tb=short)
python -m pytest client-sdk/tests/test_release_validation.py client-sdk/tests/test_declarative/test_register.py -q
make hygiene
bash scripts/check-repo-health.sh
ruff check scripts/check_dists.py
ruff format --check scripts/check_dists.py
```

## Results

| Scenario / test | Result | Notes |
|---|---|---|
| Focused declarative, actual wheel metadata and lockstep tests | PASS | 112 passed; includes dynamically defined function registration |
| Both package lint/type/format checks | PASS | 58 server and 114 client source files typechecked; 94 server and 260 client files formatted |
| Both wheels and sdists; twine; py.typed | PASS | Built from the candidate source; all four artifacts accepted |
| Client-only fresh wheel installation | PASS | Runtime distribution and namespace absent; client imports, decorator construction, explicit registration error and real HTTP pass |
| Local server extra in the same fresh environment | PASS | Offline resolution from the local server wheel; registration and pip check pass |
| Full server suite (`make test`, first phase) | FAIL | 877 passed, 3 failed; the client phase did not start because make stopped |
| Server failures rechecked after seeding pip | FAIL | Package-list test passes; unchanged WebSocket handshake and transfer-encoding tests still receive 501/502 rather than 400 |
| Full client suite run separately | FAIL | 2455 passed, 35 skipped, 8 failed; six existing raw HTTP/SSE cases and two outdated publication-workflow assertions |
| Release-workflow and registration follow-up | PASS | 74 passed after updating the expected two-phase installation checks; dynamic registration uses an isolated real registry |
| Hygiene | PASS | No local paths or credential-like strings found |
| Repository health | PASS | 106 passed, 1 warning, 0 failed after adding this evidence |

## Cleanup

The distribution verifier shuts down its owned HTTP server, joins its thread,
closes the HTTP client and removes its temporary virtual environment. No cloud
resources were created by these checks.

## Problems found

The first packaging assertion assumed Hatchling retained an extra self-reference;
actual wheel metadata expands `all`/`dev`. The corrected test checks their exact
server dependency. The first HTTP probe used `close()` instead of the public
`ServerClient.aclose()`; after correcting the probe, the complete isolated
installation check passed. These were test-harness errors, not product failures.
The uv-created development virtual environment initially lacked pip; the server
package-list regression passed after installing pip. No server product source
was changed. Two server tests still fail with 501/502 responses:
`test_upgrade_without_a_key_is_a_400_not_a_hang` and
`test_transfer_encoding_rejected_in_policy_mode`.

The client managed-runtime failures concern private octet-stream rejection
(dispatcher/worker), incomplete request bodies, HTTP/1.1 SSE framing, and
post-header SSE failures (runtime/managed). They received timeouts or HTTP501.
Those runtime implementations and test assertions were not modified. Their
root cause has not been established by this change; no assertions were relaxed.
The two publication tests initially assumed one install/import verification
phase; their updated two-phase expectations pass, including existing failure
and retry bounds.

The existing pytest-asyncio default fixture-loop warning and mypy unused-section
notice remain informational.

## Not verified

No package was published and no claim is made about an already published wheel
adopting these source changes. Full cloud `make e2e`, conditional provider features
and the Python 3.10/3.12 CI matrix have not been executed in this local check.

## Current CLI documentation follow-up

Current bilingual usage/reference guides and the SDK authoring skill were checked
against the coordinated CLI source. The command map now describes first-party
runtime and authoring responsibilities; template build/publish and named deploy
are distinct, SDK instance methods are preserved, and CLI local names must be
resolved to actual Sandbox IDs before Python connects. Archives/design history
remain unchanged. Changed Markdown introduced no missing relative link targets;
this is current-source guidance, not a claim of a new CLI/PyPI release.

## Final documentation check

- Changed Markdown local-link audit: 47 files checked, no introduced missing file links. URL anchors and remote pages were not fetched.
- Current CLI examples use named deploy/status/delete, sandbox operations and Provider run with JSON input. Historical archived documents remain historical.
- CHANGELOG updated; no version bump or package publication.
