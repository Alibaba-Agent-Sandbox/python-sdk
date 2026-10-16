# Verification: provider management recheck

- Date: 2026-10-16.
- Result: PARTIAL; real storage and the shared host's remaining cloud acceptance are blocked.
- Issue: [python-sdk #34](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/34).
- Delivery: [draft PR #38](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/38), dependent on
  [CLI draft PR #35](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/35).
- Tested product revision: `92b717c`, including accepted main `666657b`.
- Environment: Linux, Python 3.11 development environment and Node 22 source CLI.
  No cloud credentials were passed to these Python tests.

## What was verified

An independent read-only review found no new confirmed defect in command discovery/invocation,
manifest consent, no-replay transport, provider isolation or create-time Volume forwarding.
The branch now includes accepted main's server-loader, workspace, lifecycle and MCP task fixes.
Four documentation conflicts were resolved by retaining both features. The automatic merge of
`api/sandbox.py` preserves main's lifecycle APIs and this branch's Volume option.

## Commands and results

Commands below use the existing development interpreter on PATH and both source directories
on PYTHONPATH. A compatible absolute Node binary command is supplied for engine integration.

| Check | Result | Evidence / limitation |
| --- | --- | --- |
| `make lint format-check typecheck` | PASS | Both packages; mypy checked 56 server and 86 client source files. |
| `python -m pytest client-sdk/tests/test_providers/test_commands.py client-sdk/tests/test_api/test_volume_mounts.py client-sdk/tests/test_engine/test_engine.py client-sdk/tests/test_providers/test_commands_engine.py -q --tb=short` with `ABX_COMMAND_TEST_BIN` set | PASS | 95 passed in 20.61 seconds after main synchronization. Includes real local Python-to-Node and gRPC-to-HTTP checks; no cloud. |
| `python -m pytest client-sdk/tests/test_api/test_lifecycle_without_connect.py client-sdk/tests/test_agent/test_mcp_lifecycle.py client-sdk/tests/test_agent/test_mcp_tasks.py -q --tb=short` | PASS | 111 passed in 12.23 seconds; accepted lifecycle/task behavior remains intact. |
| `bash scripts/check-repo-health.sh` | PASS | 106 pass, one warning, zero failures after synchronization and the translated prerequisite clarification. |
| Independent pre-synchronization review | PASS | 93 targeted cases plus two actual Node engine cases; these overlap the later 95 and are not additive. |
| Pre-synchronization remote matrix at `5cc4407` | PASS | Nine checks: both packages on Python 3.10/3.11/3.12, build, hygiene and links. This does not establish the new head's status. |

The reviewer initially selected a non-executable module instead of `dist/bin/abx.js`, causing
two startup timeouts. With the correct absolute binary command, both cases passed independently
in 33.45 seconds and again in the post-synchronization 95-case run. The failed invocation is
not attributed to product source. No successful full local server-suite rerun is claimed;
earlier failed attempts remain in the linked historical evidence.

## Documentation and cloud prerequisites

The [official OSS Volume guide](https://help.aliyun.com/zh/agent-sandbox/user-guide/create-oss-volume)
currently requires invitation access through a support ticket. Both language guides now say
to confirm target account/region/Team access. Successful empty listing does not prove create
or mount authorization. This is separate from the existing Bucket, role and same-Team key
requirements. No credentials or private resource identifiers appear in this record.

The host recheck verified real `volume.list`, `team.list/get`, `api-key.list/get` and `quota.list`
without mutation; no Volume was visible. Host-owned details are recorded in the
[CLI recheck](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/feat/provider-operations-20261016/.agents/evidence/verify/2026-10-16-provider-management-recheck.md).
No real Python Volume mount or new Team/quota lifecycle is claimed.

## Cleanup and remaining gates

All local tests exited. Temporary plugin/engine fixtures finalized normally; no cloud resource
was created by this recheck. The review did not change another task's checkout or resources.

The shared host must land before this consumer. Authorized existing storage and same-Team key,
Volume invitation access, isolated Team/quota test configuration and real mount/read/write/cleanup
acceptance remain unavailable. The complete required local server gate and final-head remote
matrix must not be inferred from targeted tests. The PR stays draft and the ADR stays proposed.
No required checks or reviews were bypassed and no merge is claimed.

Historical evidence is preserved in [initial implementation](2026-10-16-provider-management-commands.md),
[mount review](2026-10-16-provider-management-final-review.md) and
[previous integration](2026-10-16-provider-command-integration-final.md).
