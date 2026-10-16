# 提供方管理命令

提供方命令管理所选云后端拥有的资源，例如存储卷或自定义域名。它们与沙箱 shell 执行、
`agent-sandbox-server` 注册的具名命令分别使用独立入口。提供方可以声明自己的操作，
无需添加 CLI 顶层命令，也不会改变其他提供方的命令集合。

默认提供方不再声明 `storage.mount`、`ports.domain` 或 `network.vpc`：标准沙箱协议没有这些 token 对应的可调用操作。提供方资源管理通过已声明的命令完成；存储卷管理命令不代表支持运行中沙箱挂载。

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
