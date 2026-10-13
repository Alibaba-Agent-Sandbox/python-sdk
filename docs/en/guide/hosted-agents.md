# Hosted agents

The user guide and the runnable case are in [Agents API](agents-api.md). This page is the route reference.

Codex and Qwen Code are supported today. Adapter names that are not supported yet, including Claude Code, Cursor, Qoder, and the generic command adapter, return HTTP 404 `not_found_error` with `x-should-retry: false`.

The routes live on the sandbox server (`easy_sandbox.server`), in the opt-in `agents` capability group. They stay **off** until `EBX_SERVER_ENABLED_GROUPS` includes `agents`. With the group disabled, the same paths answer 404 and the body says the route is disabled.

```bash
export EBX_SERVER_ENABLED_GROUPS=agents
python -m easy_sandbox.server
```

The template server listens on **port 9000**. Point an OpenAI-shaped client at `base_url=http://127.0.0.1:9000/v1`. When `EBX_SERVER_TOKEN` is set, agents routes accept that token as `X-Access-Token` or `Authorization: Bearer`. Other routes still use `X-Access-Token` only.

## Best practices

* Codex and Qwen Code are supported today. A body that names an adapter that is not supported yet is HTTP 404 `not_found_error` with `x-should-retry: false`.
* Treat every response as local. Read the header `X-Easy-Sandbox-Local: 1` (errors included). `x_easy_sandbox.compute` is `local_process`, `local_state`, or `none`.
* Do not call `POST /v1/responses/input_tokens`. It is 404 `agents.not_implemented_locally` with `x-should-retry: false`. No tokenizer matches the model the CLI will call.
* Install one CLI in the image. A request that does not name an adapter uses the first in the product order (`codex`). Name `adapter`, `runtime`, or `X-EBX-Adapter`, or set `EBX_AGENTS_DEFAULT`, to use another.
* Open endpoints one id at a time. `groups.agents: true` is only the gate. Each route's default scope is `agents:use`. See [Fine-grained capabilities](fine-grained-capabilities.md).
* Leave the group off until a session needs it. Start the process with `EBX_SERVER_ENABLED_GROUPS=agents`.
* Keep model API keys out of the HTTP client. The server token, when set, is the only credential these examples send.

## Everything is local, and says so

No operation here runs at OpenAI. Each is a local process or local state, and each is labeled:

* every response carries the header `X-Easy-Sandbox-Local: 1`, errors included;
* every object carries `x_easy_sandbox: {"local": true, "compute": "local_process" | "local_state" | "none", "differences": [...]}`. `compute` is never `openai_hosted`. The openai SDK models allow extra fields, so read it as `obj.model_extra["x_easy_sandbox"]`. `metadata` is never used for the label.

| `differences` code | Meaning |
|---|---|
| `queued_not_steered` | Input sent during a turn queues a new turn. Neither CLI accepts bytes into a running process. |
| `usage_adapter_best_effort` | `usage` is what the CLI reported, and `null` when it reported nothing. |
| `redaction_best_effort` | Redaction covers registered secrets and common token shapes only. |
| `update_in_place`, `snapshot_at_session_start` | A definition updates in place. A session copies it when it is created. |
| `hosted_request_converted`, `nothing_provisioned` | An empty `openai_hosted` environment request became `self_hosted`. An environment is a directory binding. |
| `local_workspace`, `no_overwrite` | Paths are relative to the environment's workspace directory. A different existing file is refused. |
| `local_blob` | A file id is a blob in server memory. |
| `not_hosted_template`, `applies_env_and_files_only` | A template is `{name, env, inline files}` and nothing else. |
| `memory_only` | Secrets and vault records live in memory and are lost on restart. |
| `secret_in_agent_env` | Code the agent runs can read a credential from the CLI environment. |
| `snapshot_copy`, `reported_paths_only`, `delete_removes_snapshot_only` | Artifacts are copies of paths the CLI reported. Deleting one never touches the file. |
| `trace_from_journal_timing_only` | Spans come from journal timestamps and carry no text. |
| `ids_from_cli_only`, `turns_grouped_from_parent_stream`, `turns_from_rollout` | Subagent ids are the CLI's own. |
| `summary_not_encrypted_compaction` | `compact` is a local summary. |
| `response_is_cli_turn`, `model_passthrough`, `stream_replayed_after_turn`, `queued_steer` | Responses semantics. |
| `local_signer` | This server signs and delivers webhook events. |
| `not_implemented_locally` | On the 404 of a route with no local capability. |

Refusals follow one rule. A field or variant this server cannot honor is **400** `invalid_request_error` with `param` naming it and `x-should-retry: false`. It is never accepted and ignored. A route with no local capability is **404** `not_found_error` with `x-should-retry: false`, never 501 and never an empty 200.

## Adapters

| Selector in the JSON body | Canonical id | Binary on `PATH` | Install, only when you use it |
|---|---|---|---|
| `codex` | `codex` | `codex` | `npm install -g @openai/codex` |
| `qwen-code`, `qwen`, `qwencode` | `qwen-code` | `qwen` | `npm install -g @qwen-code/qwen-code` |

Selection order:

1. `X-EBX-Adapter` header, or a body field `adapter` / `runtime` (top-level or under `agent`)
2. `agent.model` or `model` when that string is one of the names above (a real model id such as `gpt-5-codex` is passed through to the CLI and does not choose an adapter)
3. Config `agents.default`: the `EBX_AGENTS_DEFAULT` environment variable, or in `EBX_AGENTS_CONFIG` a JSON string at `default` or `agents.default`
4. Otherwise the first runtime in the product order: `codex`, then `qwen-code`

`GET /v1/agents/runtimes` defaults to `order=desc`. `order=asc` is the product order above. `default: true` marks the runtime step 4 selected. It does not follow the array index. A real model id (`gpt-5`) is passed to that CLI and does not change the adapter. Name the other runtime in the request to use it.

## Sessions, events, items, turns

Errors on these routes use the OpenAI envelope `{"error": {"message", "type", "param", "code"}}`.

Create a session:

```bash
curl -s -X POST http://127.0.0.1:9000/v1/agents/sessions \
  -H 'Content-Type: application/json' \
  -d '{"agent":{"model":"codex"}}'
```

`GET /v1/agents/sessions` lists sessions (filter with `agent_id`). `GET` and `DELETE /v1/agents/sessions/{id}` read and remove one; delete also drops the artifact snapshots. `POST /v1/agents/sessions/{id}` updates `metadata` only: `agent`, `vault_ids` and `environment` are 400, and so is any other key. The session object is `agent.session` with `environment.type` `self_hosted`. `environment.workspace_directory` defaults to `/workspace`.

A session takes either an inline `agent` or an `agent_id` from [definitions](#agent-definitions), plus optional `environment: {"type": "self_hosted", "id": "env_..."}` and `vault_ids`. The inline `agent` is validated like a definition: `tools` other than `mcp`, `multi_agent.enabled`, `service_tier` outside `auto|default` and a non-`text` `text.format` are 400.

Sessions, definitions, environments, vaults, templates, responses and webhook endpoints belong to the caller. With a server policy, that is the identity id; without one, a single local owner. A foreign id answers exactly like an unknown id.

Queue a turn. The body is an input message; the response is **HTTP 202 with an empty body**. The same `Idempotency-Key` and the same body replay that 202 and do not start a second turn. The same key with a different body is **409** `idempotency.mismatch` (`x-should-retry: false`). `input.tool_result`, `computer_use_approval_request_result`, `input_image` and `input_file` are 400.

```bash
curl -s -D - -o /dev/null -X POST \
  http://127.0.0.1:9000/v1/agents/sessions/$ID/events \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: turn-1' \
  -d '{"events":[{"type":"agent.session.input.message","input":"Say hello"}]}'
```

`GET /v1/agents/sessions/{id}/events` with `Accept: text/event-stream` streams the mapped events (`text/event-stream`, `id` is the runtime sequence). Omit `after` to tail from now; the stream stays open until the session is idle again after a turn you observed. `?after=0` (or `?after=evt_<seq>`) replays the ring buffer and closes once it has delivered the idle event and nothing newer is queued.

`GET .../items`, `GET .../turns`, `GET .../turns/{turn_id}`, and `GET .../turns/{turn_id}/items` return the list envelope `{object, data, first_id, last_id, has_more}`. `limit` is 1–100 (default 20) and `order` is `asc` or `desc` (default `desc`).

`GET /v1/agents/runtimes` lists **codex** and **qwen-code** only, including whether each binary is on `PATH`. Each object has `default`. That flag is true for the runtime used when the request does not name one. `order=asc` is `codex`, then `qwen-code`. The default `order` is `desc`.

## Agent definitions

`POST /v1/agents`, `GET /v1/agents`, `GET`, `POST` (update) and `DELETE /v1/agents/{agent_id}`. The id is opaque (`agent_...`). `model` is required and is passed to the CLI as `-m` unless it names an adapter. Update is in place; a running session keeps the copy it started with, and deleting a definition never stops a session.

Only `mcp` tools over an `http` transport are real. These are 400: other tool types, `stdio` transports, `allowed_tools`, `request_metadata`, `required`, `connection_origin` other than `environment`, a URL with userinfo, a query string or a fragment, `multi_agent.enabled`, `service_tier` outside `auto|default`, `text.verbosity` other than `medium`, `reasoning.summary`, and `reasoning.effort` on Qwen Code (Codex honors it). MCP header values are write-only: a response shows `"***"`.

## Environments, files, templates

* `POST /v1/agents/environments`, `GET /v1/agents/environments`, `GET /v1/agents/environments/{environment_id}`. An environment binds one workspace directory (`type: self_hosted`) and nothing is provisioned. `env` (never returned) and inline `files` are applied when it is created. An empty `{"type": "openai_hosted"}` is converted and says so; a configured one is 400. `network`, `packages`, `setup_commands`, `plugins`, `skills`, `desktop`, `container_size` and `capability_directories` are 400. The workspace directory must be absolute without `..` and outside `/`, `/etc`, `/proc` and the other system trees. `env` refuses `PATH`, `HOME`, the LLM endpoint and keys, proxy variables, loader and interpreter hooks, and every `CODEX_*`, `QWEN_*`, `GIT_*` and `EBX_*` name.
* `POST` and `GET /v1/agents/environments/{environment_id}/files`. A file is written below the workspace directory (`/workspace/a/b` becomes `a/b`), through directory file descriptors with `O_NOFOLLOW`: a symlink anywhere on the path is refused. An existing file with different bytes is 400 `agents.file_exists` (never 409, which the SDK retries); identical bytes succeed. Writes under `.git/`, `.codex/`, `.claude/`, `.cursor/`, `.qwen/`, `.qoder/`, `.ssh/` and of `.mcp.json`, `AGENTS.md`, `QWEN.md` and shell rc files are 400 `agents.path_refused`, because they change what the next turn runs. The cap is `EBX_AGENTS_MAX_FILE_BYTES` (default 10 MiB). The listing returns regular files only, skips those directories, and pages with the opaque `page` token (`next`).
* `POST /v1/files` keeps `purpose=user_data` bytes in memory so `{"type": "file_id"}` works. The dispatcher parses JSON bodies only, so send `{"purpose": "user_data", "filename": "...", "data": "<base64>"}`; multipart uploads are not parsed. A `file_id` this server did not mint is 400.
* Templates (`/v1/agents/environments/templates`, create, retrieve, update, list, delete) hold `{name, env, files}` and apply to an environment through `environment.environment_template_id`. The refused fields above are 400 on create and update, so a template can never carry them. Env values and file bodies are never returned (`size_bytes` only).

## Vaults and credentials

`/v1/vaults` and `/v1/vaults/{vault_id}/credentials` follow the official shapes. Vaults live in memory (`memory_only`), count against `EBX_AGENTS_MAX_VAULTS` (default 100 per owner) and show only `id`, `name`, `metadata`, `created_at`.

A credential is `static_bearer` or `mcp_oauth` with an access token. No response, error message or event contains a value, prefix, length or hash of the secret. These are 400: `environment_variable` (no egress proxy exists, so the only delivery would hand the secret to code the agent runs), `mcp_oauth.refresh` (no refresh broker), `networking.unrestricted`, `limited` hosts other than the credential's own host, an `mcp_server_url` that is not `https` or points at a private host, and a token containing a newline.

Attach vaults with `vault_ids` on a session (or an environment). At every turn a credential is injected into the session's MCP tool whose URL has the same scheme, host and port, as an `Authorization: Bearer` header carried in the child environment (Codex `env_http_headers`, Qwen `${VAR}` placeholders in `.qwen/settings.json`), never in `argv`. A tool without a matching credential runs unauthenticated; two matches need an explicit `credential_id`. Rotating a credential applies from the next turn. A credential or vault deleted since the session was created, or an expired `expires_at`, makes the next event 400 (`agents.credential_unavailable`, `agents.credential_expired`) instead of silently running unauthenticated. Every credential object carries `secret_in_agent_env`.

## Artifacts, traces, subagents

* `GET .../sessions/{id}/artifacts`, `GET`, `DELETE .../artifacts/{artifact_id}`, `GET .../artifacts/{artifact_id}/content`. When a turn completes, the server copies the files the CLI **reported** (Codex `file_change`, Qwen `write_file` / `replace` / `edit` inputs) into a private directory with `O_NOFOLLOW`, regular files only, within the workspace, at most `EBX_AGENTS_MAX_ARTIFACT_BYTES` (10 MiB) each and 100 per turn. The workdir is never scanned, `.git/` is skipped, and `path` is `/workspace/<relative path>`. Content is the snapshot, served as an attachment with `X-Content-Type-Options: nosniff`. Delete removes the snapshot only (`deleted_scope: snapshot`). `EBX_AGENTS_STATE_DIR` places the snapshots under `<dir>/artifacts`; otherwise a temporary 0700 directory is used.
* `GET .../sessions/{id}/traces` is empty by default. With `EBX_AGENTS_TRACES=1` it returns one OTLP trace per finished turn with one span built from the journal's start and end times; attributes are the turn status and item count, never text, commands or arguments.
* `GET .../sessions/{id}/subagents` and the five detail routes serve only ids the CLI emitted. Codex: `receiver_thread_ids` of `collab_tool_call` items, or ids named in the session's own rollout; a child's items and turns come from that child's rollout under `CODEX_HOME` (never a scan for unrelated sessions). Qwen Code: the `parent_tool_use_id` of the subagent's messages; turns are groups of that stream split at assistant messages. Any other id is 404 `resource_not_found`, byte-identical to an unknown id. `multi_agent.enabled=true` stays 400. The detail is read while the session runs; Qwen entries are kept in memory and lost on restart.

## Responses

`POST /v1/responses` runs one turn of a local CLI and returns a `response` object. `model` is the id of a stored definition, or it passes through as the CLI model (`gpt-5-codex`); a runtime name such as `qwen` means "the CLI's default model" and the object says `model_resolved: false`. Without a `previous_response_id` a new CLI session is created in `EBX_AGENTS_RESPONSES_WORKSPACE` (default `/workspace`). With one, the turn resumes that conversation, but only from the latest response of it (the CLI session is linear): otherwise 400 `agents.previous_response_not_latest`.

* Accepted: `model`, `input` (a string or `user`/`system`/`developer` messages with `input_text` parts), `instructions`, `metadata`, `store`, `background`, `stream`, `previous_response_id`, MCP `tools` (`server_label`, `server_url`, write-only `headers` and `authorization`), `reasoning.effort` (Codex).
* 400: `tools` other than `mcp`, `conversation`, `prompt`, `text.format` other than `text`, any `include`, `service_tier` outside `auto|default`, `tool_choice` other than `auto`, `input_image`, `input_file`, assistant history, items that are not messages, `background` with `store: false`, and unknown parameters.
* Sampling parameters (`temperature`, `top_p`, `max_output_tokens`, ...) are ignored and listed in the response header `X-Easy-Sandbox-Ignored-Params`.
* Output items are what the CLI emitted: `message`, `reasoning`, `command_execution`, `mcp_call` for a real MCP call, and `tool_call` (with `tool_name`) for every other native tool such as `web_search` and `file_change`. Each non-message item carries `x_easy_sandbox`. Nothing is shaped as `web_search_call`, `function_call`, `code_interpreter_call` or `local_shell_call`. `usage` is `null` when the CLI reported none. `Response.tools` lists only the MCP tools passed to the CLI.
* `stream: true` replays the stored turn with the official event names (`response.created`, `response.output_text.delta`, `response.completed`, ...) once the turn finishes (`stream_replayed_after_turn`). `GET /v1/responses/{id}?stream=true&starting_after=N` replays it again.
* `GET`, `DELETE /v1/responses/{id}`; `GET .../input_items` returns the input as accepted. `POST .../cancel` cancels a running turn and returns the terminal object; a finished response is 400 `agents.not_cancellable`, not 409. An `Idempotency-Key` replays the first response; a different body is 409. `store: false` responses disappear when the turn ends.
* `POST /v1/responses/compact` needs `previous_response_id`. Qwen Code runs `/compress` and the answer is a local summary (`summary_not_encrypted_compaction`, with `original_token_count` and `new_token_count` when the CLI printed them). Codex is 400 `agents.compact_unsupported`.
* `GET /v1/responses` without a WebSocket upgrade is 400 `agents.websocket_upgrade_required`. The `responses.connect` client-event engine (`response.create`; `response.steer` queues a successor turn behind the running one, `queued_steer`) is implemented and tested in `agents.api_responses.ResponsesSocket`, but this HTTP transport cannot hand the socket to a route handler, so the upgrade itself needs a transport change.

## Models and webhooks

`GET /v1/models` lists the caller's definitions and the two adapters with `owned_by: easy-sandbox-local` and `x_easy_sandbox.kind` / `installed`. `GET /v1/models/{id}` is 404 `model_not_found` for anything not listed and has no side effect.

Webhook endpoints (`/v1/webhook_endpoints`, create, retrieve, update, list, delete, `rotate_secret`, `test`; `GET /v1/webhook_event_types`) are local records. The `whsec_` signing secret is returned once on create and rotate. The server sends `agent.session.created`, `in_progress`, `idle` and `failed` for the owner's sessions, signed the Standard Webhooks way (`webhook-id`, `webhook-timestamp`, `webhook-signature`), so `client.webhooks.unwrap` verifies them. `agent.session.action_required` never occurs and is not accepted. The URL must be `https`, with no userinfo or query, and not a private or loopback host; redirects are not followed. For local development set `EBX_AGENTS_WEBHOOK_ALLOW_HTTP=1` and `EBX_AGENTS_ALLOW_PRIVATE_URLS=1`. `keep_old_secret_active_for_24_hours` is 400.

## No local capability: 404

| Operation | Why |
|---|---|
| `POST /v1/responses/input_tokens` | No tokenizer matches the model the CLI will call, and the real count is only known after a generation. |
| `DELETE /v1/models/{id}` | There are no fine-tuned models. Delete a definition with `DELETE /v1/agents/{agent_id}`. |
| Executor registration and the executor channel (`environment.remote_url`) | They are clients of OpenAI's hosted harness. `POST /v1/agents/environments/{id}/register` and `GET .../{id}/connect` answer the same labeled 404 (the real registration path is unpublished). |

Each answers `404`, `type: not_found_error`, `code: agents.not_implemented_locally`, `x-should-retry: false`, `X-Easy-Sandbox-Local: 1`.

Clients that only demonstrate the calls, against a server you already started: [hosted_codex.py](../../../examples/agents/hosted_codex.py) and [hosted_qwen.py](../../../examples/agents/hosted_qwen.py). [local_files_and_session.py](../../../examples/agents/local_files_and_session.py) uploads one file and opens one session against a local server. It places a local program named `codex` on `PATH` and does not read a model API key. See [examples/agents/README.md](../../../examples/agents/README.md).
