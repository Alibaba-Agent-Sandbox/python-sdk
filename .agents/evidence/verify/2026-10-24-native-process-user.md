# Verification: Native process OS user

- Date: 2026-10-24
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/83
- Base: b0407a7; scoped shared envd process adapter, tests, documentation and paired version metadata.
- Result: PARTIAL — targeted real-cloud acceptance passed; full gates are running.
- Package under test: source candidate client/server 0.3.1a2, isolated editable installation, not a public release.
- Environment: Python 3.12.13, Linux, real Express base in the configured region.
  Credentials supplied through the ignored environment, values not recorded.

## What was verified

The published 0.3.1a1 native caller returned UID 1000 for `user="root"`; a standard
caller on the same owned target returned UID 0. This repeats Issue 83. Before the
fix, new wire regressions failed because `process.user` remained in the request
and invalid principals reached HTTP. After the fix, 106 process/command/transport
tests passed.

## Commands run

```sh
uv pip install -e './server-sdk[dev]' -e './client-sdk[dev]' hatchling build twine
python -m pytest tests/test_protocol/test_process_user.py tests/test_protocol/test_process.py tests/test_transport/test_http.py tests/test_api/test_commands.py -q --tb=short
make ci
python -m pytest e2e -m 'e2e and not e2e_slow' --maxfail=5 -ra --tb=short
```

The pytest unit command runs from `client-sdk`. The repository has no lockfile;
installation uses the owner CI's declared pyproject dependencies in an isolated
environment. Full commands below remain pending until their results are recorded.

## Results

| Scenario | Result | Observation |
| --- | --- | --- |
| Focused process/command/HTTP unit suite | PASS | 106 passed |
| Real same-ID native/standard root | PASS | Both exit 0, UID 0 |
| Real same-ID native/standard user | PASS | Both exit 0, UID 1000 |
| Native `commands.start(user="root")` | PASS | UID 0 |
| Native nonexistent account | PASS | EnvdRpcError, HTTP 401; no silent fallback |
| Default identity before/after explicit calls | PASS | UID 1000 unchanged |
| Mandatory local CI | RUNNING | No completion claim |
| Official non-slow E2E | RUNNING | No completion claim |

An independent agent reviewed the implementation, real HTTP-client wire assertions,
same-ID comparison script and its exact cleanup checks; no scoped blocker was found.

## Cleanup

The focused live run registered the ID from its creation callback, killed only that
sandbox in `finally`, and independently read it back as `SandboxNotFoundError`.
No resource identity, gateway URL, credential or raw provider response is published.
The official suite's owned-resource cleanup is verified separately after completion.

## Problems found

No new product issue in the focused acceptance. Initial old-code regression failures
remain evidence of the original defect, not passing tests.

## Not verified

Public 0.3.1a2 installation/publication is not part of this PR verification. Both exact
PyPI version endpoints returned 404 before preparation; no existing version is replaced.
Remote CI, full local checks and the official E2E result are still pending.
