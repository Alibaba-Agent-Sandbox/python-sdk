# SDK API 设计

本页描述当前异步 `ProviderSandbox` 的 Provider/server 扩展。根入口
`Sandbox` / `AsyncSandbox` 和 `agent_sandbox.code_interpreter` 是独立的标准接口约定，
见[从 E2B 迁移](../guide/migrate-from-e2b.md)。本页是当前能力概览，不是新增 API 提案。

## 设计原则

- ProviderSandbox 创建、操作沙箱。源码镜像准备属于 CLI：通常使用
  `abx template launch <reference>`；build/deploy 是高级操作。标准 Template 构建器
  保留其独立接口约定。
- Shell 命令、解释器执行和模板应用命令有不同入口与前提。创建 `base` 不会启动应用。
- Provider 声明和真实账号决定可用操作；有同名方法不代表所有平台都实现了它。
- 公开签名、类型化错误和明确的资源归属约束接口。

## 范式一：命令式

以下完整程序在极速版 `base` 执行命令、读写文件。使用自己账号文档规定的 ABX
环境配置。上下文管理器在异常时也会销毁本程序创建的沙箱。

```python
import asyncio

from agent_sandbox import ProviderSandbox


async def main():
    async with await ProviderSandbox.create(template="base", timeout=60) as sandbox:
        result = await sandbox.commands.run("printf 'Hello, Agent Sandbox!'")
        assert result.exit_code == 0
        print(result.stdout)
        path = "/home/user/data.csv"
        await sandbox.files.write(path, "name,age\nAlice,30\nBob,25\n")
        assert await sandbox.files.read(path) == "name,age\nAlice,30\nBob,25\n"


asyncio.run(main())
```

结构化解释器使用标准 `agent_sandbox.code_interpreter` 入口及其文档规定的
`code-interpreter-v1` 前提；极速版 ProviderSandbox 不实现解释器操作。
生命周期与同步封装见 [SDK 用法](../guide/sdk-usage.md)，子客户端遵循各自公开签名。

## 范式二：声明式装饰器

已有 `@sandbox` 在准备好的远程运行环境中执行函数，默认负责资源清理；明确保留或复用
沙箱时遵循对应生命周期约定。包、解释器与序列化前提见[声明式用法](../guide/declarative-usage.md)。
SandboxServer 可通过已有 `@sandbox.register` 或 server 命令注册机制注册函数，注册不会
自动产生平台能力。

## 三种叫「命令」的东西

| 操作 | 入口 | 前提 |
| --- | --- | --- |
| Shell 进程 | `sandbox.commands.run(...)` | Provider 进程能力 |
| 注册的应用命令 | 应用客户端 `commands.run(...)` | 运行中的 SandboxServer 服务及应用令牌 |
| 注册命令发现 | 应用客户端 `commands.list()` | 同一运行中的服务 |

先用 `abx template launch <reference>` 启动完整模板，再根据返回的沙箱信息，通过
`application_client(..., token=...)` 保留 Provider 网关头和应用认证。见
[模板启动](../guide/template-workflows.md)与[模板 server API](../guide/template-server-api.md)。
仅用熟悉的模板名创建普通平台沙箱，不会执行这一启动流程。

规范 5 通过 `provides`、`start_cmd` / `ready_cmd` 声明服务；不使用旧模板
`capabilities` 列表来保证运行能力。

## 运行 Agent

沙箱内 Agents API 的 `/v1/agents/**` 使用已配置的 Agent adapter。先在模板中安装、
配置对应 Agent CLI，再按 [Agents API 指南](../guide/agents-api.md)调用。
本地协议夹具与真实模型调用是不同的验证范围。

## 配置

项目平台配置使用 `ABX_SANDBOX_API_KEY`、`ABX_SANDBOX_BASE_URL`、`ABX_SANDBOX_DOMAIN`。
ProviderSandbox 单次覆盖使用 `sandbox_api_key`、`sandbox_base_url`、`sandbox_domain`。
标准客户端保留独立有效的 `api_key` 接口约定。优先级和 Provider 专有配置见
[配置参考](../reference/configuration.md)，不能仅凭可选字段名推断平台能力。

## Sandbox 核心 API

完整签名以 [API 参考](../reference/api-reference.md)和 [SDK 用法](../guide/sdk-usage.md)为准。
原生生命周期、命令/文件客户端、网络解析和应用客户端与标准解释器 API 是不同入口。
PTY 等条件能力需要对应 Provider 和真实平台支持。`close()` 释放连接；`kill()` 删除资源，
只应用于自己负责生命周期的沙箱。

## 错误

Provider 错误派生自 `SandboxError`，携带 `code`、`message`、`suggestion`、`docs_url`；
标准客户端保留独立的异常约定。以下完整程序捕获真实进程超时
`CommandTimeoutError`（E3001），在 `finally` 删除自有沙箱，即使删除报错也会关闭连接。

```python
import asyncio

from agent_sandbox import ProviderSandbox
from agent_sandbox.models.errors import CommandTimeoutError


async def main():
    sandbox = await ProviderSandbox.create(template="base", timeout=60)
    try:
        await sandbox.commands.run("sleep 100", timeout=5)
    except CommandTimeoutError as error:
        print(error.code)  # E3001
    finally:
        try:
            await sandbox.kill()
        finally:
            await sandbox.close()


asyncio.run(main())
```

完整类型见[错误码](../reference/error-codes.md)，不要导入不存在的通用 SDK `TimeoutError`。

## SDK 不提供的能力

Python ProviderSandbox 不构建、推送源码镜像，也不直接按自然语言创建沙箱；使用 CLI
现有 launch/scaffold/create 指南。没有全局 `Config.set(...)` 自动清理策略或兼容别名。
使用明确的自有资源清理和 Provider 实际支持的超时能力。
