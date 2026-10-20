# 提供方管理命令

提供方命令管理所选云后端拥有的资源，例如存储卷或自定义域名。它们与沙箱 shell 执行、
`agent-sandbox-server` 注册的具名命令分别使用独立入口。提供方可以声明自己的操作，
无需添加 CLI 顶层命令，也不会改变其他提供方的命令集合。

默认提供方不再声明 `storage.mount`、`ports.domain` 或 `network.vpc`：标准沙箱协议没有这些 token 对应的可调用操作。提供方资源管理通过已声明的命令完成；存储卷管理命令不代表支持运行中沙箱挂载。

## 创建沙箱时挂载已有 Volume

内置提供方的 `Sandbox.create()`（以及 `create_sync`）接受 `volume_mounts`：

```python
from agent_sandbox import ProviderSandbox as Sandbox

async with await Sandbox.create(
    provider="alicloud-express",
    template="my-template",
    volume_mounts={"/mnt/data": "existing-volume-name"},
) as sandbox:
    print(await sandbox.files.list("/mnt/data"))
```

字典表示“沙箱内绝对路径 → 已有 Volume **名称**”，不是 Volume ID。Volume 和 API Key
必须属于同一 Team，使用相同地域。OSS 应配置 Volume 的 RAM 角色；显式传入
`metadata["fc.sandbox.auth.role"]` 时以该角色为准。存储权限、模板与运行时前提和各存储类型
的限制见[官方挂载指南](https://help.aliyun.com/zh/agent-sandbox/mount-oss-volume-1)。
Volume 目前要求提交阿里云工单申请邀测，准备存储前应确认目标账号、地域和 Team
已开通，参见[官方 OSS Volume 指南](https://help.aliyun.com/zh/agent-sandbox/user-guide/create-oss-volume)。
成功返回空列表不能证明已有创建或挂载权限。
自定义 MicroVM 源镜像须预装 ossfs2 2.0.10 或以上版本；运行验收前，应选择满足
官方挂载指南中运行时前提的模板。

路径必须是规范化的绝对 Unix 路径，不能为 `/`，不能包含尾部分隔符、空段、隐藏目录段、
`.`/`..`、NUL 或前后空白。`/bin`、`/opt`、`/var`、`/dev` 及其子路径会被拒绝。
名称必须是非空字符串，不能包含前后空白或 NUL。无效参数会在构造提供方和引擎 I/O 前失败；
其他提供方的非空挂载参数会在加载插件实现前返回 E8004。省略参数或传空字典不改变原请求。

这是创建参数，与资源管理命令独立，不增加可移植的 `storage.mount` 协议或运行时追加挂载 API。
Python 内置生命周期仍通过本地 gRPC 引擎：新增的 `CreateRequest.volume_mounts` 传递字典，
由现有 Python 协议序列化为 `POST /sandboxes` 的
`"volumeMounts": [{"name": "existing-volume-name", "path": "/mnt/data"}]`。
非空参数会先检查 `Health.supported_create_options` 是否包含 `volume_mounts`；旧的运行中引擎
会在 `Create` 前返回 E8004 和升级、重启提示，不会自动替换引擎，避免旧 protobuf 实现静默
忽略挂载参数。未请求挂载的调用保留原行为。
提供方管理命令继续使用共享 Node HTTP 引擎。本地 gRPC/HTTP 回归覆盖参数链路，且已在
杭州地域的 base 模板完成真实 OSS 挂载、读写和清理验收。显式启用的 Volume E2E 套件还会检查
销毁并重建沙箱后数据是否保留。

## Python API

```python
from agent_sandbox.providers import commands

provider = "alicloud-express"
operations = await commands.list_commands(provider)
for operation in operations:
    print(operation["id"], operation["effect"], operation["input_schema"])
```

选择已声明的 `command_id` 并按 schema 构造 `payload` 后，使用
`await commands.get_command(provider, command_id)` 查看描述，使用
`await commands.run_command(provider, command_id, input=payload, confirm=False)` 调用。

这三个函数都是异步函数，必须明确指定提供方 ID。发现接口 `list_commands` 和 `get_command`
只接受 ID，不解析或转发凭据。调用接口 `run_command` 接受 `provider_options={...}` 及
`load_config` 支持的规范配置覆盖项，例如适用的 `sandbox_api_key`、`sandbox_base_url`、
`region` 和 `access_key_id`。解析后的连接与 URL 始终指定同一个提供方。只转发该提供方
声明的配置项及用户已同意继承的通用凭据。

`list_commands` 返回描述字典列表，`get_command` 返回单个描述，`run_command` 返回操作的
JSON 结果。调用前先阅读输入 schema。未知或不可用的操作遵循引擎的类型化错误契约，
不支持的命令包括 E8004。这些函数不会创建或连接沙箱。

写入和删除操作必须传 `confirm=True`，默认值是 `False`。应先审阅具体操作和资源标识，
再明确确认。引擎负责执行此要求；SDK 不会弹出交互式提示。

**SDK 绝不自动重试提供方命令的 POST**：即使描述声明幂等、连接断开或返回 HTTP 401，
也不会重放。如果响应丢失，应先查看提供方的实际资源状态，再决定是否重新调用。
`idempotent` 供调用方判断，不代表传输层可以自动重放。GET 发现接口保留现有引擎重连行为。

## Manifest 契约

只有 `node` 和 `exec` 插件可以声明非空命令集合。没有 `[commands]` 的旧 manifest
继续表示空集合。显式空区块必须包含 `protocol = "provider-commands/1"` 和
`entries = []`；`rest` 提供方可以使用这种形式。

```toml
[commands]
protocol = "provider-commands/1"

[[commands.entries]]
id = "volumes.list"
description = "List provider volumes"
description_zh = "列出提供方存储卷"
input_schema = { type = "object", properties = {}, additionalProperties = false }
output_schema = { type = "object" }
effect = "read"
idempotent = true
```

此例展示描述格式，不保证某个已安装提供方实现了 `volumes.list`。ID 遵循
`^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$`，最多 80 个字符；重复 ID 和未知描述字段会被拒绝。
两种语言的描述都是必填项。`effect` 为 `read`、`write` 或 `delete`；`idempotent` 必须明确
使用布尔值。最多声明 128 项，每项压缩 UTF-8 JSON 不超过 64 KiB，深度不超过 16。

Schema 使用 JSON Schema draft 7。输入根节点必须指定 `type = "object"` 和
`additionalProperties = false`，输出 schema 必须是对象。禁止 schema 引用、`$id`、
`$async`、`pattern`、`patternProperties` 和 `format` 作为 schema 关键字；名为
`format` 的业务属性仍然有效。所有深度均禁止 JSON 键
`__proto__`、`prototype`、`constructor`。只接受有限的 JSON 数值。Python 加载 manifest
时验证结构契约；Node 宿主进行最终严格 schema 编译，并验证输入和输出。
SDK 不重复实现云端业务逻辑或 schema 求值。

命令描述（包括 effect 和 schema）纳入安装确认摘要。更新时改变描述会要求重新确认。
旧安装回执若缺少 `commands`，视为空列表，未变更的旧插件不会因此多出风险差异。

## 引擎协议

共享本机引擎提供以下已鉴权路由：

| 方法 | 路由 | 结果或请求体 |
| --- | --- | --- |
| GET | `/v1/providers/:id/commands` | `{ "commands": [descriptor, ...] }` |
| GET | `/v1/providers/:id/commands/:command` | 单个描述 |
| POST | `/v1/providers/:id/commands/:command` | 请求体 `{ "input": {}, "confirm": false }`；返回命令结果 |

所有请求使用现有 bearer token 和 `X-Abx-Connection` 请求头。连接中的提供方必须与路由
一致。既有命令和 features 保持独立。`node` 插件从 `buildInfra` 返回
`provider_commands.run(commandId, input, signal)`；`exec` 插件分发 EPP
`provider.commands.run`，参数为 `{command, input}`。宿主只分发 manifest 声明的 ID；
缺少 handler 继续表示不支持。

实现和 CLI 命令入口由 CLI 仓库维护。参阅
[共享引擎规范](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/engine-api.md)
和[提供方架构](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/node-provider-architecture.md)。
需要将兼容的 `abx` 放入 `PATH`，或设置 `ABX_BIN`。旧引擎没有这些路由时无法执行提供方命令。
插件仍使用已文档化的宿主权限运行。

## Provider 实现一次，两端共同发现

公共宿主负责配置隔离、安装/授权、受限 JSON Schema 校验、引擎认证、错误和通用调度。
Provider 负责厂商 API 映射、认证、资源标识、服务准入、分页。CLI 展示和 Python 异步/类型
封装可以不同，不能在各端分别维护一套云端实现。

极速版是 CLI `src/providers/alicloud_express/` 中随包发布的内置 Provider；其他可安装
Provider 的源码属于 `awesome-providers`。现有 `provider-commands/1` 声明由通用 CLI 与
Python 引擎客户端共同发现。新增已声明操作不要求给各端再加调度表或顶层命令。
稳定的类型化方法仍是显式 API，不会因为注册了名字就动态生成 Python 方法，也不保证
每个后端都支持全部能力。标准 E2B 兼容客户端继续保留自己的协议契约。

极速版新增的注册命令如下：

| ID | 影响 | 输入 |
| --- | --- | --- |
| `sandbox.pause` | 写入 | `sandbox_id`，可选 `request_timeout` |
| `sandbox.resume` | 写入 | `sandbox_id`，可选生命周期 `timeout` |
| `snapshot.create` | 写入 | `sandbox_id`，可选 `name`、`request_timeout` |
| `snapshot.list` | 只读 | 可选 `sandbox_id`、`name`、`limit`、`next_token` |
| `snapshot.restore` | 写入 | `snapshot_id`，可选生命周期 `timeout`、字符串 `metadata` |
| `snapshot.delete` | 删除 | `snapshot_id` |

六个操作只使用所选极速版的 **sandbox API Key**、地址与地域，不要求控制面 AK/SK。
已有 Team/Volume/API-key/Quota 操作仍使用 AK/SK。完整输入限制见命令 Schema。
已实现与账号可用分开判断：暂停恢复和快照各需白名单，快照还要求二代运行时。
HTTP403/409 不能归为 Provider 未声明能力。原生 ProviderSandbox 特性标志保持独立范围；
注册命令不会暗中改变旧原生暂停/恢复协议。

```sh
abx --json provider command list alicloud-express
abx --json provider command info alicloud-express snapshot.create
abx --json provider command run alicloud-express sandbox.pause \
  --input '{"sandbox_id":"<sandbox-id>"}' --yes
abx --json provider command run alicloud-express sandbox.resume \
  --input '{"sandbox_id":"<sandbox-id>","timeout":600}' --yes
abx --json provider command run alicloud-express snapshot.create \
  --input '{"sandbox_id":"<sandbox-id>","name":"checkpoint","request_timeout":300}' --yes
abx --json provider command run alicloud-express snapshot.list \
  --input '{"sandbox_id":"<sandbox-id>","limit":100}'
abx --json provider command run alicloud-express snapshot.restore \
  --input '{"snapshot_id":"<returned-snapshot-uuid>","timeout":300}' --yes
abx --json provider command run alicloud-express snapshot.delete \
  --input '{"snapshot_id":"<returned-snapshot-uuid>"}' --yes
```

Python 通过真实本地引擎调用同一份注册实现：

```python
import asyncio
from agent_sandbox.providers import commands

async def main():
    catalog = await commands.list_commands("alicloud-express")
    print([entry["id"] for entry in catalog])
    # 本地配置 ABX_SANDBOX_API_KEY、ABX_SANDBOX_BASE_URL、ABX_SANDBOX_DOMAIN。
    result = await commands.run_command(
        "alicloud-express", "snapshot.create",
        {"sandbox_id": "<sandbox-id>", "request_timeout": 300}, confirm=True,
    )
    print(result["snapshot_id"])

asyncio.run(main())
```

须使用含有上述声明的 `abx` 构建，可以用 `ABX_BIN` 指定；原始 v0.4.0 发布物尚未包含这次
注册。单独升级 Python 不能让旧引擎凭空增加命令。发现操作不访问云端或检查云凭据，
列出的是已注册实现，不是实时账号能力探测。

创建快照默认请求超时300秒，与沙箱生命周期不同；Provider 外层截止时间360秒。
不自动重试写入。结果不确定时，先按本轮独占源沙箱查询，再决定是否重复创建。
`next_token` 原样传递服务分页游标。恢复会创建新沙箱，不恢复或替换源沙箱；需要在
异常后盘点时，为新沙箱传入唯一 `metadata`。先清理克隆沙箱，再独立删除快照，源沙箱
终止不会自动删除快照。

极速版删除快照使用与模板共用的服务接口。本注册扩展只接受**返回的快照 UUID**，在
发请求前拒绝普通模板名称和别名。结果不包含会话访问 token 或未声明的后端字段。
不提供仅保留文件系统的 `keep_memory=False` 暂停模式。

Python 仓库的手动验收控制器通过两端访问同一个真实 Provider，验证内存/文件连续性、
克隆隔离及自有资源清理；不新增云端/模型 Actions 验收。官方限制：
[暂停恢复](https://help.aliyun.com/zh/agent-sandbox/pause-and-resume)、
[快照](https://help.aliyun.com/zh/agent-sandbox/snapshot-invited-test)。
