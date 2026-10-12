# Decision: Hosted Agents slice — Codex and Qwen Code

Status: proposed

## Problem

The server already has an agent runtime, Codex and Qwen Code adapters, and OpenAI-shaped session objects, but nothing registered HTTP routes. Callers could not create a session or stream a turn. A first slice exposed that runtime without vaults, the Responses API, or the other adapters. The maintainer then asked for every operation that `docs/en/design/server-sdk-v2/reviews/ops-can-do.md` marks BUILD-LOCAL-SEMANTICS (66 operations) for those two adapters, with the label contract of `ops-cannot.md`, and for the three CANNOT operations to stay 404.

## Decision

Register `routes_agents.py` on `CapabilityGroup.AGENTS` (still off unless `EBX_SERVER_ENABLED_GROUPS` includes `agents`). `routes_agents.py` holds registration and the session/event/item/turn handlers; the other handlers live in `agents/api_*.py` and are registered only in `routes_agents.py`.

The body may select `codex` or `qwen-code` (aliases `qwen`, `qwencode`, `qwen_code`). Otherwise the server uses config `agents.default` (`EBX_AGENTS_DEFAULT`, or `default` / `agents.default` in `EBX_AGENTS_CONFIG`). If neither is set, the response is 400 `agents.adapter_required`. Any other adapter name is 404 `not_found_error` with `x-should-retry: false`.

The maintainer confirmed on 2026-10-12: do not integrate the Claude Code, Cursor, or Qoder adapters in this round. Those names are other CLIs behind the same Agents API (`claude`, `cursor-agent`, `qodercli`). They are not a separate product. The adapter modules may stay in the tree, but no new routes, docs, or examples should mount them until the maintainer says to.

### What the second round added

Label contract (`agents/api_common.py`): every response carries `X-Easy-Sandbox-Local: 1` and every object `x_easy_sandbox: {local, compute, differences}` with `compute` in `local_process | local_state | none` and stable codes from one table (`DIFFERENCES`). The already shipped session, turn, item and runtime objects now carry it too. A foreign id and an unknown id answer identically; ownership is the policy identity id, or one local owner without a policy.

| Operations | Where | Notes |
|---|---|---|
| A-01..A-05 definitions | `api_definitions.py` | Opaque `agent_` ids. Only `mcp` over `http`. 400 for other tool types, `stdio`, `multi_agent.enabled`, `service_tier` outside `auto\|default`, `text.verbosity`, `reasoning.summary`, `reasoning.effort` on Qwen. Session create takes `agent_id` and validates an inline `agent` the same way. Each session gets its own spec name, so sessions no longer overwrite each other's spec. |
| A-06..A-10, O-03 environments, files, blobs | `api_environments.py`, `workspace_files.py` | Directory binding, files through `O_NOFOLLOW` directory fds, no overwrite (400 `agents.file_exists`), agent-config locations refused, size cap, listing of regular files with an opaque `page` token. `POST /v1/files` keeps `user_data` blobs in memory. |
| A-11..A-15 templates | `api_environments.py` | `{name, env, files}` only. Hosted-only fields are 400 on create and update, so `environment_template_id` can be applied. |
| A-18 session update | `api_sessions.py` | `metadata` only; `agent`, `vault_ids`, `environment` and unknown keys are 400. |
| A-27..A-31 artifacts, traces | `artifacts.py`, `api_sessions.py` | A turn hook in `AgentRuntime` copies the paths the CLI reported (Codex `file_change`, Qwen `write_file`/`replace`/`edit`) at completion. Content is served as an attachment. Traces are empty unless `EBX_AGENTS_TRACES=1`, then timing-only. |
| A-32..A-37 subagents | `subagents.py`, `api_sessions.py`, parsers | Codex `collab_tool_call.receiver_thread_ids` and the session's own rollout; child items and turns from the child rollout under `CODEX_HOME`. Qwen `parent_tool_use_id` events (previously dropped, and child tool calls leaked into the parent items) are collected per subagent. Unknown ids are 404. |
| A-38..A-47 vaults, credentials | `api_vaults.py` | Memory-only, owner-bound, write-only. Injected per turn as an `Authorization` header through the existing env carrier. A deleted or expired credential fails the next event with 400. |
| R-01..R-05, R-07 responses | `api_responses.py` | A labeled one-shot CLI turn. Output items are what the CLI emitted (native tools are `tool_call`, never hosted tool shapes). `previous_response_id` only from the latest. Compact is Qwen `/compress`; Codex is 400. |
| R-08 `responses.connect` | `api_responses.py` | The client-event engine (`ResponsesSocket`: `response.create`, `response.steer` queued) is implemented and tested. The upgrade cannot be done in a route handler: `GET /v1/responses` answers 400 `agents.websocket_upgrade_required`. Needs a transport change in `app.py`. |
| O-01, O-02 models | `api_other.py` | Definitions and the two adapters, `owned_by: easy-sandbox-local`, 404 `model_not_found` otherwise, no side effect. |
| O-06..O-14 webhooks | `api_other.py`, `webhooks.py` | Local endpoints, `whsec_` secret returned once, Standard Webhooks signing, session created/in_progress/idle/failed delivery. https only, no private hosts, no redirects. |

CANNOT, labeled 404 `not_found_error` (`agents.not_implemented_locally`, `x-should-retry: false`): R-06 `POST /v1/responses/input_tokens`, `DELETE /v1/models/{id}`, and O-04/O-05 (registered on guessed paths `POST /v1/agents/environments/{id}/register` and `GET .../{id}/connect`, because the real paths are unpublished).

Variant refusals stay 400 with `param` (ops-can-do section 3): hosted-only environment and template fields, `environment.type=openai_hosted` with content, credential `environment_variable`, `mcp_oauth.refresh`, `networking.unrestricted` and foreign `limited` hosts, tools other than `mcp`, `multi_agent.enabled`, `service_tier`, `input.tool_result`, images and files, Responses `conversation`, `prompt`, `text.format`, `include`, non-latest `previous_response_id`, and a `file_id` this server did not mint.

### Known gaps, outside this slice's files

* Exec-effect gating with an `AgentScope` (`policy.py`, `guard.py`, `router.py`, `app.py` belong to another worker). The handlers read the identity from `request.context["policy"]` and call the policy's `resolve_path` for environment files when it is present, but nothing here enforces `AgentScope` or `UrlScope`.
* `POST /v1/files` accepts JSON with base64 `data`. The dispatcher parses JSON bodies only, so the SDK's multipart `files.create` cannot reach it until `app.py` passes raw bodies.
* The `responses.connect` WebSocket upgrade (above).
* State is in memory: definitions, environments, vaults, responses, webhooks, Qwen subagent entries and artifact snapshots (a private temp directory unless `EBX_AGENTS_STATE_DIR`) are lost on restart. Sessions persist as before.

## API Design

- Sessions, events, items, turns and runtimes as in the first round; `POST /v1/agents/sessions/{id}` is now the metadata update.
- `/v1/agents`, `/v1/agents/environments[...]`, `/v1/vaults[...]`, `/v1/responses[...]`, `/v1/models[...]`, `/v1/files`, `/v1/webhook_endpoints[...]` as listed above. Route order matters in `RouteTable`: literal paths (`sessions`, `runtimes`, `environments`, `templates`) are registered before `{agent_id}` and `{environment_id}`.
- Errors: `{"error": {message, type, param, code}}`; 400 for refused variants, 404 for unknown or foreign ids and CANNOT routes, never 501.
- Environment variables added: `EBX_AGENTS_RESPONSES_WORKSPACE`, `EBX_AGENTS_MAX_FILE_BYTES`, `EBX_AGENTS_MAX_ARTIFACT_BYTES`, `EBX_AGENTS_MAX_VAULTS`, `EBX_AGENTS_TRACES`, `EBX_AGENTS_ALLOW_PRIVATE_URLS`, `EBX_AGENTS_WEBHOOK_ALLOW_HTTP`.

## Alternatives considered

- **Serve every built-in adapter now** — rejected. The maintainer asked for Codex and Qwen Code first. Other names stay 404 so clients do not treat them as implemented.
- **JSON poll instead of SSE** — rejected. The router already has `streaming=True` and `SSEResponse`.
- **Refuse subagent detail, compact and the socket as routes** — rejected by `ops-can-do.md`: the CLIs do emit the ids, Qwen has `/compress`, and the socket is server work.
- **Vault secrets on disk** — rejected: the CLI runs as the same uid, so anything on disk is readable by agent-executed code.
- **A new nodejs-sdk tree** — rejected. This slice stays in `python-sdk`.

## Dependencies

Reuses `AgentRuntime`, `adapters/codex.py`, `adapters/qwen_code.py`, and `wire_sessions.py`. `AgentRuntime` gained `turn_hooks` and per-session `subagents`; the Codex and stream-json parsers gained a `subagent` event kind. No change to the files or commands route tables, and no edit to `server/core/**`, `policy.py`, `guard.py`, `router.py`, `app.py` or `cli/`.

## Test Strategy

`server-sdk/tests/test_server/test_routes_agents.py` (first round) and `test_routes_agents_local.py` put fake `codex` and `qwen` scripts on `PATH`. The local suite drives handlers through the default route table (so registration order is real) plus a live-server sweep. It covers: the label and header on every group; the four CANNOT routes; other adapters staying 404; refused variants with `param`; secret canaries absent from every response, SSE frame, error, `argv`, and present only in the child environment; symlink, `.git`, `..` and size refusals; artifact immutability and snapshot-only delete; unreported and symlinked paths never published; subagent ids from fake JSONL and fake rollouts, an unrelated rollout never listed, hostile ids never reaching the filesystem; ownership (a foreign id equals an unknown id); Responses create, retrieve, delete, cancel, stream, idempotency, `store: false`, native tools never shaped as hosted tools; compact on both adapters; signed webhook delivery verified with the Standard Webhooks algorithm.

## Acceptance criteria

- The routes above are registered only in the `agents` group and answer 404 while that group is disabled.
- Codex and Qwen Code sessions run against the existing adapters.
- Docs (`docs/en/guide/hosted-agents.md`, `docs/zh/guide/hosted-agents.md`, and the agents section of both `template-server-api.md`) describe every route, the label contract and every refusal, with a paragraph on both getting-started guides and `examples/agents/` unchanged in scope (those two CLIs only).
- The three CANNOT operations and `DELETE /v1/models/{id}` answer a labeled 404.
