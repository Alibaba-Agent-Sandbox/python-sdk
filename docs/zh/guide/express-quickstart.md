# Express 快速开始

安装[当前 Python 双包](install-python.md)和独立的
[abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/binary-installation.md)。
按 CLI 的[模板启动指南](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/using-templates.md)
配置极速版提供方；源码构建还需文档要求的 Docker 和镜像仓库配置。

## 启动应用

```bash
export ABX_SERVER_TOKEN='replace_me'
abx --provider alicloud-express template launch 'alibaba-agent-sandbox/awesome-templates//python-hello'
```

启动器准备提供方引用、创建沙箱、执行模板启动命令并检查声明的服务，不需要选择
workflow。保留返回的沙箱 ID 和清理说明。

## 从 Python 调用

将返回的标识写入 `SANDBOX_ID`，并保持相同的 `ABX_SERVER_TOKEN`。
`ABX_SANDBOX_API_KEY` 配置平台访问，与应用令牌分开。

```python
import asyncio
import os

from agent_sandbox import ProviderSandbox


async def main():
    sandbox = await ProviderSandbox.connect(
        os.environ["SANDBOX_ID"], provider="alicloud-express"
    )
    try:
        async with await sandbox.application_client(
            9000, token=os.environ["ABX_SERVER_TOKEN"]
        ) as client:
            result = await client.commands.run("hello", name="Python")
            print(result)
    finally:
        await sandbox.close()


asyncio.run(main())
```

这段代码借用 CLI 创建的沙箱并关闭连接。使用完毕后，按启动器的清理说明删除沙箱
及自己创建的构建资源。等价的 Python 预备引用启动方式及生命周期归属见
[模板启动指南](template-workflows.md)。
