# Verification: Python MCP binary file transfer

- Date: 2026-10-16
- Change: bounded binary MCP file tools, Issue 48
- Result: PARTIAL
- Package under test: source client/server 0.3.0, based on merged main 666657b
- Environment: Linux, Python 3.11.15; Express credentials supplied in memory only

## What was verified

Strict Base64 binary transfer uses existing SDK file APIs. Optional SDK streamed
bounds preserve the unlimited default. File-tool adoption/shutdown semantics
remain unchanged, with separate metadata and task-retention contracts.

## Commands run

- Focused and combined client agent/API/protocol/transport pytest suites.
- `make ci`; separate complete client tests and package checks where a server baseline failure stops make.
- Isolated-HOME focused real Express pytest, catalog plugins linked from their public source checkouts.
- Complete isolated-HOME `make e2e`, followed by final identity-path focused cloud acceptance.

## Results

| Scenario | Result | Notes |
| --- | --- | --- |
| Initial local regressions | FAIL, fixed | Existing tool-count fixtures needed 13→15; streamed-limit delegate fixtures were extended |
| Binary/transport focused | PASS | 38 cases: actual max-size STDIO process and HTTP session with fake delegates; local httpx streams, closure, validation/privacy, normal adoption |
| Final affected client regression subset | PASS | 380 tests / 9.48s, including final 38 binary cases and agent/API/filesystem/HTTP suites |
| Client type checker | PASS | Package configuration, 86 files |
| Local CI server suite | FAIL baseline | 848 passed, 7 failed, 1 skipped; server source unchanged; exact failures retained below |
| Initial real Express attempts | FAIL, then fixed | Premature observer shutdown destroyed the adopted sandbox; native create's legacy adapter lacked the new optional bound |
| Focused real Express final | PASS | 1 test, 9.82s; maximum binary/hash/reconnect/missing/overflow; full follow-up additionally covers native-created bounded and empty reads |
| Complete client suites | PASS | Initial 2037 passed / 22 skipped; final broad rerun 2046 passed / 22 skipped, with subsequent compression/header/timeout guards additionally covered in focused tests |
| Package build/distribution | PASS | Both wheel/sdist artifacts, twine, py.typed and combined installed import; source PYTHONPATH removed |
| Health/hygiene/lint/format/diff | PASS | Health 106 pass / 1 existing recommended-runbook warning / 0 fail |
| Complete real-cloud make e2e | PASS | 115 passed / 4 native prerequisite skips / 2 slow deselected / 1 existing KI-009 xfail, 247.26s, exit 0 |
| Final identity-path real Express test | PASS | 1 test / 11.78s; max/empty native-created and reconnected reads, independent SHA, missing/overflow, owned cleanup |
| Remote CI/review | PENDING | No unexecuted gate is claimed |

The observed seven server failures are WebSocket/HTTP framing/policy/package tests:
`test_upgrade_without_a_key_is_a_400_not_a_hang`,
`test_token_is_required_for_the_upgrade`,
`test_valid_still_works`, `test_transfer_encoding_rejected_in_policy_mode`,
`test_lying_content_length_cannot_exceed_cap`, `test_ambiguous_x_access_token_rejected`,
`test_pip_returns_structure`. These local environment failures are not hidden or
rewritten as passes; current-head remote CI remains required.

## Cleanup

Each failed/focused cloud attempt tracked exactly its own sandbox and reported
`leaked_after_cleanup=0`; independent tagged janitor dry runs found zero candidates.
Temporary isolated HOME directories were removed and the owned Node engine was
stopped (exit 0). Full-suite fixtures reported no leaked owned resources; its extra tagged dry run also found zero candidates and owned engine stop exited 0. No model
request, cloud secret upload, or remote credential storage was performed.

## Problems found

1. Tool-list assertions needed the newly exposed two tools.
2. Test shutdown sequencing violated existing file-operation adoption ownership.
3. Native create's legacy gRPC file protocol could not enforce a new optional
   response bound. Its explicit bounded path now delegates to the existing native
   envd HTTP protocol; it does not silently read unlimited data first.

## Not verified

No live native E2B/container/OpenSandbox binary acceptance, resumable/chunked
transfer, immutable file snapshot or atomic write guarantee is claimed. Node
provider bounded reads deliberately return unsupported. Complete P0–P2 remains
tracked by [Issue 45](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/45).

These seven belong to the eight baseline cases independently reproduced in the
[merged task evidence](2026-10-16-mcp-background-tasks.md). No server source changed.
The first packaging command used the test-only interpreter without the build
module and failed before building; the existing workspace build environment is
used for the actual artifact/install check, with source PYTHONPATH removed.

## Independent review follow-up

Root identified a real pre-commit compression bug: streamed decoded bytes were
materialized with the original gzip header, reproducing `DecodingError`. Bounded
reads now force identity (including overriding lower-case caller headers), reject
non-identity before any body read, count raw identity bytes and rebuild length/
encoding/framing headers. Four encoding negatives prove zero body iterations and
response closure; unbounded gzip remains compatible. The final identity cloud
check is separate from the earlier complete suite, not relabelled as a second
full run. Python 3.10's distinct asyncio timeout class is handled explicitly.

The broad suite uses this source checkout with both package source roots. Its
CLI invocation uses the existing built Node CLI checkout at c269603; this does
not claim fresh CLI publication, Docker deploy acceptance or a hosted MCP
endpoint. The four real-cloud skips remain: missing OpenSandbox readiness,
explicit CubeAPI URL, native E2B key and container-edition domain/key. KI-009 is
still the platform Jupyter trailing-expression fallback limitation.
