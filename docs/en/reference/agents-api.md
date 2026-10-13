# Agents API reference

Every HTTP route the sandbox server serves once the `agents` capability group is on. The group is off by default. All 70 routes below are implemented and each one has a test. Two runtimes have a local backend: **Codex** (binary `codex`) and **Qwen Code** (binary `qwen`). `claude-code`, `cursor` and `command` are declared adapters with no local backend: `GET /v1/agents/runtimes` reports `implemented: false` for them, and a request that selects one gets `404` `agents.not_implemented_locally` whose body points at `GET /v1/agents/runtimes`.

This is not `sb.agent.*`. Usage and the worked case are in [Agents API](../guide/agents-api.md). Field-level refusals are in [Hosted agents](../guide/hosted-agents.md). This page lists parameters and responses per route.

Endpoints are declared in `server-sdk/src/agent_sandbox/server/endpoints.py`; handlers are mounted in `routes_agents.py`.

## Common conventions

Turn the group on:

```bash
export ABX_SERVER_ENABLED_GROUPS=agents      # or server.groups: [agents] in template.yaml
python -m agent_sandbox.server serve --port 9000
```

| Item | Value |
|---|---|
| Base URL | `http://<host>:9000`. An OpenAI-style client uses `base_url=http://<host>:9000/v1` |
| Request body | `Content-Type: application/json`, an object. An empty body is `{}` |
| Token | With `ABX_SERVER_TOKEN` set, every route accepts `X-Access-Token` or `Authorization: Bearer` |
| Local marker | Every response, errors included, has the header `X-Agent-Sandbox-Local: 1`. Success objects carry `x_agent_sandbox`. `compute` is `local_process`, `local_state` or `none`, never `openai_hosted` |
| Owner | The caller's identity id (`anonymous` when no token is set). Another owner's id and a missing id get the same answer |

Error envelope:

```json
{
  "error": {
    "message": "explanation",
    "type": "invalid_request_error",
    "param": "field name or null",
    "code": "agents.not_implemented_locally"
  }
}
```

`type` is `not_found_error` for 404. A variant the server cannot honor is **400** with `x-should-retry: false`. A route with no local capability, and a request that selects a runtime that is not implemented, is **404** with `code` `agents.not_implemented_locally`, `x-should-retry: false`, and `x_agent_sandbox.runtimes` pointing at `/v1/agents/runtimes`. A disabled endpoint is 404 `endpoint_disabled` with a `rule` that names the layer that turned it off.

List envelope (every route the tables below call a list):

| Query parameter | Meaning |
|---|---|
| `limit` | Integer 1-100, default 20. Outside that is 400 `invalid_request`, `param=limit` |
| `order` | `asc` or `desc`, default `desc`. Any other value is 400 |
| `after` | The `id` of the last item of the previous page. Not in the current sequence is 404 `agents.cursor_not_found` |

```json
{
  "object": "list",
  "data": [],
  "first_id": null,
  "last_id": null,
  "has_more": false
}
```

Main fields of the session object `agent.session`: `id`, `object`, `agent` (`id`, `name`, `model`, `instructions`, `tools`, `multi_agent.enabled`, `reasoning`, `service_tier`, `text`), `created_at`, `environment` (`type=self_hosted`, `id`, `workspace_directory`), `status`, `metadata`, `usage`, `vault_ids`, `error`, `required_actions`, `last_active_at`, `x_agent_sandbox`.

Adapter selection order: the header `X-ABX-Adapter`, or the body `adapter` / `runtime`, or `agent.model` / `model` being exactly `codex`, `openai-codex`, `qwen-code`, `qwen`, `qwen_code` or `qwencode`. A model id such as `gpt-5` is passed to the selected CLI and does not select an adapter. With none of them the first in product order is used: `codex`. `default` / `agents.default` in `ABX_AGENTS_DEFAULT` or `ABX_AGENTS_CONFIG` changes that default. `GET /v1/agents/runtimes?order=asc` lists `codex`, `qwen-code`, then the declared-only adapters. Lists default to `order=desc`. `default: true` marks the current default regardless of array index. A declared adapter that is not implemented (`claude-code`, `cursor`, `command`) is 404 `agents.not_implemented_locally`; so is an unknown name. Each route can be enabled on its own; the endpoint ids have the default scope `agents:use`, see [Fine-grained capabilities](../guide/fine-grained-capabilities.md).

The CLIs are not in the base image. Install one when you need it:

```bash
npm install -g @openai/codex
npm install -g @qwen-code/qwen-code
```

## Sessions, events, items, turns

### `POST /v1/agents/sessions`

Creates a session. **200**, the body is an `agent.session`.

| Field | Where | Notes |
|---|---|---|
| `agent` | body | Object. `model` is an adapter name or a model id to pass to the CLI. `instructions` is optional |
| `agent_id` | body | Id of a saved definition. When given, the adapter is not chosen from `model` |
| `adapter` / `runtime` | body or inside `agent` | Explicit adapter name |
| `input` | body | Optional. A string, or a message with `input_text`. Non-empty content queues a turn at once |
| `metadata` | body | Object of string scalars. Nested objects, arrays and `null` are 400 |
| `environment` | body | Optional `{ "type": "self_hosted", "id": "env_..." }` |
| `vault_ids` | body | Optional array of strings |
| `X-ABX-Adapter` | header | Optional |

`environment.type` is always `self_hosted`. `workspace_directory` defaults to `/workspace`.

### `GET /v1/agents/sessions`

List. Besides paging, the query accepts `agent_id` (filter by definition id). **200**, a list of `agent.session`.

### `GET /v1/agents/sessions/{id}`

Path parameter `id`. **200**, one `agent.session`. Missing is **404** `resource_not_found`.

### `POST /v1/agents/sessions/{id}`

Updates `metadata` only. `agent`, `vault_ids`, `environment` or any other key in the body is **400**. **200**, the updated `agent.session`.

### `DELETE /v1/agents/sessions/{id}`

Deletes the session and clears the artifact snapshots. **200**:

```json
{ "id": "agsess_...", "object": "agent.session.deleted", "deleted": true, "x_agent_sandbox": {} }
```

### `POST /v1/agents/sessions/{id}/events`

Queues a turn. **202**, **empty body**.

| Field | Notes |
|---|---|
| `events` | Non-empty array of objects |
| `events[].type` | `agent.session.input.message` or `input.message` takes `input` / `content` / `text`. `agent.session.input.cancel` or `input.cancel` cancels. `tool_result` and `computer_use_approval_request_result` are 400 `agents.tool_result_unsupported`. Any other type is 400 |
| `input` | Without `events`, one input may be given directly |
| `Idempotency-Key` | Optional header. The same key with the same body replays this 202. The same key with a different body is **409** `idempotency.mismatch` |

`input_image` and `input_file` are 400. Input sent during a turn queues a new turn (`queued_not_steered`); it is never written into the running process.

### `GET /v1/agents/sessions/{id}/events`

SSE, `Accept: text/event-stream`. Query `after`: without it the stream follows from now until that turn ends; `after=0` or `after=evt_<seq>` replays and closes. The frame `id` is the runtime sequence number.

### `GET /v1/agents/sessions/{id}/items`

### `GET /v1/agents/sessions/{id}/turns`

### `GET /v1/agents/sessions/{id}/turns/{turn_id}`

### `GET /v1/agents/sessions/{id}/turns/{turn_id}/items`

All are lists. For an item with `type=message`, `content[].type` is `output_text` and `content[].text` is the CLI text. In the local case Codex's text is `hello-from-fake-codex` and Qwen Code's is `hello-from-fake-qwen`.

### `GET /v1/agents/runtimes`

**200**, a list with every declared runtime. Implemented ones come first (`codex`, `qwen-code`), then the declared-only adapters. Each entry:

| Field | Notes |
|---|---|
| `id` / `name` | `codex`, `qwen-code`, `claude-code`, `cursor` or `command` |
| `implemented` | Whether the server has a local backend. Only `codex` and `qwen-code` are `true`. A runtime with `false` is refused whatever `installed` says |
| `installed` | Whether the binary is on the current `PATH` |
| `default` | Whether a request that names no adapter uses this one. Product order is `codex` then `qwen-code`; `order=asc` sorts that way. The default is `order=desc` |
| `object` | `agent.runtime` |
| `aliases` | Codex: `openai-codex`. Qwen: `qwen`, `qwen_code`, `qwencode` |
| `binary` | The runtime's binary name |
| `path` | Where it was found |
| `install_steps` | `[["npm","install","-g","@openai/codex"]]`, or the Qwen package `@qwen-code/qwen-code` |
| `auth_env_present` | Whether the process already has the CLI's key variable |
| `x_agent_sandbox` | `compute: none`, plus `installed` and `implemented` |

## Artifacts, traces, subagents

| Method | Path | Success | Response |
|---|---|---|---|
| GET | `/v1/agents/sessions/{id}/artifacts` | 200 list | Snapshots of files the CLI reported. The workspace is not scanned |
| GET | `/v1/agents/sessions/{id}/artifacts/{artifact_id}` | 200 | One artifact. `path` looks like `/workspace/<relative path>` |
| DELETE | same | 200 | Deletes the snapshot only. `deleted_scope` is `snapshot`; the original file is untouched |
| GET | `.../artifacts/{artifact_id}/content` | 200 | Snapshot bytes, `X-Content-Type-Options: nosniff` |
| GET | `/v1/agents/sessions/{id}/traces` | 200 list | Empty by default. With `ABX_AGENTS_TRACES=1`, one trace per finished turn with timing and item counts, no content |
| GET | `.../subagents` | 200 list | Only ids the CLI actually emitted |
| GET | `.../subagents/{subagent_id}` | 200 | One subagent. Any other id is 404 `resource_not_found`, same as a missing one |
| GET | `.../subagents/{subagent_id}/items` | 200 list | |
| GET | `.../subagents/{subagent_id}/turns` | 200 list | |
| GET | `.../turns/{turn_id}` | 200 | |
| GET | `.../turns/{turn_id}/items` | 200 list | |

`multi_agent.enabled=true` is still 400.

## Environments, files, templates

### `POST /v1/agents/environments`

Body: `type` must resolve to `self_hosted`. A bare `{ "type": "openai_hosted" }` is converted to `self_hosted` and noted in `x_agent_sandbox.differences`. `openai_hosted` with configuration is 400.

| Field | Notes |
|---|---|
| `workspace_directory` | Absolute path, no `..`, not `/`, `/etc`, `/proc` and the like |
| `env` | Applied at creation, never returned. `PATH`, `HOME`, secrets, proxies, `CODEX_*`, `QWEN_*`, `GIT_*`, `ABX_*` are refused |
| `files` | Inline files, written under the workspace at creation |

400: `network`, `packages`, `setup_commands`, `plugins`, `skills`, `desktop`, `container_size`, `capability_directories`. **200**, an environment object. No container is provisioned.

### `GET /v1/agents/environments`

List. **200**.

### `GET /v1/agents/environments/{environment_id}`

**200**, one environment, or 404.

### `POST /v1/agents/environments/{environment_id}/files`

Body: `path` and the content. The path is relative to the workspace. A symlink is 400. An existing file with different content is 400 `agents.file_exists`. Writing `.git/`, `.codex/`, `.claude/`, `.cursor/`, `.qwen/`, `.qoder/`, `.ssh/`, or `.mcp.json`, `AGENTS.md`, `QWEN.md`, a shell rc file, is 400 `agents.path_refused`. Size limit `ABX_AGENTS_MAX_FILE_BYTES`, default 10 MiB. **200**.

### `GET /v1/agents/environments/{environment_id}/files`

**200** list. Regular files only. Query `page` is an opaque paging token; the next page is in `next`.

### Environment templates

| Method | Path | Body | Success |
|---|---|---|---|
| POST | `/v1/agents/environments/templates` | `{name, env, files}`. Fields the environment refuses are 400 here too | 200 |
| GET | `/v1/agents/environments/templates` | none | 200 list. `env` values and file contents are not returned, only `size_bytes` |
| GET | `.../templates/{environment_template_id}` | none | 200 |
| POST | same | update `{name, env, files}` | 200 |
| DELETE | same | none | 200 |

A template is applied to an environment through `environment_template_id` on a session or environment.

### Executor routes that are refusals

| Method | Path | Response |
|---|---|---|
| POST | `/v1/agents/environments/{environment_id}/register` | 404 `agents.not_implemented_locally` |
| GET | `/v1/agents/environments/{environment_id}/connect` | same |

## Agent definitions

### `POST /v1/agents`

| Field | Notes |
|---|---|
| `model` | Required, unless the string is itself an adapter name. Otherwise passed to the CLI as `-m` |
| `name` | Optional |
| `instructions` | Optional |
| `metadata` | Object of string scalars |
| `tools` | Only `type=mcp` tools with `http` transport. `stdio`, `allowed_tools` and other tool types are 400 |
| `reasoning.effort` | Codex only. 400 on Qwen Code |
| `reasoning.summary` | 400 |
| `multi_agent.enabled` | 400 |
| `service_tier` | Only `auto` or `default` |
| `text.verbosity` | Only `medium` |
| `text.format` | Only `text` |

**200**. `id` looks like `agent_...`. MCP header values are `"***"` in the response.

### `GET /v1/agents`

**200** list.

### `GET /v1/agents/{agent_id}`

**200**, or 404 `resource_not_found` with `param=agent_id`.

### `POST /v1/agents/{agent_id}`

Updates in place. Omitted fields are unchanged. `adapter` or `runtime` in the body is 400: a definition cannot change runtime. **200**. A running session keeps the copy it started with.

### `DELETE /v1/agents/{agent_id}`

**200**: `{ "id", "object": "agent.deleted", "deleted": true }`. Existing sessions are not stopped.

## Vaults and credentials

Vaults live in memory. Each owner may hold at most `ABX_AGENTS_MAX_VAULTS` (100 by default).

| Method | Path | Body | Success |
|---|---|---|---|
| POST | `/v1/vaults` | Only `name` and `metadata`. Other keys are 400 | 200. The object has only `id`, `name`, `metadata`, `created_at` |
| GET | `/v1/vaults` | paging | 200 list |
| GET | `/v1/vaults/{vault_id}` | none | 200, or 404 |
| POST | `/v1/vaults/{vault_id}` | only `name`, `metadata` may change | 200 |
| DELETE | `/v1/vaults/{vault_id}` | none | 200 |

Credentials:

| Method | Path | Body | Success |
|---|---|---|---|
| POST | `.../credentials` | `name` required, `metadata` optional, `auth` required | 200. The response carries no secret value, prefix, length or hash |
| GET | `.../credentials` | paging | 200 list |
| GET | `.../credentials/{credential_id}` | none | 200 |
| POST | same | update `auth` and other allowed fields | 200. Takes effect from the next turn |
| DELETE | same | none | 200 |

`auth` allows `static_bearer`, or `mcp_oauth` with an access token. 400: `environment_variable`, `mcp_oauth.refresh`, `networking.unrestricted`, `limited` hosts other than the credential's host, an `mcp_server_url` that is not `https` or points at a private network, a token containing a newline.

Once attached through a session's `vault_ids`, a credential is injected only into an MCP tool whose scheme, host and port all match, as an `Authorization` header in the child process environment, never in `argv`. When two credentials match, `credential_id` is required. A credential that is deleted or past `expires_at` makes the next event 400 `agents.credential_unavailable` or `agents.credential_expired`.

## Responses

`POST /v1/responses` treats one CLI turn as one response. The `object` of a success is `response`.

| Field | Notes |
|---|---|
| `model` | The id of a saved definition, or a model passed through to the CLI (for example `gpt-5-codex`). A runtime name such as `qwen` means the CLI's default model, and the response has `model_resolved: false` |
| `input` | A string, or `user` / `system` / `developer` messages with `input_text` content |
| `instructions` | Optional string |
| `metadata` | String scalars |
| `store` | Omitted or true stores it. `false` together with `background` is 400. A `store: false` response disappears when the turn ends |
| `background` | Boolean. When true you need not wait for the turn |
| `stream` | When true, the finished turn is replayed as SSE (`response.created`, `response.output_text.delta`, `response.completed`) |
| `previous_response_id` | Continues a previous one. Only the latest response of that conversation can be continued, otherwise 400 `agents.previous_response_not_latest` |
| `tools` | MCP only: `server_label`, `server_url`, write-only `headers` and `authorization` |
| `reasoning.effort` | Codex only |

400: a non-MCP entry in `tools`, `conversation`, `prompt`, a `text.format` other than `text`, any `include`, `service_tier` other than `auto|default`, `tool_choice` other than `auto`, `input_image`, `input_file`, assistant history, unknown parameters. `temperature`, `top_p` and `max_output_tokens` are ignored and listed in the response header `X-Agent-Sandbox-Ignored-Params`.

Output items are only what the CLI actually produced: `message`, `reasoning`, `command_execution`, `mcp_call`, and `tool_call` (with `tool_name`) for other tools. `web_search_call`, `function_call`, `code_interpreter_call` and `local_shell_call` never appear. When the CLI reports no usage, `usage` is `null`.

| Method | Path | Success |
|---|---|---|
| POST | `/v1/responses` | 200, or SSE with `stream: true` |
| GET | `/v1/responses` | 400 `agents.websocket_upgrade_required` without a WebSocket upgrade |
| POST | `/v1/responses/input_tokens` | **404** `agents.not_implemented_locally`. There is no tokenizer that matches the CLI's model |
| POST | `/v1/responses/compact` | The body needs `previous_response_id`. Qwen runs a local `/compress`. Codex is 400 `agents.compact_unsupported` |
| GET | `/v1/responses/{response_id}` | 200. `?stream=true&starting_after=N` replays again |
| DELETE | `/v1/responses/{response_id}` | 200 |
| POST | `.../cancel` | 200 with the terminal object. An already finished one is 400 `agents.not_cancellable`, not 409 |
| GET | `.../input_items` | 200 list. The input accepted at creation |

`Idempotency-Key` replays the first response. A different body is 409.

## Models, files, webhooks

| Method | Path | Parameters | Success |
|---|---|---|---|
| GET | `/v1/models` | paging | 200 list. The caller's definitions and the two implemented runtimes. `owned_by` is `agent-sandbox-local` |
| GET | `/v1/models/{model}` | path `model` | 200, or 404 `model_not_found`. No side effect |
| DELETE | `/v1/models/{model}` | | **404** `agents.not_implemented_locally`. Delete a definition with `DELETE /v1/agents/{agent_id}` |
| POST | `/v1/files` | JSON: `purpose` must be `user_data`, `filename`, `data` as base64. Multipart is not parsed | 200. The `file_id` lives in memory. Using an id that was never issued is 400 |

Webhooks. The signing secret `whsec_...` is returned once, on creation and on rotation.

| Method | Path | Body | Success |
|---|---|---|---|
| POST | `/v1/webhook_endpoints` | Only `url`, `event_types`, `name`. `url` must be `https`, with no userinfo, no query string, not a private or loopback address. For local development set `ABX_AGENTS_WEBHOOK_ALLOW_HTTP=1` and `ABX_AGENTS_ALLOW_PRIVATE_URLS=1` | 200, with a one-time `secret` |
| GET | `/v1/webhook_endpoints` | paging | 200 list. No secret |
| GET | `.../{webhook_endpoint_id}` | none | 200. No secret |
| POST | same | `url`, `event_types`, `name` | 200 |
| DELETE | same | none | 200 |
| POST | `.../rotate_secret` | `keep_old_secret_active_for_24_hours` is 400 | 200, the new secret appears only this once |
| POST | `.../test` | `event_type` | 200. The server signs and delivers per Standard Webhooks |
| GET | `/v1/webhook_event_types` | none | 200. Accepts `agent.session.created`, `in_progress`, `idle`, `failed`. `agent.session.action_required` is not accepted |

## Route index

All 70 routes. Endpoint ids are the ones `GET /capabilities` and the policy use. The four marked `refusal` exist to explain with a typed 404 that the server has no such capability (`agents.not_implemented_locally`); they are declared, counted and tested like the rest.

| Endpoint id | Method | Path | Status |
|---|---|---|---|
| `agents_sessions_create` | POST | `/v1/agents/sessions` | implemented |
| `agents_sessions_list` | GET | `/v1/agents/sessions` | implemented |
| `agents_sessions_get` | GET | `/v1/agents/sessions/{id}` | implemented |
| `agents_sessions_update` | POST | `/v1/agents/sessions/{id}` | implemented |
| `agents_sessions_delete` | DELETE | `/v1/agents/sessions/{id}` | implemented |
| `agents_sessions_events_create` | POST | `/v1/agents/sessions/{id}/events` | implemented |
| `agents_sessions_events_stream` | GET | `/v1/agents/sessions/{id}/events` | implemented |
| `agents_sessions_items_list` | GET | `/v1/agents/sessions/{id}/items` | implemented |
| `agents_sessions_turns_list` | GET | `/v1/agents/sessions/{id}/turns` | implemented |
| `agents_sessions_turns_get` | GET | `/v1/agents/sessions/{id}/turns/{turn_id}` | implemented |
| `agents_sessions_turns_items_list` | GET | `/v1/agents/sessions/{id}/turns/{turn_id}/items` | implemented |
| `agents_artifacts_list` | GET | `/v1/agents/sessions/{id}/artifacts` | implemented |
| `agents_artifacts_get` | GET | `/v1/agents/sessions/{id}/artifacts/{artifact_id}` | implemented |
| `agents_artifacts_delete` | DELETE | `/v1/agents/sessions/{id}/artifacts/{artifact_id}` | implemented |
| `agents_artifacts_content` | GET | `/v1/agents/sessions/{id}/artifacts/{artifact_id}/content` | implemented |
| `agents_traces_list` | GET | `/v1/agents/sessions/{id}/traces` | implemented |
| `agents_subagents_list` | GET | `/v1/agents/sessions/{id}/subagents` | implemented |
| `agents_subagents_get` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}` | implemented |
| `agents_subagents_items_list` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/items` | implemented |
| `agents_subagents_turns_list` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns` | implemented |
| `agents_subagents_turns_get` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}` | implemented |
| `agents_subagents_turns_items_list` | GET | `/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}/items` | implemented |
| `agents_runtimes_list` | GET | `/v1/agents/runtimes` | implemented |
| `agents_environments_create` | POST | `/v1/agents/environments` | implemented |
| `agents_environments_list` | GET | `/v1/agents/environments` | implemented |
| `agents_environment_templates_create` | POST | `/v1/agents/environments/templates` | implemented |
| `agents_environment_templates_list` | GET | `/v1/agents/environments/templates` | implemented |
| `agents_environment_templates_get` | GET | `/v1/agents/environments/templates/{environment_template_id}` | implemented |
| `agents_environment_templates_update` | POST | `/v1/agents/environments/templates/{environment_template_id}` | implemented |
| `agents_environment_templates_delete` | DELETE | `/v1/agents/environments/templates/{environment_template_id}` | implemented |
| `agents_environments_get` | GET | `/v1/agents/environments/{environment_id}` | implemented |
| `agents_environment_files_create` | POST | `/v1/agents/environments/{environment_id}/files` | implemented |
| `agents_environment_files_list` | GET | `/v1/agents/environments/{environment_id}/files` | implemented |
| `agents_cannot_executor_registration` | POST | `/v1/agents/environments/{environment_id}/register` | refusal |
| `agents_cannot_executor_channel` | GET | `/v1/agents/environments/{environment_id}/connect` | refusal |
| `agents_definitions_create` | POST | `/v1/agents` | implemented |
| `agents_definitions_list` | GET | `/v1/agents` | implemented |
| `agents_definitions_get` | GET | `/v1/agents/{agent_id}` | implemented |
| `agents_definitions_update` | POST | `/v1/agents/{agent_id}` | implemented |
| `agents_definitions_delete` | DELETE | `/v1/agents/{agent_id}` | implemented |
| `agents_vaults_create` | POST | `/v1/vaults` | implemented |
| `agents_vaults_list` | GET | `/v1/vaults` | implemented |
| `agents_vaults_get` | GET | `/v1/vaults/{vault_id}` | implemented |
| `agents_vaults_update` | POST | `/v1/vaults/{vault_id}` | implemented |
| `agents_vaults_delete` | DELETE | `/v1/vaults/{vault_id}` | implemented |
| `agents_vault_credentials_create` | POST | `/v1/vaults/{vault_id}/credentials` | implemented |
| `agents_vault_credentials_list` | GET | `/v1/vaults/{vault_id}/credentials` | implemented |
| `agents_vault_credentials_get` | GET | `/v1/vaults/{vault_id}/credentials/{credential_id}` | implemented |
| `agents_vault_credentials_update` | POST | `/v1/vaults/{vault_id}/credentials/{credential_id}` | implemented |
| `agents_vault_credentials_delete` | DELETE | `/v1/vaults/{vault_id}/credentials/{credential_id}` | implemented |
| `agents_responses_create` | POST | `/v1/responses` | implemented |
| `agents_responses_connect` | GET | `/v1/responses` | implemented |
| `agents_cannot_responses_input_tokens` | POST | `/v1/responses/input_tokens` | refusal |
| `agents_responses_compact` | POST | `/v1/responses/compact` | implemented |
| `agents_responses_get` | GET | `/v1/responses/{response_id}` | implemented |
| `agents_responses_delete` | DELETE | `/v1/responses/{response_id}` | implemented |
| `agents_responses_cancel` | POST | `/v1/responses/{response_id}/cancel` | implemented |
| `agents_responses_input_items` | GET | `/v1/responses/{response_id}/input_items` | implemented |
| `agents_models_list` | GET | `/v1/models` | implemented |
| `agents_models_get` | GET | `/v1/models/{model}` | implemented |
| `agents_cannot_models_delete` | DELETE | `/v1/models/{model}` | refusal |
| `agents_files_create` | POST | `/v1/files` | implemented |
| `agents_webhooks_create` | POST | `/v1/webhook_endpoints` | implemented |
| `agents_webhooks_list` | GET | `/v1/webhook_endpoints` | implemented |
| `agents_webhooks_get` | GET | `/v1/webhook_endpoints/{webhook_endpoint_id}` | implemented |
| `agents_webhooks_update` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}` | implemented |
| `agents_webhooks_delete` | DELETE | `/v1/webhook_endpoints/{webhook_endpoint_id}` | implemented |
| `agents_webhooks_rotate_secret` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}/rotate_secret` | implemented |
| `agents_webhooks_test` | POST | `/v1/webhook_endpoints/{webhook_endpoint_id}/test` | implemented |
| `agents_webhook_event_types` | GET | `/v1/webhook_event_types` | implemented |

## End-to-end coverage

| Case | Interfaces covered | Notes |
|---|---|---|
| `examples/agents/complete_case.py` | `POST /v1/agents/sessions`, `POST .../events`, `GET .../items`, `GET /v1/agents/runtimes`. With no adapter named, `agent.id` is `codex`. `claude-code` is 404 | The events response is a 202 with an empty body. The assistant text in the example comes from a local program on `PATH`; no model key is read |
| `examples/agents/hosted_codex.py`, `hosted_qwen.py` | The same session interfaces, against an already started server | The same 200 / 202 / item text as above |
| `examples/scenarios/agent_loop_local.py` | Not the Agents API. Sandbox commands: health, shell, read a file, SIGTERM | stdout `'4\n'`, read back `answer=4`, returns -15 |

Parameters and responses of definitions, environments, vaults, responses and webhooks are as in the tables above.
