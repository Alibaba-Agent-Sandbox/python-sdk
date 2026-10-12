# Agents API — `ebx` CLI 必须跟进的规格

`ebx` CLI 现位于 Node/TypeScript 仓库（`/workspace/cli`），本工作流**没有**修改它。本文件是给 CLI 团队的规格。
设计上下文：[agents-api.md](../../en/design/agents-api.md)。
英文版为准：[../../en/design/agents-api-cli-followups.md](../../en/design/agents-api-cli-followups.md)。

CLI 应当是沙箱所暴露 HTTP 接口（Responses 线路与原生 `/agents/**` 路由）之上的轻量客户端，因此**不需要 Python**，也不需要了解适配器。所有路由都要求目标服务端启用 `agents` 能力组（默认禁用）。

## 1. 命令接口

```
ebx agent host start   <sandbox-id> [--port 9100] [--install] [--agent agent.yaml]...
ebx agent host stop    <sandbox-id>
ebx agent host status  <sandbox-id>               # GET /agents/health + /agents/runtimes
ebx agent runtimes     <sandbox-id>               # GET /agents/runtimes (installed, version, experimental)
ebx agent install      <sandbox-id> <runtime>     # POST /agents/runtimes/{name}/install
ebx agent doctor       <sandbox-id> [name]        # POST /agents/runtimes/{name}/doctor + definition validation
ebx agent define       <sandbox-id> agent.yaml    # PUT /agents/definitions/{name}  (YAML→JSON client side, ${VAR} expanded from the local env)
ebx agent list         <sandbox-id>               # GET /agents/definitions
ebx agent run          <sandbox-id> <agent|runtime> "<prompt>" [--session ID | --continue] [--stream] [--json] [--timeout 1800]
ebx agent sessions     <sandbox-id> [list|get ID|cancel ID|delete ID]
ebx agent logs         <sandbox-id> <session-id> [--follow] [--after SEQ]   # GET /v1/agents/sessions/{id}/events (SSE)
ebx agent openai-env   <sandbox-id> --remote-url URL --environment-id ID    # runs `codex exec-server`, key via env OPENAI_EXECUTOR_API_KEY
```

`<sandbox-id>` 的解析方式与其他所有 `ebx sandbox …` 命令相同。
未先执行 `host start` 时，`ebx agent run` 应自动启动 host（幂等），除非给出 `--no-bootstrap`。

## 2. 传输细节

* 端点 URL：`https://{port}-{sandbox_id}.{domain}`（沿用现有的端口 URL 规则）。
  认证：发送沙箱访问头（`X-Access-Token`），**并且**对 agents 路由再发送 `Authorization: Bearer <host token>`；`ebx agent host start`
  打印并保存 host 令牌（钥匙串或 `~/.config/ebx/agent-hosts.json`，模式 0600；除非 `--show-token`，否则绝不回显）。
* `host start` 与 Python 客户端的引导步骤相同：
  1. 当 `python3 -c "import easy_sandbox.server.agents"` 失败时，执行 `pip install easy-sandbox-server==<matching version>`；
  2. 以环境变量 `EBX_SERVER_TOKEN=<random>` 与 `EBX_AGENTS_ALLOW_INSTALL=1` 启动 `python3 -m easy_sandbox.server.agents serve --port 9100`
     （**只放环境变量，绝不放 argv**）；
  3. 等待 `GET /health`。
* 流式：Responses SSE（`stream: true`）——把 `response.output_text.delta` 作为文本打印；`--json` 把原始事件打印为 JSON 行。用
  `GET /v1/responses/{id}?stream=true&starting_after=<last sequence_number>` 重连。
* 取消：Ctrl-C → `POST /v1/responses/{id}/cancel`，然后以退出码 130 结束。

## 3. 配置与密钥

* `agent.yaml` 的 schema 即设计文档（[agents-api.md](../../en/design/agents-api.md)）第 4 节。CLI 用本地环境展开 `${VAR}`，变量未设置时报错（点名该变量），并且**绝不打印密钥值**（`--verbose` 显示 `***`）。
* 密钥只在 TLS 上的 `PUT /agents/definitions` 请求体中发送。
* `ebx agent define --lock` 应打印服务端 `EBX_AGENTS_LOCK_DEFINITIONS=1` 的提示；CLI 自己不设置它。

## 4. 退出码

| 码 | 含义 |
|---|---|
| 0 | 回合 `completed` |
| 1 | 回合 `failed`（打印错误码：`authentication_error`、`rate_limit_exceeded`、`request_timeout`、`runtime_not_installed` 等） |
| 2 | CLI 用法 / 配置错误（含未设置的 `${VAR}`） |
| 3 | host 不可达 / `agents` 能力组已禁用（404 "is disabled"） |
| 124 | `--timeout` 到期（CLI 先取消该 response） |
| 130 | 被中断（response 已取消） |

## 5. 涉及的 MCP / 现有命令

* `ebx mcp`（沙箱 MCP server）可以暴露三个工具：`agent_run`、`agent_cancel`、`agent_sessions`，实现在同一批路由上。
* `ebx sandbox port-url` 应提供 `--bearer`，在现有头之外打印 `Authorization: Bearer …`（便于官方 `openai` 客户端：`OPENAI_BASE_URL=<url>/v1`，`OPENAI_API_KEY=<host token>`）。
* `ebx agent run --openai-compat` 为已启动的 host 打印 `OPENAI_BASE_URL`/`OPENAI_API_KEY` 的 export。
* `--json` 摘要行的 JSON 输出 schema：
  `{"response_id","session_id","status","output_text","usage":{…},"error":null|{"code","message"}}`。

## 6. CLI 仓库应添加的测试

* 用桩 HTTP 服务回放 `server-sdk/tests/test_server/fixtures/agents/*.sse` 中的 SSE 记录，做退出码黄金测试。
* 测试 `--verbose` 绝不打印密钥值，且任何被拉起进程的 argv 上都不出现密钥。
