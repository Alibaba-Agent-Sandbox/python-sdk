# Provider engine: plan and adversarial verification

> **Status: superseded for catalog providers.** The current design is the Node engine: HTTP, SSE and WebSocket on `127.0.0.1`, protocol `abx-engine/1`. See [cli/docs/en/reference/engine-api.md](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/engine-api.md) and [Node provider architecture](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/node-provider-architecture.md). The gRPC-on-a-Unix-socket proposal below is kept as history.

Status: plan, produced by a three-way review on 2026-10-14. The experimental slice is [provider-engine.md](provider-engine.md). Chinese: [provider-engine-plan.md](../../zh/design/provider-engine-plan.md).

As of that review, shipped behavior differed from the proposal below: the gRPC engine created `alicloud-express` only. OpenSandbox was the catalog plugin `awesome-providers/opensandbox` and spoke HTTP from the plugin process. Catalog providers now run as `node` modules on the Node engine.

| Role | Result |
|---|---|
| Proposal | One local engine. SDKs dial gRPC on a Unix socket. The engine holds HTTP, SSE and WebSocket. Both `alicloud-express` and OpenSandbox are in-engine adapters. |
| Attack | The current slice has four blockers: an empty credential falls back to the engine process environment, a daemon thread unlinks a live socket, `Exec`/`Terminal` are open SSRF, and commands and files still bypass the engine after create. |
| Live check | pytest: 13 passed. `Exec` and `Terminal` connect to caller-supplied URLs. With umask 0 the socket is mode `0777` and `nobody` can call `Exec`. A second process replaces the listening socket inode. |

**Verdict: the current slice is not a production path for Alibaba Cloud Express.** The plan below includes the fixes those findings require.

## 1. Decision

SDKs (Python, the CLI, and later languages) see only three shapes: one request, one server stream, one bidirectional stream. Backend HTTP, SSE and WebSocket exist only inside the engine.

stdin/stdout `exec` plugins no longer carry files, SSE or terminals. `rest` remains an HTTP adapter inside the engine for backends that already speak the platform API. OpenSandbox is an in-engine adapter. It does not start `node ./provider.mjs`.

The in-sandbox server SDK does not select a provider and does not start the engine.

## 2. Process

- One process per socket. Default `~/.abx/engine.sock`. `ABX_ENGINE_SOCKET` must be an absolute path. `host:port` is rejected. A path longer than 108 bytes fails. The engine does not listen on TCP.
- `~/.abx` is mode `0700`. The process sets `umask 077` before bind and `chmod 0600` on the socket after bind. A client that sees group or other access refuses to connect.
- `Health` first. If it succeeds, attach and do not delete the socket. If it fails, spawn `python -m agent_sandbox.engine` under a file lock. Unlink-then-bind is not allowed.
- Production is a detached child, not a daemon thread that dies with the parent. pytest, or `ABX_ENGINE_INPROCESS=1`, starts the engine in-process so existing tests can still patch `SandboxProtocol`.
- Exit after `ABX_ENGINE_IDLE_SECONDS` idle (default 900). After a crash, retry only idempotent RPCs once (`Health`, `Get`, `List`, `Kill`). Do not retry `Create` or any stream.
- `Health.protocol` must be `abx.engine.v1`. A mismatch is a hard error that tells the user to restart the engine.

## 3. Protocol

The SDK puts already-resolved config in `Creds`. The engine does not read `config.toml` and does not fill missing secrets from its own environment. A missing `api_key` or backend URL fails the RPC.

Credentials live only in RPC memory and on that socket. `envd_access_token` and execd headers stay inside the engine. Later data-plane RPCs carry `sandbox_id` only.

Unary: `Health`, `Create`, `Connect`, `Get`, `List`, `Kill`, `SetTimeout`, `Pause`, `Resume`, `PortUrl`, `ExecRun`, file metadata, `ProcessSignal`, `CodeExecute`.

Server stream: `ExecStart` (raw bytes, not base64), `FileRead` (64 KiB chunks), `WatchDir`.

Bidi: `FileWrite` (first frame carries the path, later frames are bytes, one chunk in flight), `Terminal` (`OPEN` / `DATA` / `RESIZE` / `SIGNAL` / `CLOSE` / `EXIT`).

Cancelling an RPC closes the matching HTTP stream or WebSocket. Queues are bounded (4). A full queue stops the upstream read.

Errors carry trailer `abx-error-code`. Python maps them back to the existing exceptions (401 → `E1001`, sandbox 404 → `E2009`, timeout → `E3001`). Do not use `or` to treat `0` as unset. Use `optional` fields so zero and absent stay different.

The current `Exec(sse_url)` and URL-bearing `Terminal` survive only until the last migration step, and only for loopback URLs. Production calls do not pass URLs.

## 4. Alibaba Cloud Express

The adapter calls the existing `SandboxProtocol`, `ProcessProtocol` and `FilesystemProtocol`. It does not invent a second JSON shape.

- Create stays `POST /sandboxes`. The body still comes from `SandboxConfig.to_create_payload()`.
- Command streams use envd Connect (`application/connect+json`). The engine decodes once. The SDK receives raw bytes.
- File bytes use envd `/files`, 64 KiB at a time, not a JSON line.
- The terminal rewrites `envd_url` to `wss` and uses `/terminal`. The engine holds that WebSocket.

`Sandbox.create` and `connect` for the built-in provider send only RPCs. The returned object does not keep a private `HttpClient` that skips the engine for commands and files. Tests that inject a mock protocol keep that path.

## 5. OpenSandbox

An in-engine module. It does not start the installed Node plugin. File bytes do not leave the engine as `content_b64`.

Lifecycle is OpenSandbox HTTP. Commands are execd SSE. Files are execd upload and download. The terminal is the execd WebSocket. The `0x00` frame prefix is stripped inside the engine before the SDK sees the bytes.

The first slice returns `E8004` for file watch, signed URLs, stdin, code, template build, and listing processes by name.

## 6. Install store

`~/.abx/providers` stays. A `rest` plugin can still be installed. The engine reads the manifest and speaks HTTP. It does not execute files in the plugin directory.

A new `exec` install fails with `E8010` and the fixed message `exec providers cannot carry files, SSE or WebSocket; install refused`. An already installed exec plugin is marked `disabled` and is not spawned. `opensandbox` is a built-in id. An install directory with that name is ignored.

## 7. Migration order

After every step, the three existing engine tests stay green, and the cloud create body is still produced by `to_create_payload()`.

1. `Health`, file lock, modes `0700`/`0600`, and no unlink of a live socket. Old RPC behaviour stays.
2. Old `Exec` and `Terminal` accept loopback URLs only.
3. Add the new RPCs. Old fields keep their defaults.
4. Move the built-in lifecycle onto the engine.
5. Move built-in commands, files and the terminal onto the engine. `tests/test_protocol` still calls the protocol classes directly.
6. Point the CLI at the same socket.
7. OpenSandbox adapter. Tests assert there is no `content_b64`.
8. Refuse new exec installs.
9. Delete the URL-bearing RPCs and retarget the three tests. Keep the same assertions.

## 8. Not in the first slice

No Go or Java SDK. No non-Python engine binary. No Windows named pipe. The in-sandbox server on port 9000 is not proxied. A dropped terminal stream is not resumed. The engine does not read config files. EPP source files stay until a later slice. This slice stops calling them and refuses install.
