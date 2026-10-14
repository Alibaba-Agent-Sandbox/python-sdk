# Provider 引擎

> **状态：对目录提供方已被取代。** 现行设计是 Node 引擎：`127.0.0.1` 上的 HTTP、SSE 和 WebSocket，协议 `abx-engine/1`。见 [cli/docs/zh/reference/engine-api.md](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/reference/engine-api.md) 和 [Node 提供方架构](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/design/node-provider-architecture.md)。本页是较早的 Python gRPC 记录（`agent_sandbox.engine`、`engine.proto`、Unix socket `~/.abx/engine.sock`），作为历史保留。Python SDK 里内置的 `alicloud-express` 路径仍会调用这个切片。目录提供方不会。

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
