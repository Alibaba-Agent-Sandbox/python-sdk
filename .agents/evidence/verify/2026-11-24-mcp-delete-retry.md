# Verification: retrying an explicit Python MCP workspace deletion

- Date: 2026-11-24
- Change: [Issue 169](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/169)
- Result: PASS for the scoped retry verification
- Runtime: Python 3.13 with editable Client and Server SDKs from the a9a572d baseline plus the patch
- Environment: Linux, isolated local test state, and a configured real Express Provider

## What was verified

All three lookup forms reproduced lost state before the fix. After the fix,
deletion failure leaves the exact bound handle and owner metadata in the
active session. The overlapping-create test leaves the newer default selected.

## Commands run

- `python -m pytest client-sdk/tests/test_agent/test_mcp.py -q -k kill_failure` on the original implementation
- `python -m pytest client-sdk/tests/test_agent -q`
- `python -m pytest e2e/test_09_mcp_lifecycle.py -q -k lifecycle_and_external_inspection`
- `ruff check` and `ruff format --check` on the changed Python files
- `mypy src/agent_sandbox` from the Client SDK directory

## Results

| Scenario | Result | Scope |
| --- | --- | --- |
| Red regression | FAIL as expected | Default, bare and qualified IDs lost the workspace on the baseline. |
| MCP unit suite | PASS | 287 tests, including failure retention and overlapping create. |
| Express workspace and retry | PASS | One real Sandbox exercised state, files and a command returning 42. A controlled pre-request delete failure returned an error. The retry used the original connection and real Provider. A separate Provider query returned typed not-found. |
| Static checks | PASS | Ruff and formatting for edited Python files, mypy across 114 Client SDK source files. |

## Cleanup

The existing E2E tracker registered the one owned Sandbox. The test deleted
that Sandbox with the retry and separately confirmed absence before ending.
The suite's cleanup also ran. No template, credential or account change was
requested or created.

## Problems found

The generic SDK kill normally closes its transport even after a Provider
failure. Preserving the record alone would not guarantee a usable bound
connection. The MCP path now requests that the connection stay available on
failure. Public SDK calls retain their close-on-failure behavior.

## Not verified

The fault is injected before sending the first delete. Ambiguous outcomes after
a Provider accepts a request, other Providers, remote HTTP Session termination
and modern MCP wire negotiation are outside this verification. Required remote
CI and review are checked separately on the PR.
