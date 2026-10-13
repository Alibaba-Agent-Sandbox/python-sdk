# Fine-grained capabilities

Groups are the gate. Endpoint policy decides which routes inside a group can be called, and which path, command, size, and rate limits apply. `agents-cli` exposes only the session routes and leaves `POST /shell` and `POST /v1/agents` closed. That is this layer.

The design note is [Fine-grained capabilities](../design/fine-grained-capabilities.md). Path and command enforcement is in [File and command controls](file-and-command-controls.md). Agents request and response shapes are in [Agents API reference](../reference/agents-api.md).

## Two switches

1. **Group.** `core` is always on. `agents`, `dev_tools`, and `browser` start off. `file_ops`, `process`, `terminal`, `system`, and `commands` start on. A disabled group returns 404 `Built-in route '<id>' is disabled` before any endpoint rule runs.
2. **Endpoint.** Once a policy is loaded, each route is allowed or denied by its endpoint id. Set `"*": {enabled: false}`, then set the ids you want to `enabled: true`. `health`, `capabilities`, and `capabilities_check` cannot be turned off.

`table.enable_group(FILE_OPS)` opens every file route in that group. Narrowing to one route needs a policy.

## How to turn it on

Three inputs, one document. An invalid document stops the process. It does not fall open.

The `server:` block in `template.yaml`. Tooling compiles it to `/etc/easy-sandbox/server-policy.json`.

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

Inline JSON:

```bash
export EBX_SERVER_POLICY='{"groups":{"agents":true,"process":false},"endpoints":{"*":{"enabled":false},"agents_sessions_create":{"enabled":true}}}'
```

Or a file:

```bash
export EBX_SERVER_POLICY_FILE=/etc/easy-sandbox/server-policy.json
easy-sandbox-server check-config --policy /etc/easy-sandbox/server-policy.json
```

Lookup order: `EBX_SERVER_POLICY`, then `EBX_SERVER_POLICY_FILE`, then the well-known policy file. With none of them, the server keeps the group switches and does not apply per-endpoint rules.

Python:

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

`ServerPolicy.only` turns `"*"` off, turns the listed ids on, and leaves the core endpoints on. `agents-cli`'s `commands.py` is this call.

## Selectors

| Form | Matches |
|---|---|
| `agents_sessions_create` | That endpoint id |
| `files_*` | Endpoint ids matching the glob |
| `group:file_ops` | Endpoints in that group |
| `*` | Every endpoint |
| `@defaults` | The `defaults` block, applied before each endpoint |

If any matching rule at the same layer sets `enabled: false`, the endpoint is off. A more specific selector can turn it back on.

## What a rule may contain

| Key | Effect |
|---|---|
| `enabled` | `true` or `false` |
| `scopes` | The caller must hold every listed scope. `*` is everything. `files:*` is that namespace |
| `paths.allow` | Absolute paths. When set, they replace `base_dir` as that endpoint's boundary |
| `paths.deny` | Directory prefixes or globs. A pattern without `/` matches a path component, such as `*.pem`. Deny wins |
| `paths.read_only` | `true` rejects writes and deletes on that endpoint |
| `paths.symlinks` | `within` (the target must stay inside the boundary) or `never` |
| `limits` | See below. Sizes accept `5MB` and `1MiB` |
| `params` | See below. Deny-lists are unioned across layers |
| `audit` | `off`, `deny`, or `all` |

Limits every endpoint accepts: `max_request_bytes`, `rate_per_minute`, `max_concurrency`.

Routes that are not in the built-in catalogue (every Agents API route today) accept only `enabled`, `scopes`, `audit`, and those three limits. A `paths` or specialised `params` block on them fails policy load.

Presets apply before your endpoint rules:

| Preset | Effect |
|---|---|
| `default` | No extra restriction |
| `transfer-only` | Only `upload`, `download`, `files_upload_stream`, `files_download_stream` |
| `read-only` | Turns off process, terminal, dev_tools, and browser, and turns off write endpoints and `env_set` |
| `hardened` | Turns off those groups and denies `/proc`, `/sys`, `/dev`, `.ssh`, `.env`, `*.pem`, and private-key names on file routes |
| `locked` | Only `list_commands` and `run_command` |

Group names: `core`, `commands`, `file_ops`, `process`, `terminal`, `system`, `dev_tools`, `browser`, `agents`. `core` cannot be disabled.

The checker warns (L1) when one identity can both read scoped files and run `shell`, `process_start`, `code_run`, or a PTY. A process can bypass path rules. An Agents session starts the CLI inside the server. It does not need the `process` group for that.

## Endpoint catalogue

This is the route table registered when the server package is imported. Agents rows have fewer knobs because they are not in the built-in catalogue yet.

| Group | Method | Path | Endpoint id | Scope | Knobs |
|---|---|---|---|---|---|
| `agents` | GET | `/v1/agents/sessions/{id}/artifacts/{artifact_id}/content` | `agents_artifacts_content` | — | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/agents/sessions/{id}/artifacts/{artifact_id}` | `agents_artifacts_delete` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/artifacts/{artifact_id}` | `agents_artifacts_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/artifacts` | `agents_artifacts_list` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments/{environment_id}/connect` | `agents_cannot_executor_channel` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/environments/{environment_id}/register` | `agents_cannot_executor_registration` | — | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/models/{model}` | `agents_cannot_models_delete` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/responses/input_tokens` | `agents_cannot_responses_input_tokens` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents` | `agents_definitions_create` | — | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/agents/{agent_id}` | `agents_definitions_delete` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/{agent_id}` | `agents_definitions_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents` | `agents_definitions_list` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/{agent_id}` | `agents_definitions_update` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/environments/{environment_id}/files` | `agents_environment_files_create` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments/{environment_id}/files` | `agents_environment_files_list` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/environments/templates` | `agents_environment_templates_create` | — | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/agents/environments/templates/{environment_template_id}` | `agents_environment_templates_delete` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments/templates/{environment_template_id}` | `agents_environment_templates_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments/templates` | `agents_environment_templates_list` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/environments/templates/{environment_template_id}` | `agents_environment_templates_update` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/environments` | `agents_environments_create` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments/{environment_id}` | `agents_environments_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments` | `agents_environments_list` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/files` | `agents_files_create` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/models/{model}` | `agents_models_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/models` | `agents_models_list` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/responses/{response_id}/cancel` | `agents_responses_cancel` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/responses/compact` | `agents_responses_compact` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/responses` | `agents_responses_connect` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/responses` | `agents_responses_create` | — | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/responses/{response_id}` | `agents_responses_delete` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/responses/{response_id}` | `agents_responses_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/responses/{response_id}/input_items` | `agents_responses_input_items` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/runtimes` | `agents_runtimes_list` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/sessions` | `agents_sessions_create` | — | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/agents/sessions/{id}` | `agents_sessions_delete` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/sessions/{id}/events` | `agents_sessions_events_create` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/events` | `agents_sessions_events_stream` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}` | `agents_sessions_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/items` | `agents_sessions_items_list` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions` | `agents_sessions_list` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/turns/{turn_id}` | `agents_sessions_turns_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/turns/{turn_id}/items` | `agents_sessions_turns_items_list` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/turns` | `agents_sessions_turns_list` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/sessions/{id}` | `agents_sessions_update` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}` | `agents_subagents_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/items` | `agents_subagents_items_list` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents` | `agents_subagents_list` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}` | `agents_subagents_turns_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}/items` | `agents_subagents_turns_items_list` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns` | `agents_subagents_turns_list` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/traces` | `agents_traces_list` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/vaults/{vault_id}/credentials` | `agents_vault_credentials_create` | — | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `agents_vault_credentials_delete` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `agents_vault_credentials_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/vaults/{vault_id}/credentials` | `agents_vault_credentials_list` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `agents_vault_credentials_update` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/vaults` | `agents_vaults_create` | — | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/vaults/{vault_id}` | `agents_vaults_delete` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/vaults/{vault_id}` | `agents_vaults_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/vaults` | `agents_vaults_list` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/vaults/{vault_id}` | `agents_vaults_update` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/webhook_event_types` | `agents_webhook_event_types` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/webhook_endpoints` | `agents_webhooks_create` | — | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/webhook_endpoints/{webhook_endpoint_id}` | `agents_webhooks_delete` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/webhook_endpoints/{webhook_endpoint_id}` | `agents_webhooks_get` | — | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/webhook_endpoints` | `agents_webhooks_list` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}/rotate_secret` | `agents_webhooks_rotate_secret` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}/test` | `agents_webhooks_test` | — | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}` | `agents_webhooks_update` | — | enabled, scopes, audit; common limits only |
| `browser` | POST | `/browser/click` | `browser_click` | browser:use | common limits only |
| `browser` | GET | `/browser/console` | `browser_console` | browser:use | common limits only |
| `browser` | GET | `/browser/content` | `browser_content` | browser:use | common limits only |
| `browser` | POST | `/browser/evaluate` | `browser_evaluate` | browser:evaluate | executes a program |
| `browser` | POST | `/browser/navigate` | `browser_navigate` | browser:use | params: block_private_networks, url_allow, url_deny; executes a program |
| `browser` | POST | `/browser/pdf` | `browser_pdf` | browser:use | common limits only |
| `browser` | POST | `/browser/screenshot` | `browser_screenshot` | browser:use | common limits only |
| `browser` | POST | `/browser/type` | `browser_type` | browser:use | common limits only |
| `commands` | GET | `/commands` | `list_commands` | commands:list | common limits only |
| `commands` | POST | `/commands/{name}` | `run_command` | commands:run | common limits only |
| `core` | GET | `/capabilities` | `capabilities` | core:read | cannot disable |
| `core` | POST | `/capabilities/check` | `capabilities_check` | core:read | cannot disable |
| `core` | GET | `/health` | `health` | — | cannot disable |
| `dev_tools` | POST | `/code/run` | `code_run` | devtools:run | params: languages; limits: max_output_bytes, timeout_seconds; executes a program |
| `dev_tools` | GET | `/git/diff` | `git_diff` | devtools:read | paths |
| `dev_tools` | GET | `/git/status` | `git_status` | devtools:read | paths |
| `file_ops` | GET | `/download` | `download` | files:read | paths; limits: max_bytes |
| `file_ops` | POST | `/files/archive` | `files_archive` | files:read | paths; limits: max_bytes, max_files |
| `file_ops` | DELETE | `/files` | `files_delete` | files:delete | paths |
| `file_ops` | GET | `/files/download-stream` | `files_download_stream` | files:read | paths; limits: max_bytes |
| `file_ops` | GET | `/files/list` | `files_list` | files:read | paths; limits: max_depth, max_entries |
| `file_ops` | POST | `/files/mkdir` | `files_mkdir` | files:write | paths |
| `file_ops` | POST | `/files/move` | `files_move` | files:write, files:delete | paths |
| `file_ops` | POST | `/files/search` | `files_search` | files:read | paths; limits: max_depth, max_results, timeout_seconds |
| `file_ops` | GET | `/files/stat` | `files_stat` | files:read | paths |
| `file_ops` | POST | `/files/upload-stream` | `files_upload_stream` | files:write | paths; params: allow_extensions, deny_extensions, overwrite; limits: max_bytes |
| `file_ops` | GET | `/files/watch` | `files_watch` | files:read | paths; limits: max_duration_seconds |
| `file_ops` | POST | `/upload` | `upload` | files:write | paths; params: allow_extensions, deny_extensions, overwrite; limits: max_bytes |
| `process` | GET | `/process/{pid}` | `process_detail` | process:read | common limits only |
| `process` | GET | `/process/list` | `process_list` | process:read | common limits only |
| `process` | GET | `/process/{pid}/output` | `process_output` | process:read | common limits only |
| `process` | POST | `/process/{pid}/signal` | `process_signal` | process:manage | params: allowed_signals |
| `process` | POST | `/process/start` | `process_start` | process:run | paths; params: allow_commands, deny_commands; limits: max_output_bytes, max_processes, timeout_seconds; executes a program |
| `process` | POST | `/process/{pid}/stdin` | `process_stdin` | process:manage | common limits only |
| `process` | POST | `/shell` | `shell` | process:run | paths; params: allow_commands, deny_commands; limits: max_output_bytes, max_processes, timeout_seconds; executes a program |
| `process` | POST | `/shell/stream` | `shell_stream` | process:run | paths; params: allow_commands, deny_commands; limits: max_output_bytes, max_processes, timeout_seconds; executes a program |
| `system` | GET | `/env` | `env_get` | system:read | params: allow_vars, deny_vars |
| `system` | POST | `/env` | `env_set` | system:write | params: allow_vars, deny_vars |
| `system` | GET | `/packages` | `packages` | system:read | common limits only |
| `system` | GET | `/ports` | `ports` | system:read | common limits only |
| `system` | GET | `/system/info` | `system_info` | system:read | common limits only |
| `system` | GET | `/system/metrics` | `system_metrics` | system:read | common limits only |
| `terminal` | POST | `/pty/sessions` | `pty_create_session` | terminal:use | params: env_deny, shells; limits: max_sessions |
| `terminal` | DELETE | `/pty/sessions/{id}` | `pty_delete_session` | terminal:use | common limits only |
| `terminal` | GET | `/pty/sessions/{id}` | `pty_detail` | terminal:use | common limits only |
| `terminal` | GET | `/pty/sessions` | `pty_list_sessions` | terminal:use | common limits only |
| `terminal` | POST | `/pty/sessions/{id}/resize` | `pty_resize` | terminal:use | common limits only |

## How this meets the Agents API case

`agents-cli` sets `groups.agents` and enables only:

| Endpoint id | Route |
|---|---|
| `agents_sessions_create` | `POST /v1/agents/sessions` |
| `agents_sessions_get` | `GET /v1/agents/sessions/{id}` |
| `agents_sessions_list` | `GET /v1/agents/sessions` |
| `agents_sessions_events_create` | `POST /v1/agents/sessions/{id}/events` |
| `agents_sessions_items_list` | `GET /v1/agents/sessions/{id}/items` |
| `agents_runtimes_list` | `GET /v1/agents/runtimes` |

The local e2e recorded `POST /shell` as 404, `POST /v1/agents` (definitions) as 404, and the Codex and Qwen Code session, event, and item calls as 200 / 202. To open another route, add its endpoint id to `ServerPolicy.only` and to `endpoints` in `template.yaml`.
