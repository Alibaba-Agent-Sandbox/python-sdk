# Client SDK

当前 SDK 安装使用[安装指南](install-python.md)。

Client SDK 跑在**你的机器**上。它创建沙箱、连上已经存在的沙箱，然后在沙箱里执行命令、读写文件、调用代码解释器。包名是 `agent-sandbox-client`，导入 `agent_sandbox`。

```bash
python -m pip install 'agent-sandbox-client==0.4.0a1'
python -m pip check
```

不要执行 `pip install agent-sandbox`。PyPI 上的 `agent-sandbox` 是另一个无关项目。

```python
from agent_sandbox import ProviderSandbox as Sandbox

async with await Sandbox.create(template="base") as sandbox:
    result = await sandbox.commands.run("echo hello")
    print(result.stdout)
```

沙箱镜像里那个 HTTP 服务不是这个包写出来的。镜像里跑的是 [Server SDK](server-sdk.md)（`agent-sandbox-server`）。Client SDK 通过 envd 和该服务的 HTTP 接口去用它。

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
