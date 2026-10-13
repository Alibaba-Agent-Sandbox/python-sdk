# 托管代理

用户向的说明和一条能跑完的案例在 [Agents API](agents-api.md)。本页是路由参考。

目前支持 **Codex** 和 **Qwen Code**。目前未支持的适配器名称，包括 Claude Code、Cursor、Qoder 和通用 command，返回 HTTP 404，错误类型是 `not_found_error`，响应头 `x-should-retry: false`。

路由在沙箱服务端（`easy_sandbox.server`）的 `agents` 能力组上。该组默认**关闭**，只有 `EBX_SERVER_ENABLED_GROUPS` 包含 `agents` 时才打开。组关闭时，同样的路径返回 404，正文会说明路由已禁用。

```bash
export EBX_SERVER_ENABLED_GROUPS=agents
python -m easy_sandbox.server
```

模板服务监听 **9000** 端口。OpenAI 风格的客户端把 `base_url` 指到 `http://127.0.0.1:9000/v1`。设置了 `EBX_SERVER_TOKEN` 时，agents 路由同时接受 `X-Access-Token` 和 `Authorization: Bearer`。其他路由仍然只认 `X-Access-Token`。

## 最佳实践

* 目前支持 **Codex** 和 **Qwen Code**。正文里写出目前未支持的适配器名称，是 HTTP 404 `not_found_error`，并带 `x-should-retry: false`。
* 把每个响应都当成本地操作。读取响应头 `X-Easy-Sandbox-Local: 1`（错误响应也有）。`x_easy_sandbox.compute` 是 `local_process`、`local_state` 或 `none`。
* 不要调用 `POST /v1/responses/input_tokens`。它是 404 `agents.not_implemented_locally`，并带 `x-should-retry: false`。没有与 CLI 将要调用的模型一致的分词器。
* 在会话需要之前保持该组关闭。用 `EBX_SERVER_ENABLED_GROUPS=agents` 启动进程。
* HTTP 客户端里不要放模型 API key。这些示例在设置了服务器令牌时，只发送那一个凭证。

## 全部是本地操作，并且会标明

这里没有任何操作在 OpenAI 上运行。每个操作要么是本地进程，要么是本地状态，并且都带标记：

* 每个响应（包括错误响应）都带响应头 `X-Easy-Sandbox-Local: 1`；
* 每个对象都带 `x_easy_sandbox: {"local": true, "compute": "local_process" | "local_state" | "none", "differences": [...]}`。`compute` 永远不会是 `openai_hosted`。openai SDK 的模型允许额外字段，读取方式是 `obj.model_extra["x_easy_sandbox"]`。标记不放进 `metadata`。

| `differences` 代码 | 含义 |
|---|---|
| `queued_not_steered` | 回合进行中发送的输入会排成新回合。两个 CLI 都不能向运行中的进程写入字节。 |
| `usage_adapter_best_effort` | `usage` 是 CLI 报告的值；CLI 什么都没报告时是 `null`。 |
| `redaction_best_effort` | 脱敏只覆盖已登记的密钥和常见的令牌形态。 |
| `update_in_place`、`snapshot_at_session_start` | 定义原地更新。会话在创建时复制一份定义。 |
| `hosted_request_converted`、`nothing_provisioned` | 空的 `openai_hosted` 环境请求被转成 `self_hosted`。环境只是一个目录绑定。 |
| `local_workspace`、`no_overwrite` | 路径相对于环境的工作目录。内容不同的已有文件会被拒绝。 |
| `local_blob` | 文件 id 是服务端内存里的 blob。 |
| `not_hosted_template`、`applies_env_and_files_only` | 模板只是 `{name, env, 内联文件}`，没有别的。 |
| `memory_only` | 密钥和 vault 记录只在内存里，重启即丢失。 |
| `secret_in_agent_env` | 代理运行的代码可以从 CLI 环境里读到凭据。 |
| `snapshot_copy`、`reported_paths_only`、`delete_removes_snapshot_only` | 产物是 CLI 报告的路径的副本。删除产物不会动原文件。 |
| `trace_from_journal_timing_only` | span 来自日志时间戳，不含任何文本。 |
| `ids_from_cli_only`、`turns_grouped_from_parent_stream`、`turns_from_rollout` | 子代理 id 是 CLI 自己给出的。 |
| `summary_not_encrypted_compaction` | `compact` 是本地摘要。 |
| `response_is_cli_turn`、`model_passthrough`、`stream_replayed_after_turn`、`queued_steer` | Responses 的语义。 |
| `local_signer` | 由本服务签名并投递 webhook 事件。 |
| `not_implemented_locally` | 出现在没有本地能力的路由的 404 上。 |

拒绝遵循同一条规则。服务端做不到的字段或变体是 **400** `invalid_request_error`，`param` 指出字段，并带 `x-should-retry: false`，绝不会先接受再忽略。没有本地能力的路由是 **404** `not_found_error`，带 `x-should-retry: false`，绝不是 501，也绝不是空的 200。

## 适配器

| JSON 里的选择 | 规范 id | `PATH` 上的二进制 | 只有要用时才安装 |
|---|---|---|---|
| `codex` | `codex` | `codex` | `npm install -g @openai/codex` |
| `qwen-code`、`qwen`、`qwencode` | `qwen-code` | `qwen` | `npm install -g @qwen-code/qwen-code` |

选择顺序：

1. 请求头 `X-EBX-Adapter`，或正文里的 `adapter` / `runtime`（顶层或 `agent` 内）
2. `agent.model` 或 `model`，且这个字符串是上面的名字之一（`gpt-5-codex` 这种真实模型 id 会传给 CLI，不会用来选适配器）
3. 配置 `agents.default`：环境变量 `EBX_AGENTS_DEFAULT`，或 `EBX_AGENTS_CONFIG` 指向的 JSON 里的 `default` / `agents.default`

都没有指定适配器时，响应是 **400** `agents.adapter_required`。

## 会话、事件、条目、回合

这些路由上的错误使用 OpenAI 的错误信封 `{"error": {"message", "type", "param", "code"}}`。

创建会话：

```bash
curl -s -X POST http://127.0.0.1:9000/v1/agents/sessions \
  -H 'Content-Type: application/json' \
  -d '{"agent":{"model":"codex"}}'
```

`GET /v1/agents/sessions` 列出会话（可用 `agent_id` 过滤）。`GET` 和 `DELETE /v1/agents/sessions/{id}` 读取和删除一个会话，删除时也会清掉产物快照。`POST /v1/agents/sessions/{id}` 只更新 `metadata`：`agent`、`vault_ids`、`environment` 返回 400，其他任何键也是 400。会话对象是 `agent.session`，`environment.type` 为 `self_hosted`，`environment.workspace_directory` 默认是 `/workspace`。

会话可以用内联的 `agent`，也可以用[定义](#agent-定义)的 `agent_id`，再加可选的 `environment: {"type": "self_hosted", "id": "env_..."}` 和 `vault_ids`。内联 `agent` 与定义用同样的规则校验：`mcp` 以外的 `tools`、`multi_agent.enabled`、不在 `auto|default` 内的 `service_tier`、非 `text` 的 `text.format` 都是 400。

会话、定义、环境、vault、模板、response 和 webhook 端点都归调用者所有。有服务端策略时，调用者是身份 id；没有策略时只有一个本地所有者。别人的 id 与不存在的 id 得到完全相同的应答。

排入一个回合。正文是一条输入消息；响应是 **HTTP 202，空响应体**。相同的 `Idempotency-Key` 加相同正文会重放这个 202，不会启动第二个回合。相同的键加不同正文是 **409** `idempotency.mismatch`（`x-should-retry: false`）。`input.tool_result`、`computer_use_approval_request_result`、`input_image`、`input_file` 都是 400。

```bash
curl -s -D - -o /dev/null -X POST \
  http://127.0.0.1:9000/v1/agents/sessions/$ID/events \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: turn-1' \
  -d '{"events":[{"type":"agent.session.input.message","input":"Say hello"}]}'
```

带 `Accept: text/event-stream` 的 `GET /v1/agents/sessions/{id}/events` 以 `text/event-stream` 流式返回映射后的事件（`id` 是运行时序号）。不带 `after` 时从现在开始跟踪；流会一直开着，直到你看到的那个回合结束、会话重新空闲。`?after=0`（或 `?after=evt_<seq>`）会回放环形缓冲区，送出 idle 事件且没有更新的排队内容后关闭。

`GET .../items`、`GET .../turns`、`GET .../turns/{turn_id}`、`GET .../turns/{turn_id}/items` 返回列表信封 `{object, data, first_id, last_id, has_more}`。`limit` 取 1–100（默认 20），`order` 为 `asc` 或 `desc`（默认 `desc`）。

`GET /v1/agents/runtimes` 只列出 **codex** 和 **qwen-code**，并说明各自的二进制是否在 `PATH` 上。

## Agent 定义

`POST /v1/agents`、`GET /v1/agents`、`GET`、`POST`（更新）和 `DELETE /v1/agents/{agent_id}`。id 是不透明的（`agent_...`）。`model` 必填，除非它是适配器名，否则作为 `-m` 传给 CLI。更新是原地的；运行中的会话保留它启动时的那份副本，删除定义不会停止任何会话。

只有走 `http` 传输的 `mcp` 工具是真实的。下面这些是 400：其他工具类型、`stdio` 传输、`allowed_tools`、`request_metadata`、`required`、不是 `environment` 的 `connection_origin`、带用户信息、查询串或片段的 URL、`multi_agent.enabled`、不在 `auto|default` 内的 `service_tier`、不是 `medium` 的 `text.verbosity`、`reasoning.summary`，以及 Qwen Code 上的 `reasoning.effort`（Codex 支持）。MCP 请求头的值只写不读：响应里显示 `"***"`。

## 环境、文件、模板

* `POST /v1/agents/environments`、`GET /v1/agents/environments`、`GET /v1/agents/environments/{environment_id}`。环境绑定一个工作目录（`type: self_hosted`），不会预置任何东西。`env`（永远不返回）和内联 `files` 在创建时应用。空的 `{"type": "openai_hosted"}` 会被转换并明说；带配置的是 400。`network`、`packages`、`setup_commands`、`plugins`、`skills`、`desktop`、`container_size`、`capability_directories` 都是 400。工作目录必须是不含 `..` 的绝对路径，且不在 `/`、`/etc`、`/proc` 等系统目录里。`env` 拒绝 `PATH`、`HOME`、LLM 端点和密钥、代理变量、加载器和解释器钩子，以及所有 `CODEX_*`、`QWEN_*`、`GIT_*`、`EBX_*` 名称。
* `POST` 和 `GET /v1/agents/environments/{environment_id}/files`。文件写在工作目录之下（`/workspace/a/b` 变成 `a/b`），通过带 `O_NOFOLLOW` 的目录文件描述符完成：路径上任何位置出现符号链接都会被拒绝。已有且内容不同的文件是 400 `agents.file_exists`（不用 409，SDK 会重试 409）；字节相同则成功。写入 `.git/`、`.codex/`、`.claude/`、`.cursor/`、`.qwen/`、`.qoder/`、`.ssh/` 之下，以及写 `.mcp.json`、`AGENTS.md`、`QWEN.md` 和 shell rc 文件，都是 400 `agents.path_refused`，因为它们会改变下一个回合要运行的东西。大小上限是 `EBX_AGENTS_MAX_FILE_BYTES`（默认 10 MiB）。列表只返回普通文件，跳过上述目录，用不透明的 `page` 令牌（`next`）翻页。
* `POST /v1/files` 把 `purpose=user_data` 的字节放在内存里，使 `{"type": "file_id"}` 可用。分发器只解析 JSON 正文，所以请发送 `{"purpose": "user_data", "filename": "...", "data": "<base64>"}`；不解析 multipart 上传。本服务没有签发过的 `file_id` 是 400。
* 模板（`/v1/agents/environments/templates`，创建、读取、更新、列出、删除）保存 `{name, env, files}`，通过 `environment.environment_template_id` 应用到环境。上面被拒绝的字段在创建和更新时都是 400，所以模板不可能带上它们。env 的值和文件内容永远不返回（只有 `size_bytes`）。

## Vault 与凭据

`/v1/vaults` 和 `/v1/vaults/{vault_id}/credentials` 使用官方的对象形状。Vault 在内存里（`memory_only`），计入 `EBX_AGENTS_MAX_VAULTS`（每个所有者默认 100 个），只显示 `id`、`name`、`metadata`、`created_at`。

凭据是 `static_bearer`，或带访问令牌的 `mcp_oauth`。任何响应、错误消息或事件都不含密钥的值、前缀、长度或哈希。下面这些是 400：`environment_variable`（没有出口代理，唯一的投递方式会把密钥交给代理运行的代码）、`mcp_oauth.refresh`（没有刷新代理）、`networking.unrestricted`、凭据自己主机以外的 `limited` 主机、不是 `https` 或指向私有主机的 `mcp_server_url`，以及含换行的令牌。

用会话（或环境）的 `vault_ids` 挂载 vault。每个回合，凭据会注入到该会话中 URL 的协议、主机、端口都相同的 MCP 工具，形式是放在子进程环境里的 `Authorization: Bearer` 请求头（Codex 用 `env_http_headers`，Qwen 用 `.qwen/settings.json` 里的 `${VAR}` 占位符），绝不出现在 `argv`。没有匹配凭据的工具以无认证方式运行；匹配到两个就必须显式给出 `credential_id`。轮换凭据从下一个回合起生效。会话创建后凭据或 vault 被删除，或 `expires_at` 已过期，下一个事件会返回 400（`agents.credential_unavailable`、`agents.credential_expired`），而不是悄悄地无认证运行。每个凭据对象都带 `secret_in_agent_env`。

## 产物、追踪、子代理

* `GET .../sessions/{id}/artifacts`、`GET` 和 `DELETE .../artifacts/{artifact_id}`、`GET .../artifacts/{artifact_id}/content`。回合完成时，服务端把 CLI **报告**的文件（Codex 的 `file_change`，Qwen 的 `write_file` / `replace` / `edit` 输入）复制到私有目录：使用 `O_NOFOLLOW`，只复制工作目录内的普通文件，每个不超过 `EBX_AGENTS_MAX_ARTIFACT_BYTES`（10 MiB），每个回合最多 100 个。绝不扫描工作目录，跳过 `.git/`，`path` 是 `/workspace/<相对路径>`。内容是快照，以附件形式返回并带 `X-Content-Type-Options: nosniff`。删除只删快照（`deleted_scope: snapshot`）。`EBX_AGENTS_STATE_DIR` 把快照放在 `<dir>/artifacts`，否则用一个 0700 的临时目录。
* `GET .../sessions/{id}/traces` 默认为空。设置 `EBX_AGENTS_TRACES=1` 后，每个已结束的回合返回一条 OTLP trace，只有一个 span，由日志里的开始和结束时间构成；属性只有回合状态和条目数，绝不含文本、命令或参数。
* `GET .../sessions/{id}/subagents` 和五个详情路由只提供 CLI 实际给出的 id。Codex：`collab_tool_call` 条目的 `receiver_thread_ids`，或会话自己的 rollout 里点名的 id；子代理的条目和回合来自 `CODEX_HOME` 下该子代理自己的 rollout（绝不去扫描无关会话）。Qwen Code：子代理消息上的 `parent_tool_use_id`；回合是该消息流按助手消息切分后的分组。其他 id 是 404 `resource_not_found`，与不存在的 id 字节相同。`multi_agent.enabled=true` 仍然是 400。详情在会话运行期间读取；Qwen 的条目保存在内存里，重启即丢失。

## Responses

`POST /v1/responses` 运行本地 CLI 的一个回合，返回 `response` 对象。`model` 是已保存定义的 id，或者作为 CLI 的模型透传（`gpt-5-codex`）；`qwen` 这样的运行时名字表示“CLI 的默认模型”，对象里会写 `model_resolved: false`。没有 `previous_response_id` 时，在 `EBX_AGENTS_RESPONSES_WORKSPACE`（默认 `/workspace`）里创建新的 CLI 会话。带了它，回合会续接那段对话，但只能从该对话最新的 response 续接（CLI 会话是线性的），否则是 400 `agents.previous_response_not_latest`。

* 接受：`model`、`input`（字符串，或带 `input_text` 部分的 `user`/`system`/`developer` 消息）、`instructions`、`metadata`、`store`、`background`、`stream`、`previous_response_id`、MCP `tools`（`server_label`、`server_url`，只写的 `headers` 和 `authorization`）、`reasoning.effort`（Codex）。
* 400：`mcp` 以外的 `tools`、`conversation`、`prompt`、非 `text` 的 `text.format`、任何 `include`、不在 `auto|default` 内的 `service_tier`、不是 `auto` 的 `tool_choice`、`input_image`、`input_file`、助手历史、不是消息的条目、`store: false` 时的 `background`，以及未知参数。
* 采样类参数（`temperature`、`top_p`、`max_output_tokens` 等）被忽略，并列在响应头 `X-Easy-Sandbox-Ignored-Params` 里。
* 输出条目就是 CLI 实际给出的东西：`message`、`reasoning`、`command_execution`、真实 MCP 调用对应的 `mcp_call`，以及其他所有原生工具（如 `web_search`、`file_change`）对应的 `tool_call`（带 `tool_name`）。每个非消息条目都带 `x_easy_sandbox`。不会出现 `web_search_call`、`function_call`、`code_interpreter_call`、`local_shell_call`。CLI 没报告时 `usage` 是 `null`。`Response.tools` 只列出传给 CLI 的 MCP 工具。
* `stream: true` 在回合结束后，用官方事件名（`response.created`、`response.output_text.delta`、`response.completed` 等）回放已保存的回合（`stream_replayed_after_turn`）。`GET /v1/responses/{id}?stream=true&starting_after=N` 可再次回放。
* `GET`、`DELETE /v1/responses/{id}`；`GET .../input_items` 返回创建时接受的输入。`POST .../cancel` 取消运行中的回合并返回终态对象；已结束的 response 是 400 `agents.not_cancellable`，不是 409。`Idempotency-Key` 会重放第一次的 response；正文不同则是 409。`store: false` 的 response 在回合结束后消失。
* `POST /v1/responses/compact` 需要 `previous_response_id`。Qwen Code 运行 `/compress`，结果是本地摘要（`summary_not_encrypted_compaction`，CLI 打印了的话还会带 `original_token_count` 和 `new_token_count`）。Codex 是 400 `agents.compact_unsupported`。
* 没有 WebSocket 升级的 `GET /v1/responses` 是 400 `agents.websocket_upgrade_required`。`responses.connect` 的客户端事件引擎（`response.create`；`response.steer` 把后续回合排在运行中的回合之后，即 `queued_steer`）已在 `agents.api_responses.ResponsesSocket` 中实现并有测试，但当前 HTTP 传输无法把套接字交给路由处理函数，所以升级本身需要传输层改动。

## 模型与 webhook

`GET /v1/models` 列出调用者的定义和两个适配器，`owned_by: easy-sandbox-local`，并带 `x_easy_sandbox.kind` / `installed`。`GET /v1/models/{id}` 对未列出的 id 返回 404 `model_not_found`，且没有副作用。

Webhook 端点（`/v1/webhook_endpoints`，创建、读取、更新、列出、删除、`rotate_secret`、`test`；`GET /v1/webhook_event_types`）是本地记录。`whsec_` 签名密钥只在创建和轮换时返回一次。服务端为所有者的会话发送 `agent.session.created`、`in_progress`、`idle`、`failed`，按 Standard Webhooks 方式签名（`webhook-id`、`webhook-timestamp`、`webhook-signature`），所以 `client.webhooks.unwrap` 可以验证。`agent.session.action_required` 永远不会发生，也不被接受。URL 必须是 `https`，不含用户信息和查询串，且不是私有或回环主机；不跟随重定向。本地开发时设置 `EBX_AGENTS_WEBHOOK_ALLOW_HTTP=1` 和 `EBX_AGENTS_ALLOW_PRIVATE_URLS=1`。`keep_old_secret_active_for_24_hours` 是 400。

## 没有本地能力：404

| 操作 | 原因 |
|---|---|
| `POST /v1/responses/input_tokens` | 没有与 CLI 将要调用的模型一致的分词器，真实计数只有在生成之后才知道。 |
| `DELETE /v1/models/{id}` | 没有微调模型。用 `DELETE /v1/agents/{agent_id}` 删除定义。 |
| 执行器注册和执行器通道（`environment.remote_url`） | 它们是 OpenAI 托管编排器的客户端。`POST /v1/agents/environments/{id}/register` 和 `GET .../{id}/connect` 返回同样带标记的 404（真实的注册路径未公开）。 |

每一个都返回 `404`、`type: not_found_error`、`code: agents.not_implemented_locally`、`x-should-retry: false`、`X-Easy-Sandbox-Local: 1`。

只演示调用方式的客户端，对着你已经启动的服务：[hosted_codex.py](../../../examples/agents/hosted_codex.py) 和 [hosted_qwen.py](../../../examples/agents/hosted_qwen.py)。[local_files_and_session.py](../../../examples/agents/local_files_and_session.py) 对着本地服务上传一个文件并开一个会话。它在 `PATH` 上放名为 `codex` 的本地程序，不读取模型 API key。见 [examples/agents/README.md](../../../examples/agents/README.md)。
