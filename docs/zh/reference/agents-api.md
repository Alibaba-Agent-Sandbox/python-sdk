# Agents API 参考

沙箱服务端在 `agents` 能力组打开之后提供的全部 HTTP 接口。组默认关闭。目前支持 **Codex**（二进制 `codex`）和 **Qwen Code**（二进制 `qwen`）。目前未支持的适配器名称，包括 Claude Code、Cursor 和 Qoder，返回 404。

这不是 `sb.agent.*`。用法和案例见 [Agents API](../guide/agents-api.md)。字段级拒绝的叙述见 [托管代理](../guide/hosted-agents.md)。本页按路由列出参数和响应。

路由定义在 `server-sdk/src/easy_sandbox/server/routes_agents.py`。

## 通用约定

打开这一组：

```bash
export EBX_SERVER_ENABLED_GROUPS=agents
python -m easy_sandbox.server serve --port 9000
```

| 项 | 值 |
|---|---|
| 基址 | `http://<host>:9000`。OpenAI 风格客户端用 `base_url=http://<host>:9000/v1` |
| 请求体 | `Content-Type: application/json`，对象。空 body 当成 `{}` |
| 令牌 | 设置了 `EBX_SERVER_TOKEN` 时，这些路由接受 `X-Access-Token` 或 `Authorization: Bearer`。其他路由只接受 `X-Access-Token` |
| 本地标记 | 每个响应，包括错误，都有响应头 `X-Easy-Sandbox-Local: 1`。成功对象带 `x_easy_sandbox`。`compute` 是 `local_process`、`local_state` 或 `none`，不会是 `openai_hosted` |
| 所有者 | 有策略时是身份 id，否则是 `local`。别人的 id 和不存在的 id 得到同样的应答 |

错误信封：

```json
{
  "error": {
    "message": "说明",
    "type": "invalid_request_error",
    "param": "字段名或 null",
    "code": "agents.not_implemented_locally"
  }
}
```

`type` 在 404 时是 `not_found_error`。做不到的变体是 **400**，`x-should-retry: false`。没有本地能力的路由是 **404**，`code` 为 `agents.not_implemented_locally`，`x-should-retry: false`。组关闭时路径 404，正文说明路由已禁用。

列表信封（凡是下表写「列表」的）：

| 查询参数 | 含义 |
|---|---|
| `limit` | 整数 1–100，默认 20。超出是 400 `invalid_request`，`param=limit` |
| `order` | `asc` 或 `desc`，默认 `desc`。其他值 400 |
| `after` | 上一页最后一条的 `id`。不在当前序列里是 404 `agents.cursor_not_found` |

```json
{
  "object": "list",
  "data": [],
  "first_id": null,
  "last_id": null,
  "has_more": false
}
```

会话对象 `agent.session` 的主要字段：`id`、`object`、`agent`（`id`、`name`、`model`、`instructions`、`tools`、`multi_agent.enabled`、`reasoning`、`service_tier`、`text`）、`created_at`、`environment`（`type=self_hosted`、`id`、`workspace_directory`）、`status`、`metadata`、`usage`、`vault_ids`、`error`、`required_actions`、`last_active_at`、`x_easy_sandbox`。

适配器选择顺序：请求头 `X-EBX-Adapter`，或正文 `adapter` / `runtime`，或 `agent.model` / `model` 恰好是 `codex`、`openai-codex`、`qwen-code`、`qwen`、`qwen_code`、`qwencode`。`gpt-5` 这种模型 id 会传给被选中的 CLI，不用于选择适配器。都没有时用产品顺序里的第一个：`codex`。`EBX_AGENTS_DEFAULT` 或 `EBX_AGENTS_CONFIG` 里的 `default` / `agents.default` 可以改这个默认。`GET /v1/agents/runtimes?order=asc` 按 `codex`、`qwen-code` 列出。列表默认 `order=desc`。`default: true` 标出当前默认，不看数组下标。其他名字 404 `agents.not_implemented_locally`。每个路由都可以单独放行，端点 id 的默认 scope 是 `agents:use`，见[细粒度能力](../guide/fine-grained-capabilities.md)。

CLI 不在基础镜像里。要用时再装：

```bash
npm install -g @openai/codex
npm install -g @qwen-code/qwen-code
```

## 会话、事件、条目、回合

### `POST /v1/agents/sessions`

创建会话。成功 **200**，body 是 `agent.session`。

| 字段 | 位置 | 说明 |
|---|---|---|
| `agent` | body | 对象。`model` 为适配器名或要传给 CLI 的模型 id。`instructions` 可选 |
| `agent_id` | body | 已保存定义的 id。给出时不再从 `model` 选适配器 |
| `adapter` / `runtime` | body 或 `agent` 内 | 显式适配器名 |
| `input` | body | 可选。字符串，或带 `input_text` 的消息。有内容则立刻排队一轮 |
| `metadata` | body | 字符串标量的对象。嵌套对象、数组、`null` 是 400 |
| `environment` | body | `{ "type": "self_hosted", "id": "env_..." }` 可选 |
| `vault_ids` | body | 可选，字符串数组 |
| `X-EBX-Adapter` | header | 可选 |

`environment.type` 固定为 `self_hosted`。`workspace_directory` 默认 `/workspace`。

### `GET /v1/agents/sessions`

列表。查询参数除分页外还有 `agent_id`（按定义 id 过滤）。成功 **200**，列表，元素是 `agent.session`。

### `GET /v1/agents/sessions/{id}`

路径参数 `id`。成功 **200**，一个 `agent.session`。不存在 **404** `resource_not_found`。

### `POST /v1/agents/sessions/{id}`

只更新 `metadata`。body 里出现 `agent`、`vault_ids`、`environment` 或其他键是 **400**。成功 **200**，更新后的 `agent.session`。

### `DELETE /v1/agents/sessions/{id}`

删除会话，并清掉产物快照。成功 **200**：

```json
{ "id": "agsess_...", "object": "agent.session.deleted", "deleted": true, "x_easy_sandbox": {} }
```

### `POST /v1/agents/sessions/{id}/events`

排队一轮。成功 **202**，**空 body**。

| 字段 | 说明 |
|---|---|
| `events` | 非空数组。元素是对象 |
| `events[].type` | `agent.session.input.message` 或 `input.message`：取 `input` / `content` / `text`。`agent.session.input.cancel` 或 `input.cancel`：取消。`tool_result` 和 `computer_use_approval_request_result` 是 400 `agents.tool_result_unsupported`。其他 type 是 400 |
| `input` | 没有 `events` 时，可直接给一条输入 |
| `Idempotency-Key` | 可选头。相同键加相同 body 重放这个 202。相同键加不同 body 是 **409** `idempotency.mismatch` |

`input_image`、`input_file` 是 400。进行中再送输入会排成新回合（`queued_not_steered`），不会写进正在跑的进程。

### `GET /v1/agents/sessions/{id}/events`

SSE。`Accept: text/event-stream`。查询 `after`：不带则从现在开始跟踪，直到该回合结束；`after=0` 或 `after=evt_<seq>` 回放后关闭。帧的 `id` 是运行时序号。

### `GET /v1/agents/sessions/{id}/items`

### `GET /v1/agents/sessions/{id}/turns`

### `GET /v1/agents/sessions/{id}/turns/{turn_id}`

### `GET /v1/agents/sessions/{id}/turns/{turn_id}/items`

都是列表。条目 `type=message` 时 `content[].type` 为 `output_text`，`content[].text` 是 CLI 文本。本地案例里 Codex 的文本是 `hello-from-fake-codex`，Qwen Code 是 `hello-from-fake-qwen`。

### `GET /v1/agents/runtimes`

成功 **200**，列表。每项：

| 字段 | 说明 |
|---|---|
| `id` / `name` | `codex` 或 `qwen-code` |
| `default` | 请求没点名适配器时会不会用这一条。产品顺序是 `codex` 然后 `qwen-code`。`order=asc` 才按这个顺序排。默认 `order=desc` |
| `object` | `agent.runtime` |
| `aliases` | Codex：`openai-codex`。Qwen：`qwen`、`qwen_code`、`qwencode` |
| `binary` | `codex` 或 `qwen` |
| `installed` | 当前 `PATH` 上是否有该二进制 |
| `path` | 找到时的路径 |
| `install_steps` | `[["npm","install","-g","@openai/codex"]]` 或 Qwen 对应的包名 `@qwen-code/qwen-code` |
| `auth_env_present` | 进程里是否已有该 CLI 的密钥环境变量 |
| `x_easy_sandbox.compute` | `none` |

## 产物、追踪、子代理

| 方法 | 路径 | 成功 | 响应 |
|---|---|---|---|
| GET | `/v1/agents/sessions/{id}/artifacts` | 200 列表 | CLI 报告过的文件快照。不扫描整个工作目录 |
| GET | `/v1/agents/sessions/{id}/artifacts/{artifact_id}` | 200 | 一条产物。`path` 形如 `/workspace/<相对路径>` |
| DELETE | 同上 | 200 | 只删快照。`deleted_scope` 为 `snapshot`，不动原文件 |
| GET | `.../artifacts/{artifact_id}/content` | 200 | 快照字节，`X-Content-Type-Options: nosniff` |
| GET | `/v1/agents/sessions/{id}/traces` | 200 列表 | 默认空。`EBX_AGENTS_TRACES=1` 时每个已结束回合一条 trace，只有时间和条目数，没有正文 |
| GET | `.../subagents` | 200 列表 | 只含 CLI 实际给出的 id |
| GET | `.../subagents/{subagent_id}` | 200 | 一个子代理。其他 id 与不存在的 id 同为 404 `resource_not_found` |
| GET | `.../subagents/{subagent_id}/items` | 200 列表 | |
| GET | `.../subagents/{subagent_id}/turns` | 200 列表 | |
| GET | `.../turns/{turn_id}` | 200 | |
| GET | `.../turns/{turn_id}/items` | 200 列表 | |

`multi_agent.enabled=true` 仍是 400。

## 环境、文件、模板

### `POST /v1/agents/environments`

body：`type` 必须能落到 `self_hosted`。空的 `{ "type": "openai_hosted" }` 会被转成 `self_hosted` 并在 `x_easy_sandbox.differences` 里说明。带配置的 `openai_hosted` 是 400。

| 字段 | 说明 |
|---|---|
| `workspace_directory` | 绝对路径，不能含 `..`，不能是 `/`、`/etc`、`/proc` 等 |
| `env` | 创建时应用，响应里不返回。拒绝 `PATH`、`HOME`、密钥、代理、`CODEX_*`、`QWEN_*`、`GIT_*`、`EBX_*` |
| `files` | 内联文件，创建时写入工作目录之下 |

400：`network`、`packages`、`setup_commands`、`plugins`、`skills`、`desktop`、`container_size`、`capability_directories`。成功 **200**，环境对象。不会预置容器。

### `GET /v1/agents/environments`

列表。**200**。

### `GET /v1/agents/environments/{environment_id}`

**200** 一个环境，或 404。

### `POST /v1/agents/environments/{environment_id}/files`

body：`path`、内容。路径相对工作目录。符号链接 400。已存在且内容不同是 400 `agents.file_exists`。写入 `.git/`、`.codex/`、`.claude/`、`.cursor/`、`.qwen/`、`.qoder/`、`.ssh/`，或 `.mcp.json`、`AGENTS.md`、`QWEN.md`、shell rc，是 400 `agents.path_refused`。大小上限 `EBX_AGENTS_MAX_FILE_BYTES`，默认 10 MiB。成功 **200**。

### `GET /v1/agents/environments/{environment_id}/files`

**200** 列表。只含普通文件。查询 `page` 为不透明翻页令牌，下一页在 `next`。

### 环境模板

| 方法 | 路径 | body | 成功 |
|---|---|---|---|
| POST | `/v1/agents/environments/templates` | `{name, env, files}`。被环境拒绝的字段在这里也是 400 | 200 |
| GET | `/v1/agents/environments/templates` | 无 | 200 列表。`env` 的值和文件内容不返回，只有 `size_bytes` |
| GET | `.../templates/{environment_template_id}` | 无 | 200 |
| POST | 同上 | 更新 `{name, env, files}` | 200 |
| DELETE | 同上 | 无 | 200 |

通过会话或环境上的 `environment_template_id` 应用到环境。

### 明确没有的执行器接口

| 方法 | 路径 | 响应 |
|---|---|---|
| POST | `/v1/agents/environments/{environment_id}/register` | 404 `agents.not_implemented_locally` |
| GET | `/v1/agents/environments/{environment_id}/connect` | 同上 |

## Agent 定义

### `POST /v1/agents`

| 字段 | 说明 |
|---|---|
| `model` | 必填，除非该字符串本身就是适配器名。否则作为 `-m` 传给 CLI |
| `name` | 可选 |
| `instructions` | 可选 |
| `metadata` | 字符串标量对象 |
| `tools` | 只有 `type=mcp` 且传输为 `http` 的工具。`stdio`、`allowed_tools`、其他工具类型是 400 |
| `reasoning.effort` | Codex 可以。Qwen Code 上是 400 |
| `reasoning.summary` | 400 |
| `multi_agent.enabled` | 400 |
| `service_tier` | 只允许 `auto` 或 `default` |
| `text.verbosity` | 只允许 `medium` |
| `text.format` | 只允许 `text` |

成功 **200**。`id` 形如 `agent_...`。MCP 请求头的值响应里是 `"***"`。

### `GET /v1/agents`

**200** 列表。

### `GET /v1/agents/{agent_id}`

**200** 或 404 `resource_not_found`，`param=agent_id`。

### `POST /v1/agents/{agent_id}`

原地更新。省略的字段不变。body 里再给 `adapter` 或 `runtime` 是 400：定义不能换运行时。成功 **200**。正在跑的会话保留启动时的副本。

### `DELETE /v1/agents/{agent_id}`

**200**：`{ "id", "object": "agent.deleted", "deleted": true }`。不停止已有会话。

## Vault 与凭据

Vault 只在内存里。每个所有者默认最多 `EBX_AGENTS_MAX_VAULTS`（100）个。

| 方法 | 路径 | body | 成功 |
|---|---|---|---|
| POST | `/v1/vaults` | 只能有 `name`、`metadata`。其他键 400 | 200。对象只有 `id`、`name`、`metadata`、`created_at` |
| GET | `/v1/vaults` | 分页 | 200 列表 |
| GET | `/v1/vaults/{vault_id}` | 无 | 200 或 404 |
| POST | `/v1/vaults/{vault_id}` | 只能改 `name`、`metadata` | 200 |
| DELETE | `/v1/vaults/{vault_id}` | 无 | 200 |

凭据：

| 方法 | 路径 | body | 成功 |
|---|---|---|---|
| POST | `.../credentials` | `name` 必填，`metadata` 可选，`auth` 必填 | 200。响应不含密钥的值、前缀、长度或哈希 |
| GET | `.../credentials` | 分页 | 200 列表 |
| GET | `.../credentials/{credential_id}` | 无 | 200 |
| POST | 同上 | 更新 `auth` 等允许字段 | 200。下一回合起生效 |
| DELETE | 同上 | 无 | 200 |

`auth` 允许 `static_bearer`，或带访问令牌的 `mcp_oauth`。400：`environment_variable`、`mcp_oauth.refresh`、`networking.unrestricted`、凭据主机以外的 `limited` 主机、不是 `https` 或指向私网的 `mcp_server_url`、含换行的令牌。

挂到会话的 `vault_ids` 上之后，凭据只注入到协议、主机、端口都相同的 MCP 工具，放在子进程环境的 `Authorization` 头里，不出现在 `argv`。两个凭据都匹配时必须给出 `credential_id`。凭据已删或 `expires_at` 已过，下一事件是 400 `agents.credential_unavailable` 或 `agents.credential_expired`。

## Responses

`POST /v1/responses` 把一次 CLI 回合当成一个 response。成功对象的 `object` 是 `response`。

| 字段 | 说明 |
|---|---|
| `model` | 已保存定义的 id，或透传给 CLI 的模型（如 `gpt-5-codex`）。`qwen` 这种运行时名表示用 CLI 默认模型，响应里 `model_resolved: false` |
| `input` | 字符串，或 `user` / `system` / `developer` 消息，内容为 `input_text` |
| `instructions` | 可选字符串 |
| `metadata` | 字符串标量 |
| `store` | 省略或 true 则保存。`false` 且 `background` 是 400。`store: false` 的 response 在回合结束后消失 |
| `background` | 布尔。true 时不必等回合结束 |
| `stream` | true 时回合结束后用 SSE 回放（`response.created`、`response.output_text.delta`、`response.completed`） |
| `previous_response_id` | 续接上一段。只能从该对话最新一条续，否则 400 `agents.previous_response_not_latest` |
| `tools` | 仅 MCP：`server_label`、`server_url`，只写的 `headers` 和 `authorization` |
| `reasoning.effort` | 仅 Codex |

400：`tools` 里非 MCP、`conversation`、`prompt`、非 `text` 的 `text.format`、任何 `include`、`service_tier` 不是 `auto|default`、`tool_choice` 不是 `auto`、`input_image`、`input_file`、助手历史、未知参数。`temperature`、`top_p`、`max_output_tokens` 被忽略，列在响应头 `X-Easy-Sandbox-Ignored-Params`。

输出条目只有 CLI 实际给出的：`message`、`reasoning`、`command_execution`、`mcp_call`、其他工具的 `tool_call`（带 `tool_name`）。不会出现 `web_search_call`、`function_call`、`code_interpreter_call`、`local_shell_call`。CLI 没报告用量时 `usage` 是 `null`。

| 方法 | 路径 | 成功 |
|---|---|---|
| POST | `/v1/responses` | 200，或 `stream: true` 时 SSE |
| GET | `/v1/responses` | 没有 WebSocket 升级时 400 `agents.websocket_upgrade_required` |
| POST | `/v1/responses/input_tokens` | **404** `agents.not_implemented_locally`。没有与 CLI 模型一致的分词器 |
| POST | `/v1/responses/compact` | body 需要 `previous_response_id`。Qwen 跑本地 `/compress`。Codex 是 400 `agents.compact_unsupported` |
| GET | `/v1/responses/{response_id}` | 200。`?stream=true&starting_after=N` 再次回放 |
| DELETE | `/v1/responses/{response_id}` | 200 |
| POST | `.../cancel` | 200 终态对象。已结束是 400 `agents.not_cancellable`，不是 409 |
| GET | `.../input_items` | 200 列表。创建时接受的输入 |

`Idempotency-Key` 重放第一次的 response。body 不同是 409。

## 模型、文件、Webhook

| 方法 | 路径 | 参数 | 成功 |
|---|---|---|---|
| GET | `/v1/models` | 分页 | 200 列表。含调用者的定义和两个适配器。`owned_by` 为 `easy-sandbox-local` |
| GET | `/v1/models/{model}` | 路径 `model` | 200，或 404 `model_not_found`。没有副作用 |
| DELETE | `/v1/models/{model}` | | **404** `agents.not_implemented_locally`。删除定义用 `DELETE /v1/agents/{agent_id}` |
| POST | `/v1/files` | JSON：`purpose` 必须是 `user_data`，`filename`，`data` 为 base64。不解析 multipart | 200。`file_id` 在内存里。没签发过的 id 之后使用是 400 |

Webhook。签名密钥 `whsec_...` 只在创建和轮换时返回一次。

| 方法 | 路径 | body | 成功 |
|---|---|---|---|
| POST | `/v1/webhook_endpoints` | 只能有 `url`、`event_types`、`name`。`url` 必须是 `https`，无用户信息、无查询串、不是私网或回环。本地开发可设 `EBX_AGENTS_WEBHOOK_ALLOW_HTTP=1` 和 `EBX_AGENTS_ALLOW_PRIVATE_URLS=1` | 200，含一次性 `secret` |
| GET | `/v1/webhook_endpoints` | 分页 | 200 列表。不含 secret |
| GET | `.../{webhook_endpoint_id}` | 无 | 200。不含 secret |
| POST | 同上 | `url`、`event_types`、`name` | 200 |
| DELETE | 同上 | 无 | 200 |
| POST | `.../rotate_secret` | `keep_old_secret_active_for_24_hours` 是 400 | 200，新 secret 只出现这一次 |
| POST | `.../test` | `event_type` | 200。服务端按 Standard Webhooks 签名投递 |
| GET | `/v1/webhook_event_types` | 无 | 200。接受 `agent.session.created`、`in_progress`、`idle`、`failed`。不接受 `agent.session.action_required` |

## 端到端覆盖

| 案例 | 覆盖的接口 | 说明 |
|---|---|---|
| `examples/agents/complete_case.py` | `POST /v1/agents/sessions`、`POST .../events`、`GET .../items`、`GET /v1/agents/runtimes`。未点名适配器时 `agent.id` 为 `codex`。`claude-code` 为 404 | 事件响应是空 body 的 202。示例里的助手文本来自 `PATH` 上的本地程序，不读取模型密钥 |
| `examples/agents/hosted_codex.py`、`hosted_qwen.py` | 同一组会话接口，对着已经启动的服务 | 与上面相同的 200 / 202 / 条目文本 |
| `examples/scenarios/agent_loop_local.py` | 不是 Agents API。是沙箱命令：health、shell、读文件、SIGTERM | stdout `'4\n'`，读回 `answer=4`，返回 -15 |

定义、环境、vault、responses、webhook 的参数和响应以上表为准。
