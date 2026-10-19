# 本地极速版暂停与快照验收

凭据保留在被忽略的本地配置中。原生项目入口读取 ABX_SANDBOX_API_KEY、
ABX_SANDBOX_BASE_URL、ABX_SANDBOX_DOMAIN；标准入口还映射 E2B_API_KEY、
E2B_API_URL、E2B_DOMAIN。不要把极速版密钥发给其他提供商。
官方模板操作另需 ALICLOUD_ACCESS_KEY_ID、ALICLOUD_ACCESS_KEY_SECRET，
运行时 API Key 不能代替控制面授权。

## 已实现的接口与服务准入

极速版已提供暂停/恢复和 Snapshot；需要先开通对应账号/地域的白名单。Snapshot 还要求二代 MicroVM 运行时。不能因为默认模板或某次账号调用失败，就把整个服务标记为“不支持”。

| 操作 | Python 标准入口（同步） | CLI 标准入口 |
| --- | --- | --- |
| 暂停 | `sandbox.pause()` | `abx sandbox pause "$SANDBOX_ID"` |
| 恢复同一个沙箱 | `Sandbox.connect(sandbox_id)` | `abx sandbox resume "$SANDBOX_ID"` |
| 创建快照 | `sandbox.create_snapshot(name="checkpoint", request_timeout=300)` | `abx sandbox snapshot create "$SANDBOX_ID" --name checkpoint` |
| 快照列表 | `Sandbox.list_snapshots(sandbox_id=sandbox_id)`，通过分页器读取 | `abx sandbox snapshot list "$SANDBOX_ID" --format json` |
| 从快照新建沙箱 | `Sandbox.create(template=snapshot.snapshot_id)` | `abx create "$SNAPSHOT_ID" --detach` |
| 删除快照 | `Sandbox.delete_snapshot(snapshot.snapshot_id)` | `abx sandbox snapshot delete "$SNAPSHOT_ID"` |

上表 Python 使用 `from agent_sandbox import Sandbox`；异步使用 `AsyncSandbox` 并 await 相应操作。它们是标准 SDK 入口，不能与 `agent_sandbox.api.sandbox.Sandbox` 的原生 Provider/Server 扩展入口混为一谈，也不能把原生提供方的特性门禁当成极速版标准 API 的服务能力结论。Python 命名为 `create_snapshot`，TypeScript 命名为 `createSnapshot`；参数形式以实际 SDK 版本为准。

```python
import os
from agent_sandbox import Sandbox

sandbox = Sandbox.create(template=os.environ["E2E_PAUSE_TEMPLATE"], timeout=600)
try:
    sandbox.files.write("/tmp/checkpoint.txt", "before-pause")
    sandbox.pause()  # 需白名单
    sandbox = Sandbox.connect(sandbox.sandbox_id)
    assert sandbox.files.read("/tmp/checkpoint.txt") == "before-pause"
finally:
    sandbox.kill()
```

快照创建请求建议 `request_timeout=300`，它与沙箱生命周期 `timeout` 不同。只能对运行中的沙箱创建；同名同 tag 冲突时服务会失败，不会覆盖已有快照。只有文件系统的 `keep_memory=False` 暂停方式暂不支持。自动暂停/恢复使用 `lifecycle={"on_timeout": "pause", "auto_resume": True}`，同样受白名单限制。

快照独立于源沙箱存续，源沙箱 kill 后仍须单独删除快照；先清理从快照创建的沙箱以释放占用。保存创建返回的 Snapshot ID，删除时使用该 ID 或完整名称，避免误用短名。创建超时后按源沙箱查询并核对已有结果，不盲目重试。

本仓库已有真实二代模板验收记录：
[历史验证](../../../.agents/evidence/verify/2026-10-19-conditional-acceptance.md)。它是已有运行结果，不是本次文档修改重新执行的结果。

官方说明：[兼容 API](https://help.aliyun.com/zh/agent-sandbox/e2b-sdk-compatible-api-list)、[暂停与恢复](https://help.aliyun.com/zh/agent-sandbox/pause-and-resume)、[Snapshot 邀测](https://help.aliyun.com/zh/agent-sandbox/snapshot-invited-test)。

## 设计与前置条件

暂停/恢复和快照分别选择测试模板。优先创建隔离的二代 MicroVM 模板；
暂停/恢复需白名单；快照需二代 MicroVM 及相应白名单。
构建或准入错误应如实记录，不能归因为缺少本地 API Key。
官方公共镜像无需本地 Docker 构建，也不需要私人仓库凭据。

## 创建独立模板

选择与运行时密钥相同的地域和 Team，TEAM_ID 从本地配置获取。
名称必须唯一且不超过36字符。在具有标准入口的 CLI 检出中执行现有项目扩展：

```bash
REGION=cn-hangzhou
NAME="conditional-$(date +%s)"
abx template from-image \
  "fc-e2b-registry.${REGION}.cr.aliyuncs.com/runtime-v2/base:v0.0.53" \
  --name "$NAME" --team-id "$TEAM_ID" --region "$REGION" \
  --generation 2 --cpu 2 --memory 2048 --disk-size 15360 --no-envd-inject
abx template info "$TEMPLATE_ID"
```

创建结果提供 TEMPLATE_ID。构建是异步操作，轮询 info 直到 ready。
已有原生 CLI 构建以 `template create` 注册镜像模板，须先检查安装版本的帮助。
不传 --force，不修改已有模板。

## 执行与校验

通过本地环境选择模板，不提交真实值：

```bash
export E2E_PAUSE_TEMPLATE="$TEMPLATE_ID"
export E2E_SNAPSHOT_TEMPLATE="$TEMPLATE_ID"
```

SDK 测试校验仅保存在 Python 进程内存中的随机标记、文件、暂停状态、恢复连接、
快照列表、恢复、克隆隔离和删除。暂停状态与快照索引具有最终一致性。
暂停、恢复或快照转换期间删除可能返回409，仅针对已知转换进行有时限的等待。
创建快照超时后不能盲目重试，应按本次独占的源沙箱查询结果。
本次服务对重复删除仍返回204，因此用列表中不存在确认删除，不假设第二次返回 false。

## 清理与证据

先删除恢复和源沙箱，再删除被占用的快照。只清理本轮创建的资源，独立确认不存在后，
用 `abx template delete "$TEMPLATE_ID" --yes` 删除本轮模板。
记录源代码/二进制 SHA、真实通过/失败/跳过和遗留资源数，不记录密钥、账号标识和私人地址。
不向 Actions 上传凭据，不新增或分发云端/模型验收工作流。

[官方模板配置](https://help.aliyun.com/zh/agent-sandbox/build-and-manage-custom-templates-with-code)、
[兼容边界](https://www.alibabacloud.com/help/en/agent-sandbox/e2b-compatibility-explanation)、
[快照限制](https://help.aliyun.com/zh/agent-sandbox/snapshot-invited-test)。

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
