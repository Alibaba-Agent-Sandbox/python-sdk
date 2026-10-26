# Verification: Skill storage, retained state and MCP ownership

- Date: 2026-10-26
- Change: base `8959e4f` plus this task's scoped source, tests, Skills and documentation patch.
- Result: PARTIAL — real storage/state scenarios pass; repository-wide server checks retain two malformed-HTTP failures, the complete client run also retains two environment-blocked engine/mock failures.
- Package under test: editable matching client/server `0.4.0a6` from this checkout. This is source validation, not a new public release or a claim that public a6 contains the ownership correction.
- Environment: Python 3.11.15, Linux, real Alibaba Cloud Express in the configured region. Credentials were supplied locally through environment variables; values are omitted.

## What was verified

Real cloud data-plane effects establish owned OSS persistence and read-only access,
MicroVM memory/service/mount continuity, Snapshot clone isolation, and LangGraph
conversation reuse with separate user namespaces. The maintained opt-in pytest
scenario is distinct from the local fixture provisioner. New MCP unit and real
cloud regressions cover the independently discovered cross-session shutdown bug.
Initial failures remain separate receipts rather than being rewritten as passes.

## Commands run

Credentials and account-specific identifiers were injected from local configuration,
not included in command output or committed files. Equivalent repository invocations:

```sh
E2E_PAUSE_TEMPLATE=<eligible-microvm-template> E2E_SNAPSHOT_TEMPLATE=<eligible-microvm-template> \
  python -m pytest -q e2e/test_standard_contract.py -k 'pause_resume or snapshot_restore' --tb=short
E2E_SNAPSHOT_TEMPLATE=<eligible-microvm-template> \
  python -m pytest -q e2e/test_standard_contract.py -k snapshot_restore --tb=short
python -m pytest -q e2e/test_09_volume_mounts.py e2e/test_skill_storage_state.py --tb=short
python -m pytest -q e2e/test_09_mcp_lifecycle.py --tb=short
python -m pytest -q client-sdk/tests/test_agent --tb=short
python e2e/skill_tools_acceptance.py --output <new-sanitized-evidence.json>
make test
make lint
make typecheck
```

The Volume run supplied the exact explicit-owned fixture variables documented in
`e2e/README.md`; it did not select a pre-existing borrowed Volume. The Provider
runs redirected engine discovery/configuration to an isolated test directory using
existing configuration seams. The test engine was the actual Node CLI build;
`HOME` was not changed. Full unit checks ran without project cloud credentials.

## Results

| Scenario / test | Result | Actual observation |
| --- | --- | --- |
| Initial standard pause/Snapshot subset | PARTIAL | 1 passed, 1 failed in 27.38 seconds. Pause preserved the random HTTP service value and file. Snapshot create/list/restore, file read and process-memory continuity succeeded, but direct `/tmp` SDK overwrite failed with HTTP500 permission denied. |
| Independent pre-Snapshot file diagnostic | FAIL retained | The same second SDK write directly under `/tmp` fails before any Snapshot. Ordinary-user command overwrite works; `/home/user` SDK overwrite works. UID and file owner remained 1000 before/after restoration. No ownership or permission relaxation was used to hide the observation. |
| Corrected standard Snapshot regression | PASS | 1 passed, 4 deselected in 14.53 seconds. Same memory-only token, retained file, clone overwrite with unchanged source, Snapshot indexing/deletion and owned sandbox cleanup. The mutation file is inside an owned non-sticky directory. |
| Initial custom MicroVM mount fixture | FAIL retained | Volume metadata reached AVAILABLE, but mount creation returned HTTP502. A separate owned runtime probe found no `ossfs2`; `/dev/fuse` and x86_64 existed. No mount/persistence pass is inferred from that fixture. |
| Owned OSS on eligible generation-1 runtime | PASS | Exact mount entry; exclusively created sentinel, fsync and read; first sandbox killed with404; fresh second sandbox reads persisted bytes; separate read-only Volume can read and refuses write. |
| Snapshot-origin mount override attempt | FAIL retained | An owned MicroVM snapshot containing verified ossfs2 was created; the backend rejected new mount overrides with HTTP400, `creating from a snapshot does not allow volume or mount overrides`. No mutation replay. |
| Owned MicroVM append mount and pause/resume | PASS | Only newly owned sandboxes were prepared with official ossfs2 2.0.10; SHA256 `72e864b8087d6f889c5017339c625154619f626bbc13c9afcb70403544ad9b70` verified. The documented append endpoint returned204. Exact mount, persisted sentinel, process and HTTP service memory token survived observed PAUSED state and reconnect. RW recreation and RO rejection also passed. |
| Maintained Provider Volume tests plus new standard RW/RO test | PASS | 3 passed in17.33 seconds against newly owned OSS/Volumes. The earlier standard-only run also passed, including explicit typed404 cleanup, in9.75 seconds. The existing Provider test's imported class was corrected to `ProviderSandbox`. |
| LangGraph1.2.17 session boundary | PASS, scoped | Same user/conversation reconnected the same real sandbox across turns. A distinct user with the same conversation name got another sandbox; file values remained separate. Both sandboxes independently absent after cleanup. No login/authentication boundary, model execution or durable multi-process framework checkpoint store is claimed. |
| SDK repository/preview/third-party MCP runner | PASS | 20 real checks: exact public Git commit, actual Node application, HMAC preview200, unsigned/tampered403, expired403, two pinned filesystem MCP versions, real initialize/14-tool discovery/read_file result385, logs, process cleanup and sandbox typed absence. Application signing is separate from provider gateway signing. |
| Earlier final-copy repository transfer | FAIL retained | GitHub clone transferred less than1 byte/sec for30 seconds. Sandbox cleanup passed. The runner now fetches the exact immutable commit, with at most two bounded read-only fetch attempts; the later complete run passed. |
| MCP two-manager regression before fix | FAIL as expected | 1 failed,1 passed. Borrower shutdown did not close its borrowed handle; the old implementation killed it. Explicit borrowed kill already passed. |
| First ownership-patch MCP unit suite | PASS, historical scope | 261 passed in8.07 seconds. This preceded the independent namespace/lifecycle adversarial review. |
| Independent namespace/lifecycle adversarial regressions | FAIL before correction | Six failures reproduced provider raw-ID collision, owned-handle replacement, alias replacement, create/connect completing after shutdown, and new work on an already closed manager. The separate reviewer additionally exercised a queued shutdown holding the real asyncio lock. |
| Task namespace/submission regressions | FAIL before correction | Cached non-default-provider task reuse, ambiguous bare-ID refusal and late-connect submission failed. An additional assertion exposed missing provider context in the returned task handle. |
| Final task/ownership affected MCP unit suite | PASS, historical scope | 270 passed in7.92 seconds. Canonical provider identity, aliases, late lifecycle completion, borrowed cleanup, explicit kill, task submission/reconnect, binary files and retention remain covered. |
| Maintained real-cloud MCP lifecycle suite, first ownership patch | PASS, historical scope | 3 passed in14.04 seconds. Borrower closes without killing the owner; owner shutdown then gives typed not-found. Namespace-patch repeat:3 passed in11.96 seconds. |
| Task/ownership maintained real-cloud MCP lifecycle suite | PASS, historical scope | 4 passed in19.49 seconds. Includes actual qualified task handle, owner disconnect, fresh-session status/log lookup, `beforeafter` stdout, succeeded state, exit0 and explicit final sandbox deletion. |
| Final resource verification regressions, before helper | FAIL as expected | Four scenarios/five parametrized cases fail: no independent resource read, mismatches accepted, unknown observation accepted, ambiguous cleanup not reported. |
| First resource-helper complete affected MCP suite | PASS, historical scope | 275 passed in7.92 seconds. Includes resource match, mismatch/new-only rollback, unknown metadata redaction, and failed-delete/readback reconciliation with a provider-qualified recovery ID. |
| First resource-helper real-cloud lifecycle/resource/task suite | PASS, historical scope | 5 passed in25.15 seconds. Includes matching actual CPU/memory and mismatch rollback, original sandbox preservation, independently confirmed not-found, plus owner/borrower/task cases. |
| Independent endpoint-context adversarial regression | FAIL before correction | After a regional delete timeout, the first helper read metadata through the default region and mistook that region's404 for deletion. A routing mock reproduces the false cleanup confirmation. |
| Frozen-endpoint affected MCP suite | PASS, historical scope | 279 passed in7.95 seconds. Resource cleanup freezes the actual instance's resolved provider/endpoint/region/credentials/options, builds a fresh control plane and reads the raw ID. Query not-found confirms absence; setup/close failures cannot. |
| Frozen-endpoint real-cloud suite | PASS, historical scope | 5 passed in25.88 seconds. Lifecycle, borrowed cleanup, retained tasks and explicit resource match/rejection run against the final helper. The separate before/after/matching campaign repeats successfully and independently confirms all4 new resources absent. |
| Final resource handle race regressions before correction | FAIL as expected | Two rollback cases selected a static default endpoint or a replacement cache handle after metadata awaited. Two initial-verification cases falsely accepted matching metadata from a default endpoint/replacement. |
| Final captured-handle affected MCP suite | PASS | 283 passed in8.10 seconds.13 resource cases include exact-handle verification and deletion across cache clearing/replacement, identity-guarded local disposal, frozen endpoint cleanup and target-query-only absence confirmation. |
| Final captured-handle real-cloud suite | PASS | 5 passed in23.68 seconds. Actual lifecycle, borrowed cleanup, retained task continuation, matching resource acceptance and mismatch cleanup. The separate before/after/matching campaign repeats successfully, preserving the original sandbox and independently confirming all4 owned resources absent. |
| Actual resource defect and corrected acceptance | PASS, before failure preserved | Base metadata is2 CPU/2048 MiB. Bypassing only the new helper reproduces the old false-success request3/2304 with actual2/2048. Restored helper accepts matching2/2048, rejects3/2304, reports independent cleanup true, preserves the existing sandbox and confirms all4 owned IDs absent. |
| Private v3 hosted HTTPS final acceptance | PASS, exact v3 artifact | 9 checks: missing private-ingress token403, bearer401, separate sessions/15tools, owned create/commands, same-credential borrowed access, borrower DELETE preserves owner, owner DELETE cleans, and retained task owner disconnect/fresh-session qualified-handle result/succeeded0/final kill.4 owned resources independently not-found. This is private source validation, not a public-a6 claim or a v4 whole-wheel HTTPS run. |
| Initial new task E2E assertion | FAIL retained | 3 passed,1 failed in18.56 seconds. The new test incorrectly expected `completed`; the existing task contract and actual backend returned `succeeded`. The assertion was corrected to that established contract; no runtime success/failure condition was weakened. |
| `make lint` | PASS | Both packages. Scoped new/changed Python files also pass Ruff; both modified Skills pass `quick_validate.py`. |
| `make format-check` | PASS | 92 server files and240 client files. The initial invocation lacked the venv PATH; the configured environment run passed. |
| `make typecheck` | PASS | 56 server files and100 client files; an existing unused mypy section note remains. |
| `make test` initial full server phase | FAIL retained | 872 passed,1 skipped,3 failed in316.53 seconds. The Make target stopped before the client phase. Two raw malformed-HTTP checks received501/502 instead of400. Package inventory lacked pytest because the fresh uv environment had no pip. |
| Focused server rerun after environment correction | PARTIAL | Installing pip26.2.2 in the test environment fixed inventory:1 passed. The two raw malformed-HTTP failures reproduce:2 failed in1.78 seconds. Their root cause is unconfirmed; server runtime was not changed or tests bypassed. |
| Complete client suite, first ownership patch | PARTIAL | 2317 passed,21 skipped,2 failed in133.04 seconds. Cube-through-engine mock RPC returned HTTP501 with `项目网络审计已关闭`; engine-restart follow-up returned502. No cloud account was involved. The fixture already clears inherited proxies; no audit bypass or unrelated runtime change was made. |
| Complete client suite, namespace/lifecycle patch | PARTIAL | 2323 passed,21 skipped,2 identical environment-blocked engine/mock failures in129.03 seconds. The final task/resource follow-ups are covered by the283-test affected suite and real5-test lifecycle/resource/task suite; a later full CI matrix remains required. |

The MicroVM append API was taken from the
[official append-Volume documentation](https://www.alibabacloud.com/help/zh/agent-sandbox/append-mount-volume):
`POST /sandboxes/{sandboxID}/fc-volume-mounts` with `namedVolumeMounts`.
It is a backend acceptance call, not a claim that a new shared Provider command
or Python convenience method was implemented. Runtime preparation follows the
[official OSS mount guide](https://www.alibabacloud.com/help/zh/agent-sandbox/mount-oss-volume-1)
and [RAM role guide](https://www.alibabacloud.com/help/zh/agent-sandbox/create-ram-role).

## Cleanup

Every storage fixture used a fresh private empty OSS bucket, fresh FC-trust RAM
role and custom policy limited to that one bucket, two fresh Volume definitions,
and tagged sandboxes with bounded TTLs. The tests never modified a borrowed bucket,
role, policy, template or Volume. Successful sandbox deletion was independently
checked with404/typed not-found. The uncertain initial502 create was reconciled
by its unique metadata over five reads; no owned sandbox remained. Volume lists
confirmed absence; owned objects, buckets, policy attachments, policies and roles
were removed. Source Snapshots and restored sandboxes were deleted separately.
The new pytest test independently removes only its verified exclusive sentinel,
then checks every tracked sandbox's typed not-found.

Final independent readback found all seven owned RAM roles, all seven policies and
all seven OSS buckets absent, with zero owned Volume definitions and zero tagged
owned sandboxes remaining. [Cleanup receipt](skill-storage-state/final-storage-cleanup.json).

The framework check records zero remaining sandboxes. Both failed and successful
repository/MCP-tool runs independently confirm the owned sandbox is absent. No
account credentials were placed in sandbox files, Issues, outputs or receipts.

## Receipts

Derived sanitized receipts are stored in [skill-storage-state](skill-storage-state/oss-pytest-final.json):

- [Generation-1 OSS persistence/RO](skill-storage-state/oss-gen1-persistence-ro.json)
- [MicroVM mounted memory/service resume](skill-storage-state/oss-microvm-mounted-resume.json)
- [Final maintained Volume pytest](skill-storage-state/oss-pytest-final.json)
- [Initial missing ossfs2 fixture](skill-storage-state/initial-microvm-missing-ossfs2.json)
- [Snapshot mount override rejection](skill-storage-state/snapshot-mount-override-rejected.json)
- [Original Snapshot `/tmp` diagnostic](skill-storage-state/snapshot-tmp-initial-diagnostic.json)
- [Owned-directory Snapshot diagnostic](skill-storage-state/snapshot-owned-directory-diagnostic.json)
- [Pre-Snapshot `/tmp` overwrite reproduction](skill-storage-state/source-tmp-overwrite.json)
- [LangGraph isolation](skill-storage-state/langgraph-session-isolation.json)
- [Earlier GitHub transfer failure](skill-storage-state/tools-github-transfer-failure.json)
- [Final exact-fetch/preview/MCP20 checks](skill-storage-state/tools-pinned-fetch-preview-mcp.json)

The first private client wheel has SHA256
`e392045f50b39fd3ba094dbbb6df16d687e47f4e912cbc4ca61ae42622c31587`;
its initial seven-check hosted HTTPS pass is historical evidence that predates the
independent identity/race findings. The namespace/lifecycle wheel has SHA256
`32841e230ebf8c2c1544fc75083225d2c0b30b1074c82d4ff0558782a6cd4c28`.
The v3 client wheel, including task namespace/submission corrections, has SHA256
`e6f803f0e367381f62e968d6103616b9be9c35ed9fc8772289b93ca41b3a6d43`.
Both ownership/task runtime modules were compared byte-for-byte against that v3 wheel.
The historical v4 client wheel first added the explicit-resource helper and its tools.py call;
its SHA256 is `4a1a6899fcc550471aac5b4a6eaec9d6fe357687ea75da0c56febaf62dad0906`.
Its endpoint-context cleanup defect was found independently before delivery.
The historical v5 client wheel has SHA256
`d2c7f1675d170c241634dadfd28e8fdfd8f5d941065dc212866eb590e8d1852c`.
Final parent/independent review found that ID-based first observation/rollback
could switch handles after session/cache changes. Intermediate v6 fixed rollback;
the final v7 fixes both by retaining the captured created handle. The final wheel
has SHA256 `cbd1710159090133099cfde61f2d17fe511ca730d47c74838218d105e7d36746`.
All four affected runtime modules match v7 byte-for-byte; mcp.py/tasks.py remain
byte-identical to the v3 hosted artifact. Final actual resource validation,
283 affected unit tests and5 real lifecycle/resource/task tests are separate
from the exact v3 transport campaign. No whole-wheel v7 hosted HTTPS run is claimed.
The unchanged matching server wheel has SHA256
`85b937438acf943b3d92736dd6a07c4829cd80416336da35c0b25f2e5679850d`.
These are private source-test artifacts bearing a6 metadata, not replacements for
immutable public a6 files. The recorded v3 hosted transport acceptance is exact-version evidence; any eventual
release must be recorded separately by the owning delivery.

- [Original public-a6 hosted failure](skill-storage-state/remote-mcp-public-a6-failure.json)
- [First source patch HTTPS pass, before red-team findings](skill-storage-state/remote-mcp-first-patch-pass.json)
- [Final v3 hosted HTTPS and retained-task pass](skill-storage-state/remote-mcp-v3-final-pass.json)
- [First CPU/memory verification pass, before endpoint review](skill-storage-state/mcp-explicit-resource-verification.json)
- [Frozen-endpoint CPU/memory pass, before handle-race review](skill-storage-state/mcp-resources-frozen-endpoint-final.json)
- [Final captured-handle CPU/memory before/after and cleanup](skill-storage-state/mcp-resources-captured-handle-final.json)

## Problems found

- [Issue #140](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/140): Python MCP accepted CPU/memory requests without confirming actual resources. The new helper checks independent metadata and rolls back only the unverified new sandbox. Missing/failed cleanup observations remain explicit recovery outcomes. The follow-up uses the created instance's frozen endpoint context and distinguishes query404 from initialization/close failures. Direct SDK creation is unchanged.

- [Issue #139](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/139): public-a6 Python MCP cached borrowed connections were implicitly destroyed on
  shutdown. The scoped source fix separates creation ownership from cached
  handles, using actual provider-qualified keys and closed-session guards. Tasks
  retain the actual provider in returned opaque handles; clients parsing raw IDs
  must update. This does not create a tenant authorization boundary.
- Direct sticky-`/tmp` SDK overwrite fails independently of Snapshots on the tested
  envd image; ordinary non-sticky workspace writes and Snapshot isolation pass.
- MicroVM source images need the documented ossfs2 prerequisite. A Snapshot restore
  cannot accept new mount overrides; it is not a rebuilt image template.
- A Provider Skill retained the CLI-rejected `templates.deploy` feature. It now
  uses the exact consumer-specific `template.prepare` operation guidance.
- The existing Provider Volume E2E imported root standard Sandbox for a
  Provider-only method; the import now explicitly names `ProviderSandbox`.

## Not verified

No blanket certification of all providers, storage types or accounts follows from
this OSS/Express run. Costs, budgets, native signed previews, external VM snapshot
import, full Agent model behavior and durable multi-worker framework state are
outside these particular receipts. Full server and client checks retain the failures above;
no CI pass, PR merge, deployment or new package publication is asserted here.
