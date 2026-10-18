# Verification: provider Volume acceptance after accepted binary-file integration

- Date: 2026-10-16.
- Result: PARTIAL overall; fresh focused integration checks recorded below, prior required
  local full-server aggregate remains failed.
- Starting branch: `452b5e53379a4d16a1fb95b8b677707a6ae59ed8`.
- Accepted main integrated: `0ce8359` (bounded MCP binary file transfers, PR #49).
- Delivery: [Python PR #38](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/38).
- Environment: Linux, Python 3.11.15, Node 22.22.2; no cloud credentials supplied to local checks.

## Merge review

The remote PR became unmergeable after main accepted the bounded binary-file feature. A
normal merge retains both changelog entries. This is the only textual conflict; README
translations and `api/sandbox.py` merged automatically. Review confirms the create-time
Volume field/old-engine negotiation remain present and native connect now retains main's
bounded HTTP reader. Default file reads retain their prior engine route. No accepted
binary-file source, tests, ADR or evidence was rewritten.

## Verification

- `make lint format-check typecheck`: PASS, exit 0; both packages, 56 server and 87 client
  source files checked by mypy.
- The following focused tests: **253 PASS in 23.27 seconds**, exit 0. This includes actual
  Python-to-Node engine calls, shared commands/consent/no-replay, Volume forwarding, native
  gRPC behavior, and accepted MCP binary-file, tools and transport regressions.

```sh
python -m pytest \
  client-sdk/tests/test_providers/test_commands.py \
  client-sdk/tests/test_api/test_volume_mounts.py \
  client-sdk/tests/test_engine/test_engine.py \
  client-sdk/tests/test_providers/test_commands_engine.py \
  client-sdk/tests/test_agent/test_mcp_binary_files.py \
  client-sdk/tests/test_agent/test_mcp.py \
  client-sdk/tests/test_agent/test_mcp_http.py \
  client-sdk/tests/test_agent/test_tools.py -q --tb=short
```

- Repository health: **106 PASS / 1 WARN / 0 FAIL**.
- `make hygiene` and final `git diff --check`: PASS, exit 0.
- Independent read-only reviewer: no confirmed defect in persistence assertions/guarded
  cleanup, Volume forwarding/old-engine negotiation or accepted bounded-reader integration.
  The reviewer did not read credentials, change files or run cloud tests.

Checks use both source packages on PYTHONPATH, a unique per-run Unix socket and the absolute
Node CLI binary for the two real local engine tests. No unknown daemon was killed or replaced.
The cloud acceptance at the preceding source state remains historical evidence in
[real Volume acceptance](2026-10-16-provider-volume-live.md): the formal mount/persistence
suite passed 2 cases, with independent zero-owned-sandbox and complete infrastructure cleanup.
This merge adds no cloud resource and does not claim a second live run after synchronization.

## Remaining gates

Required full local server aggregate (847 PASS / 8 FAIL) remains unresolved; the complete
client/remote matrices and focused success must not be called a current full local make-ci pass.
The shared CLI host PR must land first. PR #38 and the provider ADR remain draft/proposed.
No gate was weakened and no merge to the default branch is claimed.
