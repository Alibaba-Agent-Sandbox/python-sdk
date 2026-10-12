# ops-can-do: feasibility of every inventoried operation

Reviewer role: adversarial feasibility. The question is what this server can build for the Codex CLI and the Qwen Code CLI. `ops-cannot.md` is the honesty review; this file attacks its route refusals and the older cuts in `05-agents-api.md` section 4. It does not edit source, `ops-inventory.md`, or `ops-cannot.md`.

Verdicts:

* **BUILD** — local behaviour matches the official operation with no difference a caller must be told about.
* **BUILD-LOCAL-SEMANTICS** — the route ships, with the label contract from `ops-cannot.md` (`x_easy_sandbox`, header `X-Easy-Sandbox-Local: 1`). This is the verdict for every row `ops-cannot.md` marks IMPLEMENT-AND-LABEL.
* **CANNOT** — a concrete capability is missing. The route is the 404 in `ops-cannot.md` (`not_found_error`, `x-should-retry: false`), not 501 and not an empty 200.

Where `ops-cannot.md` says REFUSE, the row below is CANNOT, or the attack section says why that refusal is wrong and the verdict is BUILD-LOCAL-SEMANTICS.

## 0. First integration

Ship adapters `codex` and `qwen-code` only. `claude_code`, `cursor`, and `command` stay unmounted until a later integration. No operation below is dropped because those three are absent. Artifact snapshots, subagent detail, MCP credential injection, and compaction are all served by Codex or Qwen or both. A session whose adapter cannot perform one labeled variant gets `400` with `param` set, not a missing route.

Evidence for the attacks: `adapters/codex.py` (parses `file_change`, `mcp_tool_call`, `command_execution`, `web_search`; no collab branch), `adapters/qwen_code.py` (MCP headers via `${VAR}`, resume, stream-json), `adapters/stream_json.py` (drops every event with `parent_tool_use_id`; files non-shell tools as kind `other`), `routes_files.py` (`_write_checked`, `_handle_files_list`, no symlink follow, `_protect_tree`). CLI facts: Codex exec JSONL `collab_tool_call` carries `receiver_thread_ids` (`codex-rs/exec/src/exec_events.rs`); the child thread id is also in the session rollout when exec JSONL omits `spawn_agent` (Codex issue 34919). Qwen stream-json sets `parent_tool_use_id` to the `agent` tool-use id and emits that subagent's own messages and tool calls (`StreamJsonOutputAdapter`, `subagents.test.ts`). Qwen non-interactive `/compress` returns a summary and original/new token counts. Neither CLI exposes a preflight tokenizer, and neither accepts bytes into a live process.

## 1. Attacks on the old refusals

### 1.1 Environment files (05: reserved, 404 until implemented)

The reservation is a missing route, not a missing capability. `routes_files.py` already writes and lists under an admitted directory, refuses to follow symlinks out of the root, and protects server trees. A-09 and A-10 are that machinery scoped to the environment's workspace directory, with the no-overwrite rule from `ops-cannot.md` section 2.3. Codex and Qwen both run with that directory as cwd; they do not need to perform the write.

`ops-cannot.md` then variant-refuses `type: file_id` because "there is no Files API." That ban is circular. O-03 is a local blob of the same bytes the inline form already accepts: `POST /v1/files` with `purpose=user_data` stores them, returns an id this server minted, and A-09 reads that blob. An OpenAI file id is 404. After O-03, `file_id` is not a permanent refusal.

**Verdict.** A-09, A-10, O-03: BUILD-LOCAL-SEMANTICS (`local_workspace`, `no_overwrite`, `local_blob`).

### 1.2 Environment templates (05: not planned)

05 equates this resource with the Easy Sandbox image template. It is a different record. Both adapters already apply an env map and files written before spawn (`InvocationFile` on Qwen for `.qwen/settings.json`; Codex `-c` plus child env). A stored `{name, env, inline files}` applied at environment or session create is that path. Confidential values stay write-only (`size_bytes` only).

`network`, `packages`, `setup_commands`, `plugins`, `skills`, `desktop`, and `capability_directories` stay `400`. Nothing in either CLI enforces a hosted network policy, installs packages as a sandbox image, or runs setup commands as a non-exec route. `ops-cannot.md` also variant-refuses `environment_template_id` even after templates exist, "because a template might carry refused fields." It cannot: those fields are rejected at template create and update, so they are not stored. `environment_template_id` then only reapplies env and inline files, which is the reduced template. That variant refusal does not stand.

**Verdict.** A-11..A-15: BUILD-LOCAL-SEMANTICS (`not_hosted_template`, `applies_env_and_files_only`).

### 1.3 Vaults (05: not planned; "local equivalent is the LLM key")

05 misreads the resource. Vaults hold MCP and bearer credentials, not the provider key. Both first-integration adapters already inject those into the child without putting them on argv: Codex `mcp_servers.<name>.env_http_headers` maps a header name to an env var (`codex.py`); Qwen writes `${VAR}` header placeholders into `.qwen/settings.json` (`qwen_code.py`). A memory-only vault that injects `static_bearer` or an access-token `mcp_oauth` into a matching MCP server is that carrier. Ownership, restart-loses-secrets, and write-only responses are as in `ops-cannot.md` sections 2.11 and 2.12.

These variants stay `400`, each for a missing capability, and they are not route refusals:

* `environment_variable` — no egress proxy. The official contract is that sandbox code cannot read the secret. The only local delivery puts it in the CLI environment, which both CLIs' shells can read.
* `mcp_oauth.refresh` — no refresh broker. Calling a caller-chosen `token_endpoint` sends the refresh token off the machine.
* `networking.unrestricted`, and `limited` hosts other than the credential URL's own host — neither CLI's traffic passes through a host filter. The one check that exists is host equality at injection.

**Verdict.** A-38..A-47: BUILD-LOCAL-SEMANTICS (`memory_only`, `secret_in_agent_env`).

### 1.4 Subagent detail routes (`ops-cannot.md` REFUSE 1–5; 05: refused)

The refusal says no adapter emits a native subagent id, so the five detail routes would invent one (R5). The adapters do not parse the id. The CLIs do emit it.

* Codex exec JSONL item type `collab_tool_call` includes `sender_thread_id`, `receiver_thread_ids`, and per-thread `agents_states` for `spawn_agent`, `send_input`, `wait`, and `close_agent`. `receiver_thread_ids` are thread ids the CLI minted. When exec JSONL drops `spawn_agent` and leaves `receiver_thread_ids` empty (Codex issue 34919), the same child id is in that session's rollout and in `thread_spawn_edges`. Read only threads this session's rollout names. Do not scan `CODEX_HOME` for unrelated sessions. Child items and turns are that child rollout's own items and turns.
* Qwen, with `--output-format stream-json`, emits the subagent's user prompt, assistant messages, and tool calls with `parent_tool_use_id` set to the `agent` tool-use id. `stream_json.py` returns `[]` for those events and skips their text. That is a parser gap. The id is the tool-use id the CLI already uses to tie the child to the parent. Items are those events. Turns are groups of that child stream separated by assistant-message boundaries (`turns_grouped_from_parent_stream`), because Qwen does not emit a separate turn id.

R5 still holds: an id neither the JSONL nor the scoped rollout contains is `404 resource_not_found`, the same bytes as an unknown id. `multi_agent.enabled=true` stays `400`. Neither adapter has a switch that turns spawning on, so accepting the flag would be accept-and-ignore. The routes still serve a subagent the CLI spawned with the flag omitted. A-32 is not an empty list by construction for these two CLIs; `adapter_emits_no_subagent_events` is the wrong difference code. Use `ids_from_cli_only`.

**The REFUSE is wrong.** A-33, A-34, A-35, A-36, A-37: BUILD-LOCAL-SEMANTICS.

### 1.5 `/v1/responses` (05: out of 0.3.0; `ops-cannot.md` REFUSE 6–8)

05's cut is a schedule cut. Both CLIs already produce the body of a response: a final assistant message, tool events, and usage (`turn.completed.usage` on Codex, the `result` event on Qwen), and both resume (`codex exec resume`, `qwen --resume`). R-01..R-05 are the local CLI turn from `ops-cannot.md` section 2.13. Request `tools` other than `mcp` stay `400`. Output still reports a tool the CLI actually emitted (`command_execution`, `file_change`, `web_search`, `mcp_tool_call`, Qwen `write_file` / `agent`) as a local item, never as an OpenAI hosted tool the caller did not see run.

**R-07 `POST /responses/compact` — the REFUSE is wrong as a route refusal.** Qwen runs `/compress` non-interactively and returns a summary plus `originalTokenCount` / `newTokenCount`, then continues the session on the summary. That is not OpenAI's encrypted compaction item. The response is a local summary (`summary_not_encrypted_compaction`). Codex `exec` `/compact` is not a reliable primitive (the slash text is often just a prompt), and `ContextCompactionItem` in the protocol is only an id. The Codex adapter answers `400 agents.compact_unsupported` until a real compaction item is emitted. The route stays because Qwen serves it.

**R-08 WebSocket `responses.connect` — the REFUSE is wrong as a route refusal.** The stated gap is "no op id and no 15.1/15.8 handshake." That is server work: the same exec-effect `AgentScope` as `responses.create`, bearer auth, no token in the URL. The server already terminates WebSockets for PTY. `response.create` on the socket is the same CLI spawn as R-01. What neither CLI has is a way to push bytes into a running `codex exec` or `qwen` process, so `response.steer` is the queue from A-21 (`queued_not_steered`), not a mid-generation steer. Label it. Do not answer the socket with an unauthenticated exec.

**R-06 `POST /responses/input_tokens` — REFUSE stands.** CANNOT. Missing capability: a tokenizer that is the one the CLI's model will call, usable without a generation. Codex reports `input_tokens` only on `turn.completed`, after the model ran. Qwen's `estimateContentTokens` is a character estimate used when the provider omits usage; it is a different number. A labeled estimate is still the billing figure clients store.

**`DELETE /v1/models/{id}` — REFUSE stands.** Not one of the 69. CANNOT. Missing capability: a fine-tuned model object. Agent definitions already delete through A-05; this route must not be a second delete.

## 2. Verdict for every inventoried operation

`BLS` is BUILD-LOCAL-SEMANTICS. Difference codes in parentheses are the ones that matter for that row; the shared label (`local: true`, `compute` never `openai_hosted`) applies to every BLS row. Variant `400`s that stay are in section 3, not extra rows.

| id | verdict | Why this server can or cannot |
|---|---|---|
| A-01 | BLS | Stored `AgentSpec`. Only MCP tools are real. Secrets write-only. |
| A-02 | BLS | Opaque id, principal-filtered. Not the definition name (D1). |
| A-03 | BLS | In-place update. Running sessions keep the snapshot they started with. |
| A-04 | BLS | Principal-filtered list. |
| A-05 | BLS | Deletes the spec. Does not kill sessions that hold a snapshot. |
| A-06 | BLS | Directory binding, `type: self_hosted`. Empty `openai_hosted` converts and says so. Nothing is provisioned. |
| A-07 | BLS | Read that binding. |
| A-08 | BLS | List bindings the principal owns. |
| A-09 | BLS | Inline bytes, or a blob from O-03, through the files admission in `routes_files.py`. No overwrite. |
| A-10 | BLS | List under the environment workspace only. |
| A-11 | BLS | Store `{name, env, inline files}` only. |
| A-12 | BLS | Read it. Env values and file bodies are not returned. |
| A-13 | BLS | Update the same reduced record. |
| A-14 | BLS | List those records. |
| A-15 | BLS | Delete the record and its confidential inputs. |
| A-16 | BLS | Exec-effect. Codex or Qwen process. `AgentScope` required. `workspace_directory` admitted. |
| A-17 | BLS | Owner-filtered read. `usage` null when the adapter reported none. |
| A-18 | BLS | `metadata` only. `agent`, `vault_ids`, `environment` are 400. |
| A-19 | BLS | Owner-filtered list. |
| A-20 | BLS | Returns after the process group is gone. Deletes the journal. |
| A-21 | BLS | `input.message` queues a turn. `input.cancel` signals the process group. Not mid-turn steering (`queued_not_steered`). |
| A-22 | BLS | SSE tail. Resume `?after=` is an extension. Redaction is best effort. |
| A-23 | BLS | User items echoed. Native tools are not `mcp_call`. `failed` stays `failed`. |
| A-24 | BLS | Turns the runtime recorded. |
| A-25 | BLS | One of those turns. |
| A-26 | BLS | Items of that turn. |
| A-27 | BLS | Snapshot copies of paths the adapter reported. Codex `file_change`. Qwen `write_file` / `replace` tool inputs (parser currently files them as `other`; the paths are in the stream). |
| A-28 | BLS | Metadata of one snapshot. Path is workspace-relative. |
| A-29 | BLS | Deletes the snapshot only (`deleted_scope: snapshot`). |
| A-30 | BLS | Bytes of the snapshot, not a live workdir read. |
| A-31 | BLS | Empty by default. Optional spans from journal timestamps only (`trace_from_journal_timing_only`). |
| A-32 | BLS | Subagents whose ids the CLI emitted (section 1.4). Not an invented empty list. |
| A-33 | BLS | Refusal overturned (section 1.4). One emitted id. |
| A-34 | BLS | Refusal overturned. That child's items, from the child rollout (Codex) or the tagged stream (Qwen). |
| A-35 | BLS | Refusal overturned. Codex rollout turns, or Qwen groups labeled `turns_grouped_from_parent_stream`. |
| A-36 | BLS | Refusal overturned. One of those turns. |
| A-37 | BLS | Refusal overturned. Items of that turn. |
| A-38 | BLS | Memory-only vault. Owner-bound. |
| A-39 | BLS | `id`, `name`, `metadata`, `created_at` only. |
| A-40 | BLS | Name and metadata. No secret in the body. |
| A-41 | BLS | Owner-filtered list. |
| A-42 | BLS | Delete. A later turn that needed it fails explicitly. |
| A-43 | BLS | `static_bearer` and access-token `mcp_oauth` only, into a matching MCP server via the env carrier. |
| A-44 | BLS | Metadata only. No secret-derived field. |
| A-45 | BLS | Rotate by replacing the memory value. Response still has no secret. |
| A-46 | BLS | List metadata. |
| A-47 | BLS | Delete one credential. |
| R-01 | BLS | One CLI turn. `model` selects a definition or passes through as the CLI `-m` / `--model`. Exec-effect gate. |
| R-02 | BLS | Ids this server minted, owner-filtered. `stream` replays the stored turn. |
| R-03 | BLS | Deletes the stored response and its turn record. |
| R-04 | BLS | Cancels the running turn, then returns the terminal state. |
| R-05 | BLS | Input items as accepted at create. |
| R-06 | CANNOT | No tokenizer for the model the CLI will call. See section 1.5. |
| R-07 | BLS | Refusal overturned. Qwen `/compress` summary. Codex 400 until it emits a compaction item. |
| R-08 | BLS | Refusal overturned. WebSocket transport over the same CLI turn. `response.steer` is queued. |
| O-01 | BLS | Definitions and mounted adapters. `owned_by: easy-sandbox-local`. No side effect on resolve. |
| O-02 | BLS | One of those ids. Anything else is 404 `model_not_found`. |
| O-03 | BLS | Local `user_data` blob for A-09. Not OpenAI Files. See section 1.1. |
| O-04 | CANNOT | Unpublished registration body to `api.openai.com`, plus a dashboard environment key. Codex as executor is a client of that harness, not a spec we can host. |
| O-05 | CANNOT | Unpublished executor frame format. The peer is the hosted socket `wss://codex-cloud-environments.chatgpt.com`. |
| O-06 | BLS | This server POSTs HMAC-signed lifecycle events to a URL from O-07. Our signer, our session payload. |
| O-07 | BLS | Store a local endpoint. Signing secret returned once. |
| O-08 | BLS | Read it. Secret not returned again. |
| O-09 | BLS | Update URL, name, or event types. |
| O-10 | BLS | List endpoints the principal owns. |
| O-11 | BLS | Delete the endpoint. |
| O-12 | BLS | Rotate the local signing secret. |
| O-13 | BLS | POST one test event through O-06. |
| O-14 | BLS | The event types O-06 actually sends. |

## 3. Variant refusals that remain on BLS routes

`400 invalid_request_error`, `param` set, `x-should-retry: false`. These are not CANNOT rows.

* Environments and templates: `network`, `packages`, `setup_commands`, `plugins`, `skills`, `desktop`, `container_size`, `capability_directories`.
* Sessions: `environment.type=openai_hosted`; `update` of `agent`, `vault_ids`, or `environment`.
* Credentials: `environment_variable`, `mcp_oauth.refresh`, `networking.unrestricted`, `limited` hosts other than the credential's own URL host.
* Definitions, sessions, responses: request `tools` other than `mcp`; `multi_agent.enabled=true`; `service_tier` outside `auto|default`.
* Events: `input.tool_result`, `computer_use_approval_request_result`, `input_image`, `input_file`.
* Responses: `conversation`, `prompt`, `text.format` other than `text`, `include` values the runtime cannot fill, `previous_response_id` that is not the session's latest. Codex-only: `compact` until a compaction item exists.
* Files: a `file_id` this server did not mint.

Removed relative to `ops-cannot.md`: the permanent ban on `type: file_id`, and the ban on `environment_template_id` once the template is the reduced record.

## 4. `ops-cannot.md` REFUSE rows, answered

| ops-cannot REFUSE | Verdict | Reason |
|---|---|---|
| 1–5 subagent retrieve, items, turns, turn, turn items | BLS | Refusal is wrong. Codex `receiver_thread_ids` / scoped rollout, and Qwen `parent_tool_use_id`, are native ids. Section 1.4. |
| 6 `POST /responses/input_tokens` | CANNOT | No matching tokenizer without a generation. |
| 7 `POST /responses/compact` | BLS | Refusal is wrong as a route refusal. Qwen `/compress` is a local summary, labeled. |
| 8 WebSocket `/responses` | BLS | Refusal is wrong as a route refusal. The handshake is server work. Steer is queued. |
| 9 `DELETE /v1/models/{id}` (not in the 69) | CANNOT | No fine-tuned model object. |

## 5. Counts

| Verdict | Operations | Count |
|---|---|---|
| BUILD | — | **0** |
| BUILD-LOCAL-SEMANTICS | A-01..A-47, R-01..R-05, R-07, R-08, O-01..O-03, O-06..O-14 | **66** |
| CANNOT | R-06, O-04, O-05 | **3** |
| **Inventory total** | | **69** |

Of the 9 route REFUSEs in `ops-cannot.md`, 7 are overturned to BUILD-LOCAL-SEMANTICS (5 subagent detail routes, compact, WebSocket) and 2 stay CANNOT (`input_tokens`, and `DELETE /v1/models/{id}` which is outside the 69). The 05 section 4 cuts of environment files (2), environment templates (5), vaults and credentials (10), and Responses create/retrieve/delete/cancel/input_items (5) are all inside the 66.

Adapters in the first integration: Codex and Qwen Code only. The other three adapters are later and remove nothing from the 66.
