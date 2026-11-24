# 阿里云智能体沙箱容器版

容器版的 sandbox-manager 运行在 ACS 或 ACK 集群中。使用包含内置 `alicloud-container` 的 Python Client SDK 源码版，可以直接访问集群。CLI 通过自己的 [Node Provider](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/tree/main/alicloud-container) 准备 SandboxSet 等资源。[English](../../en/design/provider-alicloud-container.md)

## 连接集群

| 配置 | 环境变量 |
| --- | --- |
| 集群数据面域名 | `ABX_ALICLOUD_CONTAINER_DOMAIN` |
| 选填的管理 API 地址 | `ABX_ALICLOUD_CONTAINER_BASE_URL` |
| 集群 sandbox-manager API Key | `ABX_ALICLOUD_CONTAINER_API_KEY` |
| 路由方式 | `ABX_ALICLOUD_CONTAINER_PROTOCOL`，默认 `native`，也可填 `private` |

`native` 通过 `https://api.{domain}` 管理沙箱，通过 `https://{port}-{id}.{domain}` 访问沙箱端口。`private` 的管理路径为 `/kruise/api`，数据路径为 `/kruise/{id}/{port}`。显式填写私有管理地址时，SDK 使用它的源站和路径前缀。管理 Key 只发送给集群管理接口，访问沙箱时使用会话返回的网关及 envd 令牌。

```python
import asyncio

from agent_sandbox import ProviderSandbox


async def main():
    sandbox = await ProviderSandbox.create(
        provider="alicloud-container",
        template="code-interpreter",  # 替换为集群中已有的 SandboxSet 名称
    )
    try:
        result = await sandbox.commands.run("printf container")
        print(result.stdout)
        code = await sandbox.run_code("print(42)", mode="default-context")
        print(code.stdout)
    finally:
        await sandbox.kill()


asyncio.run(main())
```

## 能力与限制

支持实例生命周期、租期、命令、进程、文件以及网关访问。暂停与恢复取决于集群配置，`connect()` 可能恢复实例或延长租期。`close()` 释放本机连接，`kill()` 删除实例。列表支持 1–100 条及 `running`、`paused` 过滤。

`run_code(..., mode="default-context")` 需要 SandboxSet 在 49999 端口提供 Jupyter。支持持久默认上下文及其 NDJSON 输出。独立执行上下文、实时回调、PTY、文件监视、实例规格覆盖、卷配置和网络配置暂未接入。

使用已注册的 SandboxSet 启动实例。创建或修改 SandboxSet 需要集群权限。内置 Python Provider 仍处于预览阶段。[官方容器版配置](https://help.aliyun.com/zh/agent-sandbox/quick-start1/)
