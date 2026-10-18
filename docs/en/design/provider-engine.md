# Provider engine

> **Status: retired historical Python gRPC design.** The builtin provider now uses [direct HTTP](builtin-data-plane.md). Catalog Node plugins use the separate [Node engine](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/reference/engine-api.md). The examples below are historical and are no longer supported commands.

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
