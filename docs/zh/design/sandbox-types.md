# 沙箱生命周期与资源归属

本页说明当前 ProviderSandbox 生命周期，不定义额外的持久化/休眠 SDK 类型或全局清理服务。
标准 `Sandbox` / `AsyncSandbox` 保留独立的[标准合同](../guide/migrate-from-e2b.md)。

## 创建自己负责的沙箱

创建 `base` 获得平台命令/文件环境，不会启动模板应用，也不自动代表解释器、PTY、
持久化存储等条件能力。以下完整示例负责自己创建的沙箱：

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

上下文管理器在代码完成或抛出异常时销毁此沙箱。安装与账号配置见
[开始使用](../guide/getting-started.md)，实际签名见 [SDK 用法](../guide/sdk-usage.md)。
超时是资源/命令配置，不是跨平台通用的计费或数据保留承诺。

## 连接已有沙箱

`await ProviderSandbox.connect(sandbox_id)` 连接已有实例。`close()` 释放本地连接，
`kill()` 删除远程沙箱；只删除自己负责生命周期的资源。借用实例时完成后关闭客户端，
让资源所有者负责删除。客户端断开或最后一个进程退出，不意味着 SDK 自动清理全账号的孤儿资源。

## 模板应用与解释器

模板应用先走 CLI 统一启动流程和就绪检查，再使用令牌调用解析出的应用服务，见
[模板启动](../guide/template-workflows.md)。仅提供一个熟悉的平台模板名，不会自动启动服务。

结构化解释器使用标准 `agent_sandbox.code_interpreter` 入口及其文档规定的模板前提；
极速版 ProviderSandbox 不实现解释器操作。

## 条件平台能力

暂停/恢复、快照和持久化存储取决于具体 Provider、平台和账号，以当前平台文档及精确操作
合同为准。SDK 不承诺跨平台通用的持久化/休眠模式、免费存储、固定启动时间或保留期，
也没有公开的 `Config.set(...)` 全局清理策略。本页不提供未来模式参数或推测的生命周期 API。
