# 命令与 SDK 对照

本文对应当前源码的 CLI 入口。Python 标准 `Sandbox` / `AsyncSandbox`、跨提供方 `ProviderSandbox` 和应用 HTTP 客户端是不同入口，方法不能混用。已安装发行版的命令以其 `--help` 为准。

| 任务 | CLI | ProviderSandbox / Python |
| --- | --- | --- |
| 获取和编写模板 | `abx template list / info / init` | `—` |
| 构建可复用产物 | `abx template build SOURCE --yes` | `—` |
| 发布源码版本 | `abx template publish SOURCE --tag VERSION --yes` | `—` |
| 部署源码应用 | `abx deploy SOURCE --name APP --yes` | `—` |
| 从原生模板创建 | `abx deploy --template-id TEMPLATE --name APP --yes` | `await ProviderSandbox.create(template=..., provider=...)` |
| 查询和删除 | `abx list; abx status APP; abx delete APP --yes` | `await sandbox.refresh_info(); await sandbox.kill()` |
| 执行命令 | `abx sandbox exec APP -- COMMAND` | `await sandbox.commands.run(command)` |
| 调用注册函数 | `abx sandbox command run APP FUNCTION --arg key=value` | `await sandbox.run(name, **kwargs)` |
| 列出注册函数 | `abx sandbox command list APP` | `await sandbox.list_commands()` |
| 原生 Provider 操作 | `abx provider command list PROVIDER; abx provider run OPERATION` | `agent_sandbox.providers.commands` |

CLI 的本机部署名称不等于云端沙箱 ID。先用 `abx status APP` 获取真实 ID，再通过 `ProviderSandbox.connect(id, provider=...)` 连接相同提供方。`close()` 只关闭客户端；创建者负责删除远端资源。托管应用通过自身 HTTP API 使用，不能当作单个 Sandbox 调用。

[标准客户端迁移](migrate-from-e2b.md) · [应用连接与认证](template-workflows.md) · [模板编写](authoring-templates.md)
