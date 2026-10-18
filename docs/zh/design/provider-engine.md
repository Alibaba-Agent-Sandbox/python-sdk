# Provider 引擎

> **状态：已退役的 Python gRPC 历史设计。** 内置提供方现使用[直接 HTTP](builtin-data-plane.md)，目录 Node 插件使用独立的 [Node 引擎](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/reference/engine-api.md)。下文示例是历史记录，不再是受支持的命令。

历史状态：试验切片，数据面还没有全部迁完。阿里云极速版的 `Create` 走引擎。套接字是 `0600`，活着的套接字会复用，`Exec` / `Terminal` 只接受回环地址。已经建好的沙箱上，命令和文件仍由 SDK 自己的 HTTP 客户端发送。其余步骤见 [provider-engine-plan.md](provider-engine-plan.md)。

在这个切片上，SDK 自己不去连后端的 HTTP、SSE 或 WebSocket。它们拨一个本机 Unix socket 上的 gRPC 服务（`~/.abx/engine.sock`，或 `ABX_ENGINE_SOCKET`）。引擎进程握着那些连接。

| SDK 调用 | 引擎 RPC | 引擎对后端使用的协议 |
|---|---|---|
| `alicloud-express` 的 `Sandbox.create` | `Create` | HTTP `POST /sandboxes` |
| `Engine.exec_sse` | `Exec` | HTTP SSE，每个 data 行一块 |
| `Engine.terminal` | `Terminal` | WebSocket，字节走双向流 |

`python -m agent_sandbox.engine` 会把这个 socket 提供给任何有 gRPC 客户端的语言。Python SDK 在第一次使用时也会在进程内启动它。

```python
from agent_sandbox.engine import Engine

info = await Engine().create("base", api_key="...", api_url="https://...")
async for line in Engine().exec_sse("http://backend/events"):
    print(line)
reply = await Engine().terminal("ws://backend/pty", b"ping")
```
