# 阿里云智能体沙箱容器版

容器版的 sandbox-manager 运行在 ACS 或 ACK 集群中。使用包含内置 `alicloud-container` 的 Python Client SDK 源码版，可以直接访问集群。CLI 通过自己的 [Node Provider](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/tree/main/alicloud-container) 准备 SandboxSet 等资源。[English](../../en/design/provider-alicloud-container.md)

## 安装 Client SDK

在包含容器版内置 Provider 的源码目录运行 `python -m pip install ./client-sdk`。PyPI 上的 `0.4.0a7` 尚未包含这个 Provider。

## 连接集群

配置集群 sandbox-manager 的 API Key，并至少提供域名或管理 API 地址之一。运行示例前，准备同一集群中已注册的 SandboxSet。

| 配置 | 环境变量 |
| --- | --- |
| 集群网关域名 | `ABX_ALICLOUD_CONTAINER_DOMAIN` |
| 显式管理 API 地址 | `ABX_ALICLOUD_CONTAINER_BASE_URL` |
| 集群 sandbox-manager API Key | `ABX_ALICLOUD_CONTAINER_API_KEY` |
| 网关路由方式 | `ABX_ALICLOUD_CONTAINER_PROTOCOL`，默认为 `native`，也可填 `private` |

`native` 的默认管理地址为 `https://api.{domain}`，沙箱端口地址为 `https://{port}-{id}.{domain}`。`private` 的默认管理地址为 `https://{domain}/kruise/api`，沙箱端口使用 `/kruise/{id}/{port}` 路径。显式私有管理地址必须以 `/kruise/api` 结尾，源站及该路径前的前缀也用于数据面。管理 Key 用于集群 API，沙箱网关及 envd 使用会话返回的令牌。

```python
import asyncio

from agent_sandbox import ProviderSandbox


async def main():
    sandbox = await ProviderSandbox.create(
        provider="alicloud-container",
        template="base",  # 替换为集群中已有的 SandboxSet 名称
    )
    try:
        result = await sandbox.commands.run("printf container")
        print(result.stdout)
        await sandbox.files.write("/tmp/container-demo.txt", result.stdout)
        print(await sandbox.files.read("/tmp/container-demo.txt"))
    finally:
        await sandbox.kill()


asyncio.run(main())
```

## 在已有解释器上下文中运行 Python

如果 SandboxSet 在 `49999` 端口提供 Jupyter 服务，可以在示例的 `try` 块内调用以下接口。默认上下文在多次调用间保留，`run_code` 收集服务输出后返回执行结果。

```python
result = await sandbox.run_code("print(42)", mode="default-context")
print(result.stdout)
```

## 显式绑定集群

服务需要自行传入集群配置时，可使用 [`ProviderClient`](../guide/provider-runtime.md)。将 `ProviderLock(provider="alicloud-container", version=...)` 中的版本设为已安装的 `agent-sandbox-client` 版本，通过 `TransportConfig.provider_options` 传入 `api_key`、`domain` 或 `base_url`，需要时添加 `protocol`。锁与 SDK 内置实现匹配时会直接加载该实现。

## 支持范围

客户端使用已注册的 SandboxSet，支持实例生命周期、租期调整、命令及流式输出、进程、文件和网关端口访问。暂停和恢复取决于集群配置。`connect()` 可能恢复实例或延长租期。`close()` 释放本机连接，`kill()` 删除实例。列表每次返回一页，支持 1–100 条及 `running`、`paused` 过滤。

独立解释器上下文、解释器实时回调、PTY、文件监视、实例规格覆盖以及卷和网络配置暂未接入。创建或修改 SandboxSet 的步骤见[阿里云集群配置指南](https://help.aliyun.com/zh/agent-sandbox/quick-start1/)。内置 Python Provider 仍处于预览阶段。
