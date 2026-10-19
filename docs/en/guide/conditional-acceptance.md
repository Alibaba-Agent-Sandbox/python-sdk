# Local Express pause and snapshot acceptance

Keep credentials in ignored local configuration. Native project commands read
ABX_SANDBOX_API_KEY/BASE_URL/DOMAIN; the standard entry additionally maps
E2B_API_KEY/API_URL/DOMAIN. Never send an Express key to another provider.
Official template operations separately need ALICLOUD_ACCESS_KEY_ID and
ALICLOUD_ACCESS_KEY_SECRET; a runtime key cannot replace that authorization.

## Design and prerequisites

Pause/resume and snapshot tests use separate selectors. Prefer an isolated
MicroVM generation2 fixture. Generation1 pause may need enablement; snapshots
require MicroVM and account/region access. Provisioning or admission errors remain
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
[snapshot limits](https://help.aliyun.com/zh/functioncompute/snapshots).

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
