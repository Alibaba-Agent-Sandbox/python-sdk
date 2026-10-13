# Fine-grained capabilities

Every route has one endpoint id, and one rule per endpoint decides whether it can be called and which path, command, size, and rate limits apply. There is no second gate in front of the rules. `agents-cli` exposes only the session routes and leaves `POST /shell` and `POST /v1/agents` closed. That is this layer.

The design note is [Fine-grained capabilities](../design/fine-grained-capabilities.md). Path and command enforcement is in [File and command controls](file-and-command-controls.md). Agents request and response shapes are in [Agents API](agents-api.md). The full route table is in the [Agents API reference](../reference/agents-api.md).

## One switch: the endpoint

An endpoint id (`upload`, `files_list`, `agents_sessions_create`) is the unit everything uses: the policy, the audit log, `GET /capabilities`, and the client. A group is only a **name for a set of endpoint ids**. Writing `groups: [file_ops]`, `group:file_ops`, `table.enable_group(CapabilityGroup.FILE_OPS)`, or `ABX_SERVER_ENABLED_GROUPS=file_ops` expands to the ids declared in that group, and the result is the same per-endpoint rule set.

Defaults: `core` is always on. `agents`, `dev_tools`, and `browser` are opt-in and start off. `file_ops`, `process`, `terminal`, `system`, and `commands` start on. `health`, `capabilities`, and `capabilities_check` cannot be turned off.

Rules come from five layers and are merged per endpoint:

| Layer | Source | Can turn on | Can turn off |
|---|---|---|---|
| default | the built-in opt-in groups | no | yes (opt-in groups) |
| code | `default_table().enable_group()` / `disable_group()` in the template's `commands.py` | yes | yes |
| preset | `preset:` | yes | yes |
| policy | `groups`, `defaults`, `endpoints` of the policy document | yes | yes |
| environment | `ABX_SERVER_ENABLED_GROUPS` | yes | no |

The more specific selector wins: an exact id beats a glob, a glob beats `group:<name>`. At equal specificity the later layer wins, and inside one layer a single `enabled: false` turns the endpoint off. So `endpoints.code_run.enabled: false` in the policy stays off even when the environment enables `dev_tools`.

A denial names the rule that denied it. The 404 body carries `code: endpoint_disabled` and `rule`, for example `policy:endpoints.shell`, `policy:groups.process`, `preset:read-only`, `code:enable_group:file_ops`, or `default:opt-in:browser`. `GET /capabilities` reports the same `rule` per endpoint. Its `groups` and `group_summary` fields are derived from the endpoint state (`{"file_ops": {"enabled": 11, "total": 12}}`), never stored.

`ABX_SERVER_ENABLED_GROUPS` is the only group environment variable. A comma list of group names, such as `agents,dev_tools`. An unknown name stops the process with a did-you-mean message. There is no variable to disable groups. Write `groups: {process: false}` or `endpoints` rules.

## How to turn it on

Three inputs, one document. An invalid document stops the process. It does not fall open.

The `server:` block in `template.yaml`. Tooling compiles it to `/etc/agent-sandbox/server-policy.json`. Accepted keys: `version`, `preset`, `base_dir`, `groups`, `defaults`, `auth`, `endpoints`, `description`. `groups` is either a list of groups to turn on or a map of group to `true`/`false`.

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

Group shorthand, list or map:

```yaml
server:
  groups: [agents, dev_tools]     # same as {agents: true, dev_tools: true}
```

```yaml
server:
  groups:
    process: false
    terminal: false
```

Inline JSON:

```bash
export ABX_SERVER_POLICY='{"groups":["agents"],"endpoints":{"*":{"enabled":false},"agents_sessions_create":{"enabled":true}}}'
```

Or a file:

```bash
export ABX_SERVER_POLICY_FILE=/etc/agent-sandbox/server-policy.json
agent-sandbox-server check-config --policy /etc/agent-sandbox/server-policy.json
```

Lookup order: `ABX_SERVER_POLICY`, then `ABX_SERVER_POLICY_FILE`, then the well-known policy file. With none of them the built-in defaults apply: opt-in groups off, everything else on, no per-endpoint limits.

Python:

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

`ServerPolicy.only` turns `"*"` off, turns the listed ids on, and leaves the core endpoints on. `agents-cli`'s `commands.py` is this call. `only` also accepts `"transfer"` (the four upload and download ids) and `"group:<name>"`.

To open a whole group from `commands.py` without a policy document:

```python
from agent_sandbox.server import CapabilityGroup, default_table

default_table().enable_group(CapabilityGroup.DEV_TOOLS)
```

`enable_group` and `disable_group` are the only code-level switches. `disable_group(CORE)` raises.

## Selectors

| Form | Matches |
|---|---|
| `agents_sessions_create` | That endpoint id |
| `files_*` | Endpoint ids matching the glob |
| `group:file_ops` | Endpoints in that group |
| `*` | Every endpoint |
| `@defaults` | The `defaults` block, applied before each endpoint |

If several matching rules of the same specificity and layer disagree, `enabled: false` wins. A more specific selector can turn the endpoint back on.

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

Agents endpoints are in the built-in catalogue. The default scope is `agents:use`. Enable one endpoint id with `enabled: true`, the same way as `upload`. They have no `paths` and no specialised `params`, so the only other keys are `enabled`, `scopes`, `audit`, and the three limits above. A `paths` or specialised `params` block on them fails policy load.

Presets apply before your endpoint rules:

| Preset | Effect |
|---|---|
| `default` | No extra restriction (opt-in groups stay off) |
| `transfer-only` | Only `upload`, `download`, `files_upload_stream`, `files_download_stream` |
| `read-only` | Turns off process, terminal, dev_tools, and browser, and turns off write endpoints and `env_set` |
| `hardened` | Turns off those groups and denies `/proc`, `/sys`, `/dev`, `.ssh`, `.env`, `*.pem`, and private-key names on file routes |
| `locked` | Only `list_commands` and `run_command` |

Group names: `core`, `commands`, `file_ops`, `process`, `terminal`, `system`, `dev_tools`, `browser`, `agents`. `core` cannot be disabled.

The checker warns (L1) when one identity can both read scoped files and run `shell`, `process_start`, `code_run`, or a PTY. A process can bypass path rules. An Agents session starts the CLI inside the server. It does not need the `process` group for that.

## Endpoint catalogue

This is the endpoint declaration table (`agent_sandbox.server.endpoints.ENDPOINTS`). The route table, the policy, and `GET /capabilities` are all derived from it. `pty_connect` is the WebSocket upgrade, served on the PTY port. Agents rows use the scope `agents:use`. They have fewer knobs than file routes that take a path, because these routes do not accept paths or specialised parameters.

| Group | Method | Path | Endpoint id | Scope | Knobs |
|---|---|---|---|---|---|
| `agents` | GET | `/v1/agents/sessions/{id}/artifacts/{artifact_id}/content` | `agents_artifacts_content` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/agents/sessions/{id}/artifacts/{artifact_id}` | `agents_artifacts_delete` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/artifacts/{artifact_id}` | `agents_artifacts_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/artifacts` | `agents_artifacts_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments/{environment_id}/connect` | `agents_cannot_executor_channel` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/environments/{environment_id}/register` | `agents_cannot_executor_registration` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/models/{model}` | `agents_cannot_models_delete` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/responses/input_tokens` | `agents_cannot_responses_input_tokens` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents` | `agents_definitions_create` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/agents/{agent_id}` | `agents_definitions_delete` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/{agent_id}` | `agents_definitions_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents` | `agents_definitions_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/{agent_id}` | `agents_definitions_update` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/environments/{environment_id}/files` | `agents_environment_files_create` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments/{environment_id}/files` | `agents_environment_files_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/environments/templates` | `agents_environment_templates_create` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/agents/environments/templates/{environment_template_id}` | `agents_environment_templates_delete` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments/templates/{environment_template_id}` | `agents_environment_templates_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments/templates` | `agents_environment_templates_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/environments/templates/{environment_template_id}` | `agents_environment_templates_update` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/environments` | `agents_environments_create` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments/{environment_id}` | `agents_environments_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/environments` | `agents_environments_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/files` | `agents_files_create` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/models/{model}` | `agents_models_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/models` | `agents_models_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/responses/{response_id}/cancel` | `agents_responses_cancel` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/responses/compact` | `agents_responses_compact` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/responses` | `agents_responses_connect` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/responses` | `agents_responses_create` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/responses/{response_id}` | `agents_responses_delete` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/responses/{response_id}` | `agents_responses_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/responses/{response_id}/input_items` | `agents_responses_input_items` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/runtimes` | `agents_runtimes_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/sessions` | `agents_sessions_create` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/agents/sessions/{id}` | `agents_sessions_delete` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/sessions/{id}/events` | `agents_sessions_events_create` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/events` | `agents_sessions_events_stream` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}` | `agents_sessions_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/items` | `agents_sessions_items_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions` | `agents_sessions_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/turns/{turn_id}` | `agents_sessions_turns_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/turns/{turn_id}/items` | `agents_sessions_turns_items_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/turns` | `agents_sessions_turns_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/agents/sessions/{id}` | `agents_sessions_update` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}` | `agents_subagents_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/items` | `agents_subagents_items_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents` | `agents_subagents_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}` | `agents_subagents_turns_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}/items` | `agents_subagents_turns_items_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns` | `agents_subagents_turns_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/agents/sessions/{id}/traces` | `agents_traces_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/vaults/{vault_id}/credentials` | `agents_vault_credentials_create` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `agents_vault_credentials_delete` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `agents_vault_credentials_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/vaults/{vault_id}/credentials` | `agents_vault_credentials_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `agents_vault_credentials_update` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/vaults` | `agents_vaults_create` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/vaults/{vault_id}` | `agents_vaults_delete` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/vaults/{vault_id}` | `agents_vaults_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/vaults` | `agents_vaults_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/vaults/{vault_id}` | `agents_vaults_update` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/webhook_event_types` | `agents_webhook_event_types` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/webhook_endpoints` | `agents_webhooks_create` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | DELETE | `/v1/webhook_endpoints/{webhook_endpoint_id}` | `agents_webhooks_delete` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/webhook_endpoints/{webhook_endpoint_id}` | `agents_webhooks_get` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | GET | `/v1/webhook_endpoints` | `agents_webhooks_list` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}/rotate_secret` | `agents_webhooks_rotate_secret` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}/test` | `agents_webhooks_test` | agents:use | enabled, scopes, audit; common limits only |
| `agents` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}` | `agents_webhooks_update` | agents:use | enabled, scopes, audit; common limits only |
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
| `terminal` | WS | `/pty` | `pty_connect` | terminal:use | common limits only |
| `terminal` | POST | `/pty/sessions` | `pty_create_session` | terminal:use | params: env_deny, shells; limits: max_sessions |
| `terminal` | DELETE | `/pty/sessions/{id}` | `pty_delete_session` | terminal:use | common limits only |
| `terminal` | GET | `/pty/sessions/{id}` | `pty_detail` | terminal:use | common limits only |
| `terminal` | GET | `/pty/sessions` | `pty_list_sessions` | terminal:use | common limits only |
| `terminal` | POST | `/pty/sessions/{id}/resize` | `pty_resize` | terminal:use | common limits only |

## How this meets the Agents API case

`agents-cli` enables only:

| Endpoint id | Route |
|---|---|
| `agents_sessions_create` | `POST /v1/agents/sessions` |
| `agents_sessions_get` | `GET /v1/agents/sessions/{id}` |
| `agents_sessions_list` | `GET /v1/agents/sessions` |
| `agents_sessions_events_create` | `POST /v1/agents/sessions/{id}/events` |
| `agents_sessions_items_list` | `GET /v1/agents/sessions/{id}/items` |
| `agents_runtimes_list` | `GET /v1/agents/runtimes` |

The local e2e recorded `POST /shell` as 404, `POST /v1/agents` (definitions) as 404, and the Codex and Qwen Code session, event, and item calls as 200 / 202. To open another route, add its endpoint id to `ServerPolicy.only` and to `endpoints` in `template.yaml`.
