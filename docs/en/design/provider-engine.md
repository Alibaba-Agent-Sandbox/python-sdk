# Provider engine

> **Status: superseded for catalog providers.** The current design is the Node engine: HTTP, SSE and WebSocket on `127.0.0.1`, protocol `abx-engine/1`. See [cli/docs/en/reference/engine-api.md](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/engine-api.md) and [Node provider architecture](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/node-provider-architecture.md). This page is the earlier Python gRPC record (`agent_sandbox.engine`, `engine.proto`, Unix socket `~/.abx/engine.sock`) and is kept as history. The built-in `alicloud-express` path in the Python SDK still calls this slice. Catalog providers do not.

Historical status: experimental slice, not the full data-plane migration. `Create` for Alibaba Cloud Express goes through the engine. The socket is mode `0600`, a live socket is reused, and `Exec` / `Terminal` accept loopback URLs only. Commands and files on an existing sandbox still use the SDK HTTP client. The rest of the plan is [provider-engine-plan.md](provider-engine-plan.md).

On this slice, SDKs do not open backend HTTP, SSE or WebSocket connections themselves. They dial a local gRPC service on a Unix socket (`~/.abx/engine.sock`, or `ABX_ENGINE_SOCKET`). The engine process holds those connections.

| SDK call | Engine RPC | What the engine speaks to the backend |
|---|---|---|
| `Sandbox.create` for `alicloud-express` | `Create` | HTTP `POST /sandboxes` |
| `Engine.exec_sse` | `Exec` | HTTP SSE, one data line per chunk |
| `Engine.terminal` | `Terminal` | WebSocket, bytes relayed on a bidirectional stream |

`python -m agent_sandbox.engine` serves the socket for any language that has a gRPC client. The Python SDK also starts that server in-process on first use.

```python
from agent_sandbox.engine import Engine

info = await Engine().create("base", api_key="...", api_url="https://...")
async for line in Engine().exec_sse("http://backend/events"):
    print(line)
reply = await Engine().terminal("ws://backend/pty", b"ping")
```
