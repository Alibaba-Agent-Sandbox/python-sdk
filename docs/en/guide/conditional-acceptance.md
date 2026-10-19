# Local Express pause and snapshot acceptance

Keep credentials in ignored local configuration. Native project commands read
ABX_SANDBOX_API_KEY/BASE_URL/DOMAIN; the standard entry additionally maps
E2B_API_KEY/API_URL/DOMAIN. Never send an Express key to another provider.
Official template operations separately need ALICLOUD_ACCESS_KEY_ID and
ALICLOUD_ACCESS_KEY_SECRET; a runtime key cannot replace that authorization.

## Implemented interfaces and backend admission

Express supports pause/resume and Snapshot after the corresponding account/region allowlist is enabled. Snapshot additionally requires a generation2 MicroVM runtime. Failure on a default template or a particular account does not establish that the service lacks these features.

| Operation | Standard synchronous Python entry | Standard CLI entry |
| --- | --- | --- |
| Pause | `sandbox.pause()` | `abx sandbox pause "$SANDBOX_ID"` |
| Resume the same sandbox | `Sandbox.connect(sandbox_id)` | `abx sandbox resume "$SANDBOX_ID"` |
| Create a snapshot | `sandbox.create_snapshot(name="checkpoint", request_timeout=300)` | `abx sandbox snapshot create "$SANDBOX_ID" --name checkpoint` |
| List snapshots | `Sandbox.list_snapshots(sandbox_id=sandbox_id)`, consume the paginator | `abx sandbox snapshot list "$SANDBOX_ID" --format json` |
| Create from a snapshot | `Sandbox.create(template=snapshot.snapshot_id)` | `abx create "$SNAPSHOT_ID" --detach` |
| Delete a snapshot | `Sandbox.delete_snapshot(snapshot.snapshot_id)` | `abx sandbox snapshot delete "$SNAPSHOT_ID"` |

Python examples use `from agent_sandbox import Sandbox`; asynchronous callers use `AsyncSandbox` and await the appropriate operations. These standard clients are distinct from the native Provider/Server extension at `agent_sandbox.api.sandbox.Sandbox`. A native provider feature gate is not a statement that the Express standard API is unavailable. Python spells the method `create_snapshot`; TypeScript uses `createSnapshot`, with argument shapes determined by the installed SDK version.

```python
import os
from agent_sandbox import Sandbox

sandbox = Sandbox.create(template=os.environ["E2E_PAUSE_TEMPLATE"], timeout=600)
try:
    sandbox.files.write("/tmp/checkpoint.txt", "before-pause")
    sandbox.pause()  # requires allowlist admission
    sandbox = Sandbox.connect(sandbox.sandbox_id)
    assert sandbox.files.read("/tmp/checkpoint.txt") == "before-pause"
finally:
    sandbox.kill()
```

Use `request_timeout=300` for snapshot creation; sandbox lifetime `timeout` is a different setting. Snapshot creation requires a running source. Same-name/same-tag conflicts fail without overwriting an existing snapshot. Filesystem-only pause via `keep_memory=False` is currently unavailable. Automatic pause/resume uses `lifecycle={"on_timeout": "pause", "auto_resume": True}` and remains subject to allowlisting.

Snapshots outlive their source sandbox and must be deleted separately after killing any restored sandboxes that occupy them. Keep the returned Snapshot ID; delete by that ID or a returned qualified name rather than a short name. After an ambiguous create timeout, reconcile existing results by the owned source sandbox before retrying.

This repository already records real generation2 acceptance in its [historical verification](../../../.agents/evidence/verify/2026-10-19-conditional-acceptance.md). It is historical execution evidence, not a new run performed for this documentation change.

Official references: [compatible APIs](https://help.aliyun.com/zh/agent-sandbox/e2b-sdk-compatible-api-list), [pause/resume](https://help.aliyun.com/zh/agent-sandbox/pause-and-resume), and [Snapshot invited test](https://help.aliyun.com/zh/agent-sandbox/snapshot-invited-test).

## Design and prerequisites

Pause/resume and snapshot tests use separate selectors. Prefer an isolated
MicroVM generation2 fixture. Pause/resume requires allowlisting; snapshots additionally
require a generation2 MicroVM runtime. Provisioning or admission errors remain
failures, not evidence that a local API key is absent. The public-image fixture
needs no local Docker build or private registry credentials.

## Provision a uniquely named fixture

Choose the same region/Team as the runtime key. Set REGION and TEAM_ID from local
configuration; NAME must be unique and at most36 characters. From a checkout with
the standard CLI entry use this existing project extension:

```bash
REGION=cn-hangzhou
NAME="conditional-$(date +%s)"
abx template from-image \
  "fc-e2b-registry.${REGION}.cr.aliyuncs.com/runtime-v2/base:v0.0.53" \
  --name "$NAME" --team-id "$TEAM_ID" --region "$REGION" \
  --generation 2 --cpu 2 --memory 2048 --disk-size 15360 --no-envd-inject
abx template info "$TEMPLATE_ID"
```

The create result supplies TEMPLATE_ID. Poll info until build state is ready;
creation is asynchronous. Accepted native CLI builds use `template create` for
this image-registration operation; inspect installed help before choosing it.
Do not pass --force or update existing templates for this test.

## Run and verify

Use local environment selectors without committing their values:

```bash
export E2E_PAUSE_TEMPLATE="$TEMPLATE_ID"
export E2E_SNAPSHOT_TEMPLATE="$TEMPLATE_ID"
```

The SDK suite verifies a nonce held only in a running Python process, files,
paused-state observation, connect/resume, snapshot list/restore, clone isolation
and deletion. Paused-list and snapshot indexing are eventually consistent.
Deletion may return409 during pausing/resuming/snapshotting; wait for that known
transition only, with a deadline. Do not retry snapshot creation after an ambiguous
timeout: reconcile snapshots by the uniquely owned source sandbox first.
This backend returned204 even on repeated snapshot deletion, so assert list
absence rather than expecting a second delete to return false.

## Cleanup and evidence

Delete restored/source sandboxes before their occupied snapshot. Delete only
resources created by this run. Verify exact resource absence after cleanup, then
remove the owned fixture with `abx template delete "$TEMPLATE_ID" --yes`.
Record source/artifact SHA, actual passes/failures/skips, admission errors and
owned residual count; omit keys, account identifiers and private endpoint details.
Do not upload credentials or dispatch cloud/model acceptance in Actions.

[Official template setup](https://help.aliyun.com/zh/agent-sandbox/build-and-manage-custom-templates-with-code),
[compatibility](https://www.alibabacloud.com/help/en/agent-sandbox/e2b-compatibility-explanation),
[snapshot limits](https://help.aliyun.com/zh/agent-sandbox/snapshot-invited-test).

## SDK test / SDK 测试

```bash
cd e2e
python -m pytest test_standard_contract.py -q -ra
```

E2E_PAUSE_TEMPLATE independently selects pause and can fall back to the snapshot
fixture. E2E_SNAPSHOT_TEMPLATE selects snapshot restoration. Conditional skips
never count as passes. Provisioning and CLI artifact verification belong to
[CLI40](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/40).
E2E_PAUSE_TEMPLATE 独立选择暂停模板，也可回退到快照模板；
E2E_SNAPSHOT_TEMPLATE 选择快照恢复模板。未配置时基础场景仍执行，条件性跳过不算通过。
