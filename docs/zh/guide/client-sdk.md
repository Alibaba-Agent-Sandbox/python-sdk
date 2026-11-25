# Client SDK

0.5 预览版的安装与运行时可选依赖见[安装指南](install-python.md)。

Client SDK 跑在**你的机器**上。它创建沙箱、连上已经存在的沙箱，然后在沙箱里执行命令、读写文件、调用代码解释器。包名是 `agent-sandbox-client`，导入 `agent_sandbox`。

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client==0.5.0a0'
python -m pip check
```

不要执行 `pip install agent-sandbox`。PyPI 上的 `agent-sandbox` 是另一个无关项目。

```python
from agent_sandbox import ProviderSandbox as Sandbox

async with await Sandbox.create(template="base") as sandbox:
    result = await sandbox.commands.run("echo hello")
    print(result.stdout)
```

[Server SDK](server-sdk.md)（`agent-sandbox-server`）是按需运行在沙箱内的 HTTP 应用。实例生命周期、命令、文件等 Provider 操作使用所选 Provider 的传输方式，并非全部经过 Server SDK。调用注册的业务命令，需要对应应用已经安装、启动并完成鉴权。

## 选择目标与客户端

| 任务 | Python 入口 | 目标与凭据 |
| --- | --- | --- |
| 创建或管理极速版、OpenSandbox 实例 | `ProviderSandbox.create()` / `ProviderSandbox.connect()` | Provider 模板/镜像或真实 Sandbox ID，以及该 Provider 的配置 |
| 调用已运行的 Server SDK 应用 | `ServerClient` | HTTP 服务 URL、应用令牌及所需的网关请求头 |
| 调用托管 Agents API 应用 | `httpx` 等 HTTP 客户端 | 统一 Gateway URL 与业务 bearer token，见[托管 Agents API](managed-agents-api.md) |

CLI 部署名称、Sandbox ID、HTTP URL、Agents Session ID 是不同的标识。`ProviderSandbox.connect()` 接收 Sandbox ID，不接收 URL 或 CLI 本地部署名称。`ServerClient` 不创建或销毁云实例。CLI 的 OpenAPI 绑定和别名不会自动变成 Python 方法；超出类型化客户端范围的 API 使用服务公开的 HTTP 接口。

`ProviderSandbox` 可以使用已配置的默认 Provider，也可以明确填写 `provider="alicloud-express"` 或 `provider="opensandbox"`。管理多个后端的 ID 时建议明确指定。它只选择后端，不转换 ID，也不使不同 Provider 的能力等价。各后端的地址、凭据和安装要求见[Provider 配置](providers.md)。

## 关闭正确的资源

`await sandbox.close()` 释放本机连接，远端沙箱继续运行。`await sandbox.kill()` 删除远端沙箱。`ProviderSandbox` 的异步上下文管理器退出时会尝试 `kill()`，通过 `connect()` 获得的实例也一样；借用已有沙箱时，使用 `try/finally` 和 `close()`。HTTP 客户端的 `aclose()` 只关闭传输连接。

Agents Session 有独立的关闭、取消、删除操作。请求被接收不等于任务完成，取消请求被接收不等于执行已停止。根据[托管 API](managed-agents-api.md) 返回的 Session、Submission 或 Operation 查询结果；传输超时不能作为换新幂等键重放任务的理由。

## 从这里开始

| 文档 | 做什么 |
|------|--------|
| [快速开始](getting-started.md) | 安装、配置、创建、执行、销毁 |
| [SDK 使用](sdk-usage.md) | `commands`、`files`、`run_code`、命名命令 |
| [认证配置](authentication.md) | API Key 与 AK/SK |
| [声明式用法](declarative-usage.md) | `@sandbox` 把函数丢进沙箱执行 |
| [云上端到端练习](cloud-examples.md) | 在默认提供方上跑示例 |
| [环境变量](environment-variables.md) | 创建时注入，以及沙箱内怎么读 |
| [会话持久化](session-persistence.md) | 进程退出后仍能按 id 连回去 |
| [提供方](providers.md) | 换一个沙箱后端 |
| [E2B 迁移](migrate-from-e2b.md) | 方法名相近的地方，以及不能直接替换的地方 |
| [MCP 集成](mcp-integration.md) | 把沙箱操作交给 IDE 里的 Agent |
| [命令与 SDK 对照](command-map.md) | 和 E2B、OpenSandbox 的命令对照 |
| [对比](comparison.md) | 和 E2B、Modal、Docker Sandbox 的定位 |
| [故障排查](troubleshooting.md) | 创建、认证、文件、命令失败时看这里 |

参考：[API 参考](../reference/api-reference.md)、[配置](../reference/configuration.md)、[错误码](../reference/error-codes.md)。

## 示例

这些脚本都在你的机器上运行，见 [示例目录](../../../examples/README.zh-CN.md#client-sdk-示例)：

- `examples/quickstart/` — 创建、文件、代码、`@sandbox`
- `examples/compat-demos/` — E2B 风格和 Modal 风格的调用
- `examples/agents/` — 调用已经打开的 Agents API，或在云上跑 Codex
- `examples/scenarios/agent_loop_local.py` — 本地拉起服务，再按创建、执行、读取、销毁走一遍
- `examples/templates/python-hello/call_api.py` — 对一个已经在听的模板服务器发 HTTP

要写进镜像、在沙箱里启动的代码见 [Server SDK](server-sdk.md)。
