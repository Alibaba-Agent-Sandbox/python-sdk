# 细粒度能力

每条路由只有一个端点 id，每个端点一条规则，决定它能不能被调用，以及路径、命令、大小和频率限制。规则前面没有第二道门。`agents-cli` 只放开会话相关的几条 Agents 路由，`POST /shell` 和 `POST /v1/agents` 保持关闭，用的就是这一层。

设计评审稿在 [细粒度能力设计](../design/fine-grained-capabilities.md)。路径和命令的执行细节在 [文件与命令控制](file-and-command-controls.md)。Agents 请求和响应在 [Agents API](agents-api.md)。完整路由表在 [Agents API 参考](../reference/agents-api.md)。

## 一个开关：端点

端点 id（`upload`、`files_list`、`agents_sessions_create`）是所有环节共用的单位：策略、审计日志、`GET /capabilities` 和客户端。组只是**一组端点 id 的名字**。写 `groups: [file_ops]`、`group:file_ops`、`table.enable_group(CapabilityGroup.FILE_OPS)` 或 `ABX_SERVER_ENABLED_GROUPS=file_ops`，都会展开成该组声明的端点 id，得到同一份逐端点规则。

默认值：`core` 永远开着。`agents`、`dev_tools`、`browser` 是可选组，默认关。`file_ops`、`process`、`terminal`、`system`、`commands` 默认开。`health`、`capabilities`、`capabilities_check` 不能关掉。

规则来自五层，按端点合并：

| 层 | 来源 | 能打开 | 能关闭 |
|---|---|---|---|
| default | 内置的可选组 | 否 | 是（可选组） |
| code | 模板 `commands.py` 里的 `default_table().enable_group()` / `disable_group()` | 是 | 是 |
| preset | `preset:` | 是 | 是 |
| policy | 策略文档的 `groups`、`defaults`、`endpoints` | 是 | 是 |
| environment | `ABX_SERVER_ENABLED_GROUPS` | 是 | 否 |

更具体的选择器优先：精确 id 优于 glob，glob 优于 `group:<name>`。同样具体时，后面的层优先；同一层里只要有一条 `enabled: false`，该端点就是关的。所以策略里的 `endpoints.code_run.enabled: false`，即使环境变量打开了 `dev_tools`，它也仍然是关的。

拒绝会指出是哪条规则拒绝的。404 正文带 `code: endpoint_disabled` 和 `rule`，例如 `policy:endpoints.shell`、`policy:groups.process`、`preset:read-only`、`code:enable_group:file_ops`、`default:opt-in:browser`。`GET /capabilities` 逐端点报告同一个 `rule`。它的 `groups` 和 `group_summary` 由端点状态推导（`{"file_ops": {"enabled": 11, "total": 12}}`），不单独存储。

`ABX_SERVER_ENABLED_GROUPS` 是唯一的组环境变量，值是逗号分隔的组名，例如 `agents,dev_tools`。未知名字会让进程带着拼写建议退出。没有用来关闭组的变量，请写 `groups: {process: false}` 或 `endpoints` 规则。

## 如何启动

三种入口，服务端用同一份文档。无效文档会阻止启动，不会退回成全部允许。

`template.yaml` 的 `server:` 块。工具链把它编译成 `/etc/agent-sandbox/server-policy.json`。可用的键：`version`、`preset`、`base_dir`、`groups`、`defaults`、`auth`、`endpoints`、`description`。`groups` 可以是要打开的组列表，也可以是组到 `true`/`false` 的映射。

```yaml
server:
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

组的简写，列表或映射：

```yaml
server:
  groups: [agents, dev_tools]     # 等价于 {agents: true, dev_tools: true}
```

```yaml
server:
  groups:
    process: false
    terminal: false
```

内联 JSON：

```bash
export ABX_SERVER_POLICY='{"groups":["agents"],"endpoints":{"*":{"enabled":false},"agents_sessions_create":{"enabled":true}}}'
```

或文件：

```bash
export ABX_SERVER_POLICY_FILE=/etc/agent-sandbox/server-policy.json
agent-sandbox-server check-config --policy /etc/agent-sandbox/server-policy.json
```

查找顺序：`ABX_SERVER_POLICY`，然后 `ABX_SERVER_POLICY_FILE`，然后默认路径上的策略文件。都没有时用内置默认：可选组关，其余全开，没有逐端点限制。

Python：

```python
from agent_sandbox.server import SandboxServer, ServerPolicy

policy = ServerPolicy.only(
    "agents_sessions_create",
    "agents_sessions_events_create",
    "agents_sessions_items_list",
    "agents_runtimes_list",
)
SandboxServer(policy=policy).serve(port=9000)
```

`ServerPolicy.only` 先把 `"*"` 关掉，再打开列出的 id，并保留 core 端点。`agents-cli` 的 `commands.py` 就是这个调用。`only` 还接受 `"transfer"`（上传下载的四个 id）和 `"group:<name>"`。

不写策略文档、在 `commands.py` 里打开整组：

```python
from agent_sandbox.server import CapabilityGroup, default_table

default_table().enable_group(CapabilityGroup.DEV_TOOLS)
```

`enable_group` 和 `disable_group` 是仅有的代码级开关。`disable_group(CORE)` 会抛错。

## 选择器

| 写法 | 匹配 |
|---|---|
| `agents_sessions_create` | 这一个端点 id |
| `files_*` | 名字匹配这个 glob 的端点 |
| `group:file_ops` | 这一组里的端点 |
| `*` | 全部端点 |
| `@defaults` | 策略里的 `defaults` 块，先于各端点 |

同样具体、同一层里的多条匹配规则冲突时，`enabled: false` 优先。更具体的选择器可以再打开该端点。

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
| `default` | 不额外限制（可选组保持关闭） |
| `transfer-only` | 只留 `upload`、`download`、`files_upload_stream`、`files_download_stream` |
| `read-only` | 关掉 process、terminal、dev_tools、browser，并关掉写端点和 `env_set` |
| `hardened` | 关掉上述组，文件路由拒绝 `/proc`、`/sys`、`/dev`、`.ssh`、`.env`、`*.pem`、私钥文件名 |
| `locked` | 只留 `list_commands` 和 `run_command` |

组名：`core`、`commands`、`file_ops`、`process`、`terminal`、`system`、`dev_tools`、`browser`、`agents`。`core` 不能关。

同一个身份既能读有路径范围的文件，又能跑 `shell`、`process_start`、`code_run` 或 PTY 时，检查会给出 L1 警告。进程可以绕过路径规则。Agents 会话由服务端自己拉起 CLI，不需要为此打开 `process` 组。

## 端点目录

下表是端点声明表（`agent_sandbox.server.endpoints.ENDPOINTS`）。路由表、策略和 `GET /capabilities` 都由它派生。`pty_connect` 是 WebSocket 升级，在 PTY 端口上提供。Agents 行的 scope 是 `agents:use`。可配项比带路径的文件路由少，因为这些接口不接收路径或专用参数。

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
| `browser` | POST | `/browser/evaluate` | `browser_evaluate` | browser:evaluate | 会执行程序 |
| `browser` | POST | `/browser/navigate` | `browser_navigate` | browser:use | params：block_private_networks、url_allow、url_deny；会执行程序 |
| `browser` | POST | `/browser/pdf` | `browser_pdf` | browser:use | 仅通用 limits |
| `browser` | POST | `/browser/screenshot` | `browser_screenshot` | browser:use | 仅通用 limits |
| `browser` | POST | `/browser/type` | `browser_type` | browser:use | 仅通用 limits |
| `commands` | GET | `/commands` | `list_commands` | commands:list | 仅通用 limits |
| `commands` | POST | `/commands/{name}` | `run_command` | commands:run | 仅通用 limits |
| `core` | GET | `/capabilities` | `capabilities` | core:read | 不可关闭 |
| `core` | POST | `/capabilities/check` | `capabilities_check` | core:read | 不可关闭 |
| `core` | GET | `/health` | `health` | — | 不可关闭 |
| `dev_tools` | POST | `/code/run` | `code_run` | devtools:run | params：languages；limits：max_output_bytes、timeout_seconds；会执行程序 |
| `dev_tools` | GET | `/git/diff` | `git_diff` | devtools:read | paths |
| `dev_tools` | GET | `/git/status` | `git_status` | devtools:read | paths |
| `file_ops` | GET | `/download` | `download` | files:read | paths；limits：max_bytes |
| `file_ops` | POST | `/files/archive` | `files_archive` | files:read | paths；limits：max_bytes、max_files |
| `file_ops` | DELETE | `/files` | `files_delete` | files:delete | paths |
| `file_ops` | GET | `/files/download-stream` | `files_download_stream` | files:read | paths；limits：max_bytes |
| `file_ops` | GET | `/files/list` | `files_list` | files:read | paths；limits：max_depth、max_entries |
| `file_ops` | POST | `/files/mkdir` | `files_mkdir` | files:write | paths |
| `file_ops` | POST | `/files/move` | `files_move` | files:write, files:delete | paths |
| `file_ops` | POST | `/files/search` | `files_search` | files:read | paths；limits：max_depth、max_results、timeout_seconds |
| `file_ops` | GET | `/files/stat` | `files_stat` | files:read | paths |
| `file_ops` | POST | `/files/upload-stream` | `files_upload_stream` | files:write | paths；params：allow_extensions、deny_extensions、overwrite；limits：max_bytes |
| `file_ops` | GET | `/files/watch` | `files_watch` | files:read | paths；limits：max_duration_seconds |
| `file_ops` | POST | `/upload` | `upload` | files:write | paths；params：allow_extensions、deny_extensions、overwrite；limits：max_bytes |
| `process` | GET | `/process/{pid}` | `process_detail` | process:read | 仅通用 limits |
| `process` | GET | `/process/list` | `process_list` | process:read | 仅通用 limits |
| `process` | GET | `/process/{pid}/output` | `process_output` | process:read | 仅通用 limits |
| `process` | POST | `/process/{pid}/signal` | `process_signal` | process:manage | params：allowed_signals |
| `process` | POST | `/process/start` | `process_start` | process:run | paths；params：allow_commands、deny_commands；limits：max_output_bytes、max_processes、timeout_seconds；会执行程序 |
| `process` | POST | `/process/{pid}/stdin` | `process_stdin` | process:manage | 仅通用 limits |
| `process` | POST | `/shell` | `shell` | process:run | paths；params：allow_commands、deny_commands；limits：max_output_bytes、max_processes、timeout_seconds；会执行程序 |
| `process` | POST | `/shell/stream` | `shell_stream` | process:run | paths；params：allow_commands、deny_commands；limits：max_output_bytes、max_processes、timeout_seconds；会执行程序 |
| `system` | GET | `/env` | `env_get` | system:read | params：allow_vars、deny_vars |
| `system` | POST | `/env` | `env_set` | system:write | params：allow_vars、deny_vars |
| `system` | GET | `/packages` | `packages` | system:read | 仅通用 limits |
| `system` | GET | `/ports` | `ports` | system:read | 仅通用 limits |
| `system` | GET | `/system/info` | `system_info` | system:read | 仅通用 limits |
| `system` | GET | `/system/metrics` | `system_metrics` | system:read | 仅通用 limits |
| `terminal` | WS | `/pty` | `pty_connect` | terminal:use | 仅通用 limits |
| `terminal` | POST | `/pty/sessions` | `pty_create_session` | terminal:use | params：env_deny、shells；limits：max_sessions |
| `terminal` | DELETE | `/pty/sessions/{id}` | `pty_delete_session` | terminal:use | 仅通用 limits |
| `terminal` | GET | `/pty/sessions/{id}` | `pty_detail` | terminal:use | 仅通用 limits |
| `terminal` | GET | `/pty/sessions` | `pty_list_sessions` | terminal:use | 仅通用 limits |
| `terminal` | POST | `/pty/sessions/{id}/resize` | `pty_resize` | terminal:use | 仅通用 limits |

## 和 Agents API 案例的关系

`agents-cli` 只启用：

| 端点 id | 路由 |
|---|---|
| `agents_sessions_create` | `POST /v1/agents/sessions` |
| `agents_sessions_get` | `GET /v1/agents/sessions/{id}` |
| `agents_sessions_list` | `GET /v1/agents/sessions` |
| `agents_sessions_events_create` | `POST /v1/agents/sessions/{id}/events` |
| `agents_sessions_items_list` | `GET /v1/agents/sessions/{id}/items` |
| `agents_runtimes_list` | `GET /v1/agents/runtimes` |

本地 e2e 已确认：`POST /shell` 是 404，`POST /v1/agents`（定义）是 404，Codex 和 Qwen Code 的会话、事件、条目仍然 200 / 202。要再开放一条路由，把对应端点 id 加进 `ServerPolicy.only` 和 `template.yaml` 的 `endpoints`。
