# 内置沙箱数据通道

内置 `alicloud-express` 提供方直接使用 SDK 的 HTTP 传输：
`Sandbox.create` 请求平台，命令、文件和终端使用返回的 envd 地址及凭据。
create 和 connect 共用协议实现，不再依赖本机会话守护进程、gRPC socket、
`grpcio` 或 `protobuf` 包。

沙箱 ID、模板 ID/别名、元数据、资源、到期时间和 envd 版本均保留平台响应值。
envd0.5 的流请求使用原始 JSON，envd0.6 使用 Connect 封包。
沙箱 TTL 与创建请求的 HTTP 超时仍是两个独立参数。

```python
from agent_sandbox import Sandbox

async with await Sandbox.create("base", timeout=300, request_timeout=30) as sb:
    result = await sb.commands.run("echo ready")
    print(result.stdout)
```

按[认证指南](../guide/authentication.md)设置 `ABX_SANDBOX_API_KEY` 和实际平台地址/域名。
`close()` 释放本地 HTTP 连接并保留沙箱，`kill()` 销毁沙箱。
其他进程可以用 `Sandbox.connect(id)` 连接，无需原进程保留本机会话。
创建请求中断时远端结果可能未知，不能盲目重放写操作；应通过元数据核对自有资源。

## 从 Python 引擎切片迁移

试验性深层导入 `agent_sandbox.engine.Engine`、对应命令行模块和
`ABX_ENGINE_SOCKET` 已退役。改用 `Sandbox.create/connect`、`commands`、
`files` 和 `open_terminal`。旧 socket 不再参与请求。
单独管理的旧守护进程由其管理者停止；SDK 不删除其他进程的 socket 或销毁其资源。

已安装的 `node` 插件仍通过 `providers.engine_client`、`~/.abx/engine.json`
调用 CLI 的 **Node 引擎**。它与 EPP 进程适配器是独立且仍有效的契约，本次均保留。
见 [Node 引擎 API](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/reference/engine-api.md)。
[旧 Python 引擎](provider-engine.md)和[计划](provider-engine-plan.md)作为历史保留，不是安装指南。
