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
| 执行命令 | `abx exec APP -- COMMAND` | `await sandbox.commands.run(command)` |
| 调用业务操作 | `abx sandbox APP OPERATION [OPTIONS]`（已绑定 OpenAPI） | `await sandbox.run(name, **kwargs)`（已注册的服务端函数） |
| 发现业务操作 | `abx sandbox APP --help`（已绑定 OpenAPI） | `await sandbox.list_commands()`（运行中的服务端注册表） |
| 原生 Provider 操作 | `abx provider command list PROVIDER; abx provider run OPERATION` | `agent_sandbox.providers.commands` |

CLI 的本机部署名称不等于云端沙箱 ID。先用 `abx status APP` 获取真实 ID，再通过 `ProviderSandbox.connect(id, provider=...)` 连接相同提供方。`close()` 只关闭客户端；创建者负责删除远端资源。托管应用通过自身 HTTP API 使用，不能当作单个 Sandbox 调用。

CLI 的操作名和参数来自目标绑定的 OpenAPI 合同，不必与 Python 函数名相同。注册服务端函数不会自动为 CLI 建立绑定；Python 的命令发现查询运行中的服务端，并受其授权策略控制。详见 [CLI API 指南](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/sandbox-api.md)。

[标准客户端迁移](migrate-from-e2b.md) · [应用连接与认证](template-workflows.md) · [模板编写](authoring-templates.md)
