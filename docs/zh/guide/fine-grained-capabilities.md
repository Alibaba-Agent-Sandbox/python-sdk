# 细粒度能力

能力组是门。端点策略才决定这一组里哪几条路由能被调用，以及路径、命令、大小和频率限制。`agents-cli` 只放开会话相关的几条 Agents 路由，`POST /shell` 和 `POST /v1/agents` 保持关闭，用的就是这一层。

设计评审稿在 [细粒度能力设计](../design/fine-grained-capabilities.md)。路径和命令的执行细节在 [文件与命令控制](file-and-command-controls.md)。Agents 路由的请求和响应在 [Agents API 参考](../reference/agents-api.md)。

## 两层开关

1. **组**。`core` 永远开着。`agents`、`dev_tools`、`browser` 默认关。`file_ops`、`process`、`terminal`、`system`、`commands` 默认开。组关着时，这条路由直接 404，正文是 `Built-in route '<id>' is disabled`，还不会看端点规则。
2. **端点**。策略加载之后，每条路由再用端点 id 决定开或关。`endpoints` 里写 `"*": {enabled: false}`，再把要留下的 id 设为 `enabled: true`。`health`、`capabilities`、`capabilities_check` 不能关掉。

只写 `table.enable_group(FILE_OPS)` 会打开该组全部文件路由。要按接口收紧，必须再给一份策略。

## 如何启动

三种入口，服务端用同一份文档。无效文档会阻止启动，不会退回成全部允许。

`template.yaml` 的 `server:` 块。工具链把它编译成 `/etc/easy-sandbox/server-policy.json`。

```yaml
server:
  groups:
    agents: true
    file_ops: false
    process: false
    terminal: false
    dev_tools: false
    browser: false
  endpoints:
    "*":
      enabled: false
    agents_sessions_create:
      enabled: true
    agents_sessions_events_create:
      enabled: true
    agents_sessions_items_list:
      enabled: true
    agents_runtimes_list:
      enabled: true
```

进程环境变量，JSON 字符串：

```bash
export EBX_SERVER_POLICY='{"groups":{"agents":true,"process":false},"endpoints":{"*":{"enabled":false},"agents_sessions_create":{"enabled":true}}}'
```

或文件：

```bash
export EBX_SERVER_POLICY_FILE=/etc/easy-sandbox/server-policy.json
easy-sandbox-server check-config --policy /etc/easy-sandbox/server-policy.json
```

查找顺序：`EBX_SERVER_POLICY`，然后 `EBX_SERVER_POLICY_FILE`，然后默认路径上的策略文件。都没有时，服务端保持原来的组开关，不做逐端点限制。

Python：

```python
from easy_sandbox.server import SandboxServer, ServerPolicy, default_table

policy = ServerPolicy.only(
    "agents_sessions_create",
    "agents_sessions_events_create",
    "agents_sessions_items_list",
    "agents_runtimes_list",
).with_options(groups={
    "agents": True,
    "file_ops": False,
    "process": False,
    "terminal": False,
    "dev_tools": False,
    "browser": False,
})
SandboxServer(route_table=default_table(), policy=policy).serve(port=9000)
```

`ServerPolicy.only` 等价于先把 `"*"` 关掉，再打开列出的端点 id，并保留永远开着的 core 端点。`agents-cli` 的 `commands.py` 就是这样写的。

## 选择器

| 写法 | 匹配 |
|---|---|
| `agents_sessions_create` | 这一个端点 id |
| `files_*` | 名字匹配这个 glob 的端点 |
| `group:file_ops` | 这一组里的端点 |
| `*` | 全部端点 |
| `@defaults` | 策略里的 `defaults` 块，先于各端点 |

同一层里只要出现一次 `enabled: false`，该端点就是关的。更具体的选择器可以再打开它。

## 一条规则里能写什么

| 键 | 作用 |
|---|---|
| `enabled` | `true` 或 `false` |
| `scopes` | 调用者必须全部具备。`*` 表示全部，`files:*` 表示该名字空间 |
| `paths.allow` | 绝对路径列表。给出之后取代 `base_dir`，成为这条端点的边界 |
| `paths.deny` | 目录前缀或 glob。不含 `/` 的模式匹配路径分量，如 `*.pem`。拒绝优先 |
| `paths.read_only` | `true` 时这条端点上的写和删除被拒绝 |
| `paths.symlinks` | `within`（目标必须留在边界内）或 `never` |
| `limits` | 见下表。大小可写 `5MB`、`1MiB` |
| `params` | 见下表。拒绝类列表在多层之间取并集 |
| `audit` | `off`、`deny`、`all` |

所有端点都能写的 limits：`max_request_bytes`、`rate_per_minute`、`max_concurrency`。

Agents 端点已经在内置目录里，默认 scope 是 `agents:use`。和 `upload` 一样，可以把某一个端点 id 单独设为 `enabled: true`。这些端点没有 `paths`，也没有专用 `params`，所以除此之外只能写 `enabled`、`scopes`、`audit` 和上面三个通用 limits。写上 `paths` 或专用 `params` 时，策略加载失败。

预设，写在你的端点规则之前：

| 预设 | 效果 |
|---|---|
| `default` | 不额外限制 |
| `transfer-only` | 只留 `upload`、`download`、`files_upload_stream`、`files_download_stream` |
| `read-only` | 关掉 process、terminal、dev_tools、browser，并关掉写端点和 `env_set` |
| `hardened` | 关掉上述组，文件路由拒绝 `/proc`、`/sys`、`/dev`、`.ssh`、`.env`、`*.pem`、私钥文件名 |
| `locked` | 只留 `list_commands` 和 `run_command` |

组名：`core`、`commands`、`file_ops`、`process`、`terminal`、`system`、`dev_tools`、`browser`、`agents`。`core` 不能关。

同一个身份既能读有路径范围的文件，又能跑 `shell`、`process_start`、`code_run` 或 PTY 时，检查会给出 L1 警告。进程可以绕过路径规则。Agents 会话由服务端自己拉起 CLI，不需要为此打开 `process` 组。

## 端点目录

下表是进程导入服务端时实际登记的路由。Agents 行的 scope 是 `agents:use`。可配项比带路径的文件路由少，因为这些接口不接收路径或专用参数。

| 组 | 方法 | 路径 | 端点 id | scope | 可配项 |
|---|---|---|---|---|---|
| `agents` | GET | `/v1/agents/sessions/{id}/artifacts/{artifact_id}/content` | `agents_artifacts_content` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | DELETE | `/v1/agents/sessions/{id}/artifacts/{artifact_id}` | `agents_artifacts_delete` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/artifacts/{artifact_id}` | `agents_artifacts_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/artifacts` | `agents_artifacts_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/environments/{environment_id}/connect` | `agents_cannot_executor_channel` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/agents/environments/{environment_id}/register` | `agents_cannot_executor_registration` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | DELETE | `/v1/models/{model}` | `agents_cannot_models_delete` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/responses/input_tokens` | `agents_cannot_responses_input_tokens` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/agents` | `agents_definitions_create` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | DELETE | `/v1/agents/{agent_id}` | `agents_definitions_delete` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/{agent_id}` | `agents_definitions_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents` | `agents_definitions_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/agents/{agent_id}` | `agents_definitions_update` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/agents/environments/{environment_id}/files` | `agents_environment_files_create` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/environments/{environment_id}/files` | `agents_environment_files_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/agents/environments/templates` | `agents_environment_templates_create` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | DELETE | `/v1/agents/environments/templates/{environment_template_id}` | `agents_environment_templates_delete` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/environments/templates/{environment_template_id}` | `agents_environment_templates_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/environments/templates` | `agents_environment_templates_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/agents/environments/templates/{environment_template_id}` | `agents_environment_templates_update` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/agents/environments` | `agents_environments_create` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/environments/{environment_id}` | `agents_environments_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/environments` | `agents_environments_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/files` | `agents_files_create` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/models/{model}` | `agents_models_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/models` | `agents_models_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/responses/{response_id}/cancel` | `agents_responses_cancel` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/responses/compact` | `agents_responses_compact` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/responses` | `agents_responses_connect` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/responses` | `agents_responses_create` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | DELETE | `/v1/responses/{response_id}` | `agents_responses_delete` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/responses/{response_id}` | `agents_responses_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/responses/{response_id}/input_items` | `agents_responses_input_items` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/runtimes` | `agents_runtimes_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/agents/sessions` | `agents_sessions_create` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | DELETE | `/v1/agents/sessions/{id}` | `agents_sessions_delete` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/agents/sessions/{id}/events` | `agents_sessions_events_create` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/events` | `agents_sessions_events_stream` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}` | `agents_sessions_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/items` | `agents_sessions_items_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions` | `agents_sessions_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/turns/{turn_id}` | `agents_sessions_turns_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/turns/{turn_id}/items` | `agents_sessions_turns_items_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/turns` | `agents_sessions_turns_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/agents/sessions/{id}` | `agents_sessions_update` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}` | `agents_subagents_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/items` | `agents_subagents_items_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents` | `agents_subagents_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}` | `agents_subagents_turns_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}/items` | `agents_subagents_turns_items_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns` | `agents_subagents_turns_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/agents/sessions/{id}/traces` | `agents_traces_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/vaults/{vault_id}/credentials` | `agents_vault_credentials_create` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | DELETE | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `agents_vault_credentials_delete` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `agents_vault_credentials_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/vaults/{vault_id}/credentials` | `agents_vault_credentials_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `agents_vault_credentials_update` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/vaults` | `agents_vaults_create` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | DELETE | `/v1/vaults/{vault_id}` | `agents_vaults_delete` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/vaults/{vault_id}` | `agents_vaults_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/vaults` | `agents_vaults_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/vaults/{vault_id}` | `agents_vaults_update` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/webhook_event_types` | `agents_webhook_event_types` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/webhook_endpoints` | `agents_webhooks_create` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | DELETE | `/v1/webhook_endpoints/{webhook_endpoint_id}` | `agents_webhooks_delete` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/webhook_endpoints/{webhook_endpoint_id}` | `agents_webhooks_get` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | GET | `/v1/webhook_endpoints` | `agents_webhooks_list` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}/rotate_secret` | `agents_webhooks_rotate_secret` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}/test` | `agents_webhooks_test` | agents:use | enabled、scopes、audit；仅通用 limits |
| `agents` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}` | `agents_webhooks_update` | agents:use | enabled、scopes、audit；仅通用 limits |
| `browser` | POST | `/browser/click` | `browser_click` | browser:use | 仅通用 limits |
| `browser` | GET | `/browser/console` | `browser_console` | browser:use | 仅通用 limits |
| `browser` | GET | `/browser/content` | `browser_content` | browser:use | 仅通用 limits |
| `browser` | POST | `/browser/evaluate` | `browser_evaluate` | browser:evaluate | 可执行程序 |
| `browser` | POST | `/browser/navigate` | `browser_navigate` | browser:use | params: block_private_networks, url_allow, url_deny；可执行程序 |
| `browser` | POST | `/browser/pdf` | `browser_pdf` | browser:use | 仅通用 limits |
| `browser` | POST | `/browser/screenshot` | `browser_screenshot` | browser:use | 仅通用 limits |
| `browser` | POST | `/browser/type` | `browser_type` | browser:use | 仅通用 limits |
| `commands` | GET | `/commands` | `list_commands` | commands:list | 仅通用 limits |
| `commands` | POST | `/commands/{name}` | `run_command` | commands:run | 仅通用 limits |
| `core` | GET | `/capabilities` | `capabilities` | core:read | 不能关闭 |
| `core` | POST | `/capabilities/check` | `capabilities_check` | core:read | 不能关闭 |
| `core` | GET | `/health` | `health` | — | 不能关闭 |
| `dev_tools` | POST | `/code/run` | `code_run` | devtools:run | params: languages；limits: max_output_bytes, timeout_seconds；可执行程序 |
| `dev_tools` | GET | `/git/diff` | `git_diff` | devtools:read | paths |
| `dev_tools` | GET | `/git/status` | `git_status` | devtools:read | paths |
| `file_ops` | GET | `/download` | `download` | files:read | paths；limits: max_bytes |
| `file_ops` | POST | `/files/archive` | `files_archive` | files:read | paths；limits: max_bytes, max_files |
| `file_ops` | DELETE | `/files` | `files_delete` | files:delete | paths |
| `file_ops` | GET | `/files/download-stream` | `files_download_stream` | files:read | paths；limits: max_bytes |
| `file_ops` | GET | `/files/list` | `files_list` | files:read | paths；limits: max_depth, max_entries |
| `file_ops` | POST | `/files/mkdir` | `files_mkdir` | files:write | paths |
| `file_ops` | POST | `/files/move` | `files_move` | files:write, files:delete | paths |
| `file_ops` | POST | `/files/search` | `files_search` | files:read | paths；limits: max_depth, max_results, timeout_seconds |
| `file_ops` | GET | `/files/stat` | `files_stat` | files:read | paths |
| `file_ops` | POST | `/files/upload-stream` | `files_upload_stream` | files:write | paths；params: allow_extensions, deny_extensions, overwrite；limits: max_bytes |
| `file_ops` | GET | `/files/watch` | `files_watch` | files:read | paths；limits: max_duration_seconds |
| `file_ops` | POST | `/upload` | `upload` | files:write | paths；params: allow_extensions, deny_extensions, overwrite；limits: max_bytes |
| `process` | GET | `/process/{pid}` | `process_detail` | process:read | 仅通用 limits |
| `process` | GET | `/process/list` | `process_list` | process:read | 仅通用 limits |
| `process` | GET | `/process/{pid}/output` | `process_output` | process:read | 仅通用 limits |
| `process` | POST | `/process/{pid}/signal` | `process_signal` | process:manage | params: allowed_signals |
| `process` | POST | `/process/start` | `process_start` | process:run | paths；params: allow_commands, deny_commands；limits: max_output_bytes, max_processes, timeout_seconds；可执行程序 |
| `process` | POST | `/process/{pid}/stdin` | `process_stdin` | process:manage | 仅通用 limits |
| `process` | POST | `/shell` | `shell` | process:run | paths；params: allow_commands, deny_commands；limits: max_output_bytes, max_processes, timeout_seconds；可执行程序 |
| `process` | POST | `/shell/stream` | `shell_stream` | process:run | paths；params: allow_commands, deny_commands；limits: max_output_bytes, max_processes, timeout_seconds；可执行程序 |
| `system` | GET | `/env` | `env_get` | system:read | params: allow_vars, deny_vars |
| `system` | POST | `/env` | `env_set` | system:write | params: allow_vars, deny_vars |
| `system` | GET | `/packages` | `packages` | system:read | 仅通用 limits |
| `system` | GET | `/ports` | `ports` | system:read | 仅通用 limits |
| `system` | GET | `/system/info` | `system_info` | system:read | 仅通用 limits |
| `system` | GET | `/system/metrics` | `system_metrics` | system:read | 仅通用 limits |
| `terminal` | POST | `/pty/sessions` | `pty_create_session` | terminal:use | params: env_deny, shells；limits: max_sessions |
| `terminal` | DELETE | `/pty/sessions/{id}` | `pty_delete_session` | terminal:use | 仅通用 limits |
| `terminal` | GET | `/pty/sessions/{id}` | `pty_detail` | terminal:use | 仅通用 limits |
| `terminal` | GET | `/pty/sessions` | `pty_list_sessions` | terminal:use | 仅通用 limits |
| `terminal` | POST | `/pty/sessions/{id}/resize` | `pty_resize` | terminal:use | 仅通用 limits |

## 和 Agents API 案例的关系

`agents-cli` 打开 `groups.agents`，并只启用：

| 端点 id | 路由 |
|---|---|
| `agents_sessions_create` | `POST /v1/agents/sessions` |
| `agents_sessions_get` | `GET /v1/agents/sessions/{id}` |
| `agents_sessions_list` | `GET /v1/agents/sessions` |
| `agents_sessions_events_create` | `POST /v1/agents/sessions/{id}/events` |
| `agents_sessions_items_list` | `GET /v1/agents/sessions/{id}/items` |
| `agents_runtimes_list` | `GET /v1/agents/runtimes` |

本地 e2e 已确认：`POST /shell` 是 404，`POST /v1/agents`（定义）是 404，Codex 和 Qwen Code 的会话、事件、条目仍然 200 / 202。要再开放一条路由，把对应端点 id 加进 `ServerPolicy.only` 和 `template.yaml` 的 `endpoints`。
