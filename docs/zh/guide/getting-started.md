# 快速开始

在自己的机器上安装 Client SDK，即可创建和使用沙箱。
[Server SDK](server-sdk.md) 用于运行沙箱镜像内的应用。
本文使用 Provider 扩展入口 `ProviderSandbox`。标准同步 `Sandbox` 和异步
`AsyncSandbox` 入口见 [E2B 迁移指南](migrate-from-e2b.md)。

## 1. 安装和配置

使用 Python 3.10 及以上版本，先按[安装指南](install-python.md)创建并激活虚拟环境，再安装：

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client==0.4.0a4'
python -m pip check
export ABX_SANDBOX_API_KEY='your-api-key'
```

按[智能体沙箱产品文档](https://help.aliyun.com/zh/functioncompute/product-overview-of-fc-agent-sandbox)
获取极速版沙箱 API Key。默认提供方为 `alicloud-express`，地域为 `cn-hangzhou`。
本项目各入口，包括标准 `Sandbox` / `AsyncSandbox` 和 `ProviderSandbox`，
均支持 `ABX_SANDBOX_API_KEY`、`ABX_SANDBOX_BASE_URL` 和 `ABX_SANDBOX_DOMAIN`，
项目配置统一推荐这些名称。Provider 扩展的 `sandbox_api_key=` 覆盖见
[认证指南](authentication.md)；标准入口保留其文档中的公开 `api_key=` 参数。

安装客户端会安装同版本的服务端发行包，但不会更新已有镜像内的服务端。
PyPI 上名为 `agent-sandbox` 的发行包是其他项目。可选依赖及源码开发安装见
[安装指南](install-python.md)。

## 2. 创建沙箱、执行命令和传输文件

保存为 `quickstart.py`，然后执行 `python quickstart.py`：

```python
import asyncio

from agent_sandbox import ProviderSandbox


async def main():
    async with await ProviderSandbox.create(template="base", timeout=300) as sandbox:
        print(f"Sandbox ID: {sandbox.id}")
        result = await sandbox.commands.run("printf 'Hello, Agent Sandbox!'")
        assert result.exit_code == 0
        print(result.stdout)

        path = "/home/user/note.txt"
        await sandbox.files.write(path, "Hello from Python!")
        assert await sandbox.files.read(path) == "Hello from Python!"
        await sandbox.files.download(path, "note.txt")
        await sandbox.files.upload("note.txt", "/home/user/copied-note.txt")
        assert await sandbox.files.read("/home/user/copied-note.txt") == "Hello from Python!"

    # 退出上下文时销毁自己创建的沙箱，出现异常也会清理。


asyncio.run(main())
```

`base` 提供命令和文件操作，不代表包含解释器或应用服务。原生命令可传入
`user="root"` 或其他已存在的系统账号，仅影响当前请求。

连接已有沙箱使用 `await ProviderSandbox.connect(sandbox_id)`。使用完调用
`await sandbox.close()` 释放客户端连接；仅在自己拥有沙箱生命周期时调用
`await sandbox.kill()` 删除实例。

## 3. 运行 Python 程序

在 `base` 上运行 Python 程序可直接使用命令执行：

```python
result = await sandbox.commands.run("python3 -c 'print(1 + 1)'")
assert result.exit_code == 0 and result.stdout.strip() == "2"
```

将这段代码放进第 2 步的上下文中。这是进程执行，不是解释器 API。极速版的结构化
解释器结果应通过标准 `agent_sandbox.code_interpreter` 入口获取，见
[E2B 迁移指南](migrate-from-e2b.md)；极速版 `ProviderSandbox` 适配器未实现解释器操作。

## 4. 启动模板应用

使用独立安装的 [abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox)
启动目录中的模板，执行模板声明的启动与就绪检查。如何调用应用 API 和清理自己
创建的资源见[模板启动指南](template-workflows.md)。创建普通 `base` 沙箱不会自动
启动模板应用。

## 下一步

模板构建辅助函数直接从已安装的本项目公开入口导入：
`from agent_sandbox import Template, AsyncTemplate, wait_for_port, default_build_logger`。
这些名称不需要另装 `e2b`；标准模板 API 仍有其文档规定的平台、账号前提和公开参数。

[2026-10-25 公开 a4 示例记录](../../../.agents/evidence/verify/2026-10-25-public-a4-examples.md)
区分了 14 个真实云端示例、本地协议夹具、超时控制和独立清理检查。
示例通过不代表整个模板目录都已验证。

- [SDK 用法](sdk-usage.md)：Provider 扩展及其同步封装。
- [声明式函数](declarative-usage.md)：将 Python 函数放到远程执行。
- [MCP 集成](mcp-integration.md)：连接 IDE 或 Agent。
- [故障排查](troubleshooting.md)：处理安装和运行错误。

## 相关：abx CLI

CLI 是独立的 Node.js 包 `@agent-sandbox/cli`。安装 Python 包不会安装 `abx`，
也不存在 Python `[cli]` extra。请按
[CLI 安装指南](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/binary-installation.md)操作。
