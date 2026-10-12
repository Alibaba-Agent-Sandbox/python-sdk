# ops-cannot: the adversarial review of "implement every Agents API and Responses operation"

Reviewer role: honesty and security, opposed to the maintainer's goal of implementing every operation the SDK can call.
The maintainer's direction stands. This file does not argue for the old 25-of-47 cut. It lists what must be refused, and what may be
implemented only with an explicit local semantic. Everything else in the 47 plus Responses plus `GET /v1/models` can ship.

Evidence read: `05-agents-api.md`, `03-policy-and-permissions.md` (sections 12, 15.1-15.8), `server-sdk/src/easy_sandbox/server/agents/*`
(`config.py`, `wire_sessions.py`, `runtime.py`, `store.py`, `procenv.py`, `redact.py`, `errors.py`, adapters), and the real wheel
`openai==3.29.0` at `/tmp/oai-venv/.../openai/types/beta/agents/**` and `resources/responses/**` for the official parameter and object shapes.
Nothing here edits source.

## 0. Ground rules used for every verdict

Verdict vocabulary (as in the brief):

* **IMPLEMENT**: the local operation is indistinguishable in meaning from the official one.
* **IMPLEMENT-AND-LABEL**: it works, but a caller must be able to tell it is local. See the label contract below.
* **REFUSE**: `404` with the OpenAI error envelope, `type: not_found_error`, `code: agents.not_implemented_locally` (or `resource_not_found` when the id truly does not exist), header `x-should-retry: false`. Never 501 (the SDK retries 5xx), never an empty 200, never a 200 with a plausible fake object.

Two distinct refusal shapes. A *route* refusal is the 404 above. A *variant* refusal (one `type`, one parameter, one field of an otherwise
implemented route) is `400 invalid_request_error` with `param` naming the field and `x-should-retry: false`. A route that
accepts a field and ignores it is the most common lie in this API and is banned: **accept-and-ignore is not allowed for any field that
changes isolation, network reach, tools, billing or storage**. Fields that only affect model sampling may be ignored if they are listed in the
`X-Easy-Sandbox-Ignored-Params` response header (already in the Responses design, `agents-api.md` 6.4).

**Label contract** (what IMPLEMENT-AND-LABEL means, concretely). The `openai` pydantic models allow extra fields, so a caller can read
`obj.model_extra["x_easy_sandbox"]`. Every local object that has an official counterpart whose meaning differs carries:

```json
"x_easy_sandbox": {"local": true, "compute": "local_process", "differences": ["<stable-code>", ...]}
```

and every response on these routes carries the header `X-Easy-Sandbox-Local: 1`. `compute` is one of `local_process`, `local_state`, `none`;
it is never `openai_hosted`. `differences` are stable codes documented in one table (for example `queued_not_steered`, `memory_only`,
`snapshot_copy`, `secret_in_agent_env`). Do not use `metadata` for the label: it is the caller's namespace (16 keys, official limits).

Hard rules, applied below as R1-R6:

* R1. LLM provider keys never appear in an HTTP response, in `argv`, in an error `message`/`param`, in an SSE event, or in the journal.
* R2. Tool and MCP secrets are write-only. No route returns a value, a prefix, a length, a hash or a last-4 of one.
* R3. Agent sessions are exec-effect and need an explicit `AgentScope`. Anything that can start, resume or steer a CLI process, or write files the CLI will execute or read, inherits that requirement.
* R4. No route claims `openai_hosted` compute, a hosted network policy, hosted package installation, an egress proxy or a hosted vault when nothing was scheduled at OpenAI.
* R5. Subagent routes never invent a subagent the CLI did not emit.
* R6. A Responses object never claims a tool ran unless the CLI emitted a tool event for it; it never claims a tool class the CLI does not have.

## 1. Defects already visible in the current source that make "200 with an OpenAI-shaped object" a lie today

These are not hypothetical. They exist in `agents/` now and must be fixed before the corresponding route is exposed with the full op set.
They matter because the maintainer's direction multiplies the number of routes that reuse these mappers.

| # | Where | What is wrong | Rule |
|---|-------|---------------|------|
| D1 | `wire_sessions.session_object` | `agent.id` and `agent.name` are both the definition *name*; the official `agent.id` is an opaque id. `GET /agents/{id}` and `session.agent.id` must agree, and two principals can collide on a name. | wrong id |
| D2 | `session_object` | `environment.id` is the constant `"env_easy_sandbox"` and `remote_url` is `""`. Every session claims the same environment id; a caller that stores it and later calls `environments.files.list(env_id)` reaches a shared object. An empty `remote_url` makes a self-hosted worker try to connect to `""`. | wrong id, scope bypass |
| D3 | `session_object` | `text.verbosity: "medium"`, `service_tier: "default"`, `tools: []`, `reasoning.summary: None` are hard-coded. A caller who asked for `low`, `priority` or a web search tool reads back something that is not what ran, and gets no 400 at create. | accept-and-ignore |
| D4 | `session_object` | `agent.model` falls back to the adapter name (`"codex"`) when the definition has no model. `codex` is not a model. | fake object |
| D5 | `item_object` | message and reasoning items with status `failed` are mapped to `completed` (`_status` too). A failed item is shown as successful. | claims success |
| D6 | `item_object` | Any item that is not message, reasoning or command_execution becomes `mcp_call` with `server_label: "agent"`. A CLI-native tool (Read, Edit, Grep, WebSearch) is reported as an MCP call to a server that does not exist. | claims a tool class that did not run |
| D7 | `item_object` | Only assistant output is mapped (`role: "assistant"` hard-coded). The caller's own input messages are in `Turn.input_items` but are not emitted by `items.list`; the list is not the transcript the official one is. | missing items |
| D8 | `AgentSpec.public_dict` | Masks `api_key`, `git.token`, `secrets`, MCP `env` and `headers` values, but returns `env` values, MCP `args`, MCP `url` and `provider.base_url` verbatim. An MCP URL such as `https://host/mcp?token=...`, an arg such as `--token=...` or a `base_url` with userinfo is a secret echo. `extra_args` and `command` are echoed too. | R1/R2 |
| D9 | `procenv.build_child_env` | `spec.env` is applied after the adapter env and may set `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`, `HTTP(S)_PROXY`, `NODE_OPTIONS`, `PYTHONPATH`, `CODEX_HOME`, `GIT_*`. `_DENIED_ENV` blocks only four names (`LD_PRELOAD`, `LD_AUDIT`, `LD_LIBRARY_PATH`, `DYLD_INSERT_LIBRARIES`). Redirecting the LLM endpoint through `env` bypasses the "caller `base_url` forbidden / `llm_override` off" rule (05 section 7) and sends the provider key to the caller's host. | R1 |
| D10 | `adapters/codex.py` | Remote MCP `url`, `base_url` and stdio MCP `args` are written to `argv` as `-c key=value`. Secrets are in env, but only if the caller kept them out of those three fields (see D8). `extra_args` is caller-controlled argv with no validation. | R1 |
| D11 | `runtime.py` / `store.py` | No owner or principal on `Session`, `Turn`, or `AgentSpec`. 05 section 10.6 requires ownership; the code has none. A `list` route today would enumerate every caller's sessions. `AgentStore.resolve` registers an *ephemeral definition as a side effect of a read-shaped lookup* (`models`, `responses`). | scope bypass |
| D12 | tree | `wire_responses` is imported in the `runtime.py` docstring but does not exist; no code exists for artifacts, traces, subagents, vaults, environments, templates or `previous_response_id`. 05 claims 25 ops "tier 1" while the tree implements sessions/turns/items/events only. | doc claims more than the code |
| D13 | `errors.agents_wire_code` | Unknown internal codes collapse to `internal_error`; `cancelled` also maps to `internal_error`. A cancelled turn reports an internal error. `authentication_error` on a turn means "the sandbox's LLM key was rejected", which in OpenAI vocabulary means "your OpenAI key is bad". | misleading error |

## 2. Per-group review

Notation: **Official** = what the caller believes. **Local** = what the sandbox can truthfully do. **Failure** = what goes wrong on a 200 with a
fake OpenAI-hosted object. Counts are from `05-agents-api.md` section 1 (47 operations).

### 2.1 Agent definitions (5: create, retrieve, update, list, delete)

* **Official.** A durable, server-side, versioned Agent resource: `model`, `instructions`, `tools` (function, mcp, web_search, computer_use, tool_search,
  programmatic_tool_calling), `reasoning`, `service_tier`, `text`, `multi_agent`, `metadata`. Reusable by any session in the project.
* **Local.** A stored `AgentSpec`: runtime adapter, model string passed to the CLI, instructions, MCP servers, provider reference, permissions. In memory, or
  state dir without secrets. Only MCP tools are real (via the CLI). The CLI has its own native tools that the definition cannot enumerate or disable beyond `permissions`.
* **Failure of a fake object.**
  * `tools: [{"type":"web_search"}]` or a `function` tool accepted and ignored: the caller believes the model can search or call back. Function tools additionally imply `requires_action` + `tool_result`, which are unsupported (05 section 4, C-14).
  * `multi_agent.enabled: true` accepted: the caller expects subagents (R5).
  * `service_tier: priority|flex|fast` accepted: the caller believes it changed billing/latency.
  * id = name (D1): collisions between principals, `agent_id` guessable.
  * `GET` echoing `provider.api_key` or MCP URL tokens (D8): R1/R2.
  * `provider.api_key_env` pointing at an arbitrary server variable: exfiltration of any server env var into the child.
* **Local semantics to document.** Update is in place (no versions); running sessions keep the snapshot they started with; delete never kills sessions
  (they keep their embedded snapshot). Secret fields are accepted only if the policy statement carries `AgentScope(llm_override=True)`, are write-only, and the
  response shows `"***"` or omits them. `api_key_env` must be on an operator allowlist. Validation errors must name the field, never echo the value.
* **Verdict.** IMPLEMENT-AND-LABEL (`create`, `retrieve`, `update`, `list`, `delete`). Variant refusals (400): tool types other than `mcp`,
  `multi_agent.enabled=true`, `service_tier` outside `auto|default`, `reasoning.effort` on an adapter that cannot honour it (rather than dropping it), any `provider.base_url` not in `AgentScope.llm_hosts`.
  `list`/`retrieve` are principal-filtered (D11).

### 2.2 Environments (3: create, retrieve, list)

* **Official.** `environments.create` takes an `environment` whose only SDK-typed value is `openai_hosted`: container, network policy (`enabled|disabled|restricted` with
  allowed/blocked domains), `packages` (npm, python, system), `setup_commands` (confidential shell), `plugins` (ZIP), `skills`, `files`, `env`, `desktop`,
  `environment_template_id`, `vault_ids`. The result is an `agent.environment` with `status` and `type`.
* **Local.** A named binding to one admitted workspace directory (`self_hosted`) plus an allowlisted env map. Nothing is provisioned. `EnvironmentInfo.type` can legitimately be
  `self_hosted` (the response model allows it), so a truthful 200 exists.
* **Failure of a fake object.** `network: {access: "disabled"}` accepted and ignored: the caller believes no egress, the CLI has full egress (03 section 12: network control is the
  platform's job). `packages`/`setup_commands` ignored: the caller believes dependencies exist. Accepting and *running* them is worse: `setup_commands` is arbitrary shell executed from a
  route with no exec effect, no `AgentScope`, no command policy (R3, and it defeats P3). `plugins` ZIPs are code. Returning `type: "openai_hosted"` is a flat lie (R4).
* **Local semantics.** `create` accepts `{"type":"openai_hosted"}` only when it carries no other configuration, and returns `type: "self_hosted"`, a fresh opaque id, `status: "ready"`,
  `compute: local_process`, and `workspace_directory`. A caller who wants a directory binding sends `type: "self_hosted"` (allowed by the wire, not by the SDK type hint, so `extra_body`). The directory goes through the
  same `PathScope` admission as `sessions.create`. This deliberately differs from 05 section 5 (C-6), which converts a hosted request silently: conversion is acceptable only for an empty hosted request.
  `env` is accepted only after a deny list far wider than `_DENIED_ENV` (D9: LLM base URLs and keys, proxy variables, `NODE_OPTIONS`, `PYTHONPATH`, `PATH`, `HOME`, `CODEX_*`, `GIT_*`, `EBX_*`) and is never returned.
* **Verdict.** IMPLEMENT-AND-LABEL for `create`, `retrieve`, `list`. Variant refusals (400, `x-should-retry: false`): `network`, `packages`, `setup_commands`, `plugins`, `skills`,
  `desktop`, `container_size`, `environment_template_id`, `files` with `type: file_id`, and `vault_ids` unless 2.9 is implemented. `environment_template_id` is refused even if 2.4 exists, because applying a template that carries refused fields would reintroduce them.

### 2.3 Environment files (2: create, list)

* **Official.** Upload a file (inline base64 or `file_id`) to an absolute path under `/workspace` of an environment; list live files with `path` and `size_bytes`.
* **Local.** Writing and listing files under the environment's workspace directory.
* **Failure of a fake object.** If implemented as a plain helper, `create` is an unauthenticated-by-scope file write: it bypasses `files.write` `PathScope` (P1, P2), can write through a symlink out of the root, can overwrite
  a file the agent will execute (including `.git/hooks/*`, `.codex/config.toml`, `.mcp.json`, shell rc files, which change what the next CLI turn runs), and can reach state dir paths if the check is lexical. `list` as a plain
  walk lists the state dir, `.git`, and server files if the workspace is `/`. `file_id` has no Files API behind it: accepting it would return a 200 for a file that was never fetched.
* **Local semantics.** The handler is a thin consumer of the files group: it calls the same admission as `files.write` and `files.list` on the environment's directory (race-free open, no symlink follow, refuse hardlinks and non-regular files, size cap, system deny list, `protect_dir`). It needs *both* an environment ownership check and an allow for the files ops. It writes only
  below the environment's workspace directory; the official "absolute path inside `/workspace`" is interpreted relative to that directory and the response `path` shows what was actually written. No overwrite of an existing file unless the same bytes (otherwise 400 `agents.file_exists`, `x-should-retry: false`; not 409, the SDK retries 409). Paths that name agent-config locations (`.git/**`, `.codex/**`, `.claude/**`, `.cursor/**`, `.mcp.json`, `AGENTS.md`, shell rc) are refused unless the statement is `permissions: full` + `unconfined_ok`.
* **Verdict.** IMPLEMENT-AND-LABEL (`create` and `list`; labels `local_workspace`, `no_overwrite`). Variant refusal: `type: file_id`.

### 2.4 Environment templates (5: create, retrieve, update, list, delete)

* **Official.** A reusable *hosted* template: network, packages, setup commands, plugins, skills, files, env, desktop, name. Applied before inline config; "network overrides cannot broaden its policy."
* **Local.** There is nothing hosted to template. A record of `{name, env, files}` is storable; the other fields have no local meaning. The Easy Sandbox "template" is a different thing (image/deploy templates);
  reusing the word invites a caller to believe `environment_template_id` selects a sandbox image.
* **Failure of a fake object.** A template that stores `packages`/`setup_commands`/`network` and returns them in the object tells the caller they will be applied. A template applied at session create that executes `setup_commands`
  is an exec route without exec policy (as 2.2). A returned `network` with `restricted` is a security claim with no enforcement. The echo of inline file `data` or `env` would leak.
* **Verdict.** The maintainer's direction wants this implemented; the only honest subset is thin. IMPLEMENT-AND-LABEL for `{name, env, files(inline)}` with the env and files rules from 2.2/2.3, and with `x_easy_sandbox.differences: ["not_hosted_template", "applies_env_and_files_only"]`.
  Any of `network`, `packages`, `setup_commands`, `plugins`, `skills`, `desktop`, `capability_directories` is a 400 variant refusal. If the maintainer will not accept a reduced template, the alternative is a **route REFUSE** for all five; there is no honest middle that keeps the refused fields.
  Template inline file bodies and env values are write-only (return `size_bytes` only, the official `FileHostedTemplateFileResourceInline` shape already does).

### 2.5 Sessions (5: create, retrieve, update, list, delete)

* **Official.** A hosted conversation with an agent in an environment, with status machine, embedded `agent`, `environment`, `usage`, `vault_ids`, `required_actions`.
* **Local.** A journaled sequence of local CLI processes. Everything about it is exec and net.
* **Failure of a fake object.**
  * `environment.type: "openai_hosted"` returning a session: R4. Must stay `400 agents.environment_unsupported` (05 section 5).
  * `agent` overrides (`tools`, `multi_agent`, `service_tier`, `text`, `reasoning`) accepted and dropped (D3).
  * `vault_ids` accepted and not applied: the caller believes MCP auth is attached; the CLI runs unauthenticated or uses another credential.
  * `list` without ownership (D11): cross-principal enumeration.
  * `session.environment.id` constant (D2).
  * `DELETE` that returns 200 while the process group is still alive: a deleted session that still runs and writes.
  * `status` values: `requires_action` can never occur locally, so it must never be emitted; `usage: null` must be reported as null, not zeros that read as "no tokens used".
* **Local semantics.** `create` is exec-effect, two-level gated, `AgentScope` required (R3, 15.6); `workspace_directory` admitted by `PathScope`; sessions record principal, and a foreign id answers like an unknown id. `update` changes `metadata` only (400 for `agent`, `vault_ids`, `environment`). `delete` returns only after the process group is gone (SIGTERM, SIGKILL after 5 s) or returns 202-equivalent state in the object; it deletes the journal and artifact snapshots.
* **Verdict.** IMPLEMENT-AND-LABEL (all five). Not plain IMPLEMENT because compute is a local process, steering is a queue, and `usage` is adapter best-effort.

### 2.6 Session events (2: `events.create` send, `events.stream`)

* **Official.** `POST .../events` delivers input messages, cancel, and tool/computer-use results; the server steers an active turn (`active_turn_not_steerable` exists as an error code). `GET .../events` is the SSE stream.
* **Local.** `input.message` queues a new turn (FIFO, max 20); `input.cancel` signals the process group; there is no mid-turn steering; there is no tool-result channel.
* **Failure of a fake object.**
  * `202` for `input.tool_result` / `computer_use_approval_request_result`: the caller believes its function result reached the model. It reached nothing. Must be `400 agents.tool_result_unsupported` (already in 05; keep).
  * `202` for an `input_image`/`input_file` content part that is dropped: silent data loss.
  * `202` for `input.message` during an active turn with no visible difference: the caller believes it steered the turn; it queued a new one (`queued_not_steered`). The 202 is empty so the only place to say this is the `turn.created` event, which must carry `status: "queued"` and the label.
  * `input.cancel` on an idle session: answer `400 agents.no_active_turn`, not a silent 202 and not 409 (retried).
  * The SSE stream replaying a journal that contains un-redacted secrets; the redactor catches only registered verbatim/URL/JSON-escaped values and four token shapes, not base64 or split output (`redact.py` says so), so command output deltas can carry a key the agent echoed.
  * Retry storms: an `Idempotency-Key` replay must return the original 202 and must not start a second turn; a mismatch is `409 idempotency.mismatch` with `x-should-retry: false`.
* **Verdict.** `send_event`: IMPLEMENT-AND-LABEL (exec-effect, `AgentScope` required; variants `tool_result`, `computer_use_approval_request_result`, image/file parts are 400). `stream_events`: IMPLEMENT-AND-LABEL (resume `?after=` is an extension; `x_easy_sandbox.differences: ["redaction_best_effort"]` on `command_execution_output.delta`). Stream authorization is read-effect plus ownership.

### 2.7 Session items (1: list) and turns (3: list, retrieve, list items)

* **Official.** The full ordered transcript of a session or turn, including the user's items, with official item types.
* **Local.** Items the CLI emitted plus the stored input messages. Item types are message, reasoning, command_execution, and (when really MCP) mcp_call.
* **Failure of a fake object.** D5 (failed shown as completed), D6 (native tool reported as MCP), D7 (no user items), D13 (cancelled shown as an internal error). Item `command` and `output` carry whatever the agent ran: with redaction best-effort, these are the highest-leak fields in the API. Turn `usage` as zeros when unknown reads as "free".
* **Local semantics.** User input items are echoed from `Turn.input_items`. Native CLI tools use a documented `tool_call` item type with `tool_name` and an honest `status`, not `mcp_call`; `mcp_call` only when the parser saw an MCP namespace (`mcp__server__tool`, codex `mcp_tool_call`). `failed` stays `failed`. Item and turn lists are paginated by the common envelope, and a foreign session id is a 404 before any item is read.
* **Verdict.** IMPLEMENT-AND-LABEL (`items.list`, `turns.list`, `turns.retrieve`, `turns.list_items`) after D5-D7 and D13 are fixed. Output redaction caveat is a documented difference.

### 2.8 Artifacts (4: list, retrieve, content, delete)

* **Official.** An *immutable* file published by a completed turn: `id`, `environment_id`, `path` (original absolute path), `size_bytes`, `turn_id`. `content` returns the bytes. `delete` removes the artifact.
* **Local.** Files the CLI reported as written or changed in a turn (codex `file_change` items; claude `Write`/`Edit` tool results). The sandbox can copy those into a server-owned snapshot at turn completion.
* **Failure of a fake object.**
  * Serving `content` from the live workdir: not immutable (the agent edits it next turn), follows symlinks out of the workdir, and is a file read with no `files.read` check, no `PathScope`, no size cap (scope bypass; R3).
  * Listing by scanning the workdir after the turn: invents artifacts the CLI never published (R5-style invention) and exposes unrelated files such as `.env` and `.git/config`.
  * `path` is a host absolute path: for a sandbox where the workspace is `/workspace` this is fine; for a per-session private workdir it leaks the server's state dir layout. Report the path relative to the environment's workspace directory, absolute-from-workspace.
  * `delete` returns `deleted: true` when only the snapshot was removed and the file on disk remains: callers who delete an artifact to remove a secret-bearing file believe it is gone.
  * An artifact can legitimately contain a secret the agent read from its own env (D9/R1 residual risk): the content route is an exfiltration channel from the sandbox to the caller. That equals what the agent can already print into items, but it bypasses redaction (binary), so it must be gated by the same ownership and a separate allow.
* **Local semantics.** Artifacts exist only for paths the adapter reported (no scan); at turn completion each is copied with `O_NOFOLLOW`, regular files only, size cap (default 10 MiB per file, 100 per turn), into the 0700 state dir; the artifact id is opaque; `path` is workspace-relative; `delete` removes the snapshot only and the response says so (`deleted_scope: "snapshot"`); `content` serves the snapshot with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`. Adapters without file-change events (`cursor`, `command`, `qwen_code` unless verified) yield an empty list, which is true.
* **Verdict.** IMPLEMENT-AND-LABEL (`list`, `retrieve`, `content`, `delete`; labels `snapshot_copy`, `reported_paths_only`, `delete_removes_snapshot_only`).

### 2.9 Traces (1: list)

* **Official.** `agent.session.trace` with an `otlp` ExportTraceServiceRequest, one per root turn, "only currently published data."
* **Local.** The runtime knows turn start/end and item start/end times. It does not have model-call spans, token-level spans or subagent spans, and no OpenAI trace backend exists.
* **Failure of a fake object.** Synthesized spans for model calls or tool latencies the CLI never reported: invented telemetry. Putting prompts, command lines or tool arguments into span attributes: leaks secrets past redaction (commands contain tokens), and the OTLP object is machine-forwarded to collectors by SDK users.
* **Verdict.** IMPLEMENT-AND-LABEL. Default response is the honest empty list envelope (as 05). Optional upgrade: one trace per turn whose spans are built only from observed `turn` and `item` lifecycle timestamps, with attributes limited to `item.type`, `status`, `exit_code` and durations; resource attribute `service.name=easy-sandbox-local`; no text, no command, no arguments. Label `trace_from_journal_timing_only`.

### 2.10 Subagents (6: list; retrieve; items; turns list/retrieve/items)

* **Official.** Subagents spawned by `multi_agent` config or the model; each has its own turns and items.
* **Local.** No adapter in the tree parses a subagent event (`grep subagent adapters/` finds nothing). Claude Code's Task tool and codex collaboration features can spawn sub-agents that today appear as flat tool calls or not at all.
* **Failure of a fake object.** Listing `[]` is true only while no CLI subagent happened. If claude ran a Task tool and the route answers `{"data": []}` with `multi_agent.enabled: false`, the caller concludes nothing was delegated: a lie by omission. Synthesizing a subagent per Task/tool call, or mapping a CLI's thread id to a subagent id, is R5. Returning a subagent object with a fabricated id for the detail routes would make the SDK follow it into five more routes.
* **Local semantics.** `list` returns the envelope with exactly the subagents an adapter emitted as `subagent.started` events carrying a native id; today that is none, and the object says so (`differences: ["adapter_emits_no_subagent_events"]`). The five detail routes answer `404 resource_not_found` + `x-should-retry: false` for any id; the day an adapter emits native subagent ids they become IMPLEMENT-AND-LABEL driven strictly by those events. A Task-tool call in the meantime is an ordinary `tool_call` item (2.7).
* **Verdict.** `list`: IMPLEMENT-AND-LABEL (empty by construction, labelled). The five detail routes: REFUSE.

### 2.11 Vaults (5: create, retrieve, update, list, delete)

* **Official.** A named collection of credentials for MCP servers and OpenAI-hosted environments. Referenced by `vault_ids` on sessions and environments.
* **Local.** A write-only secret holder whose only truthful consumer is the local CLI's MCP connection. 05 section 4 says "not planned"; the maintainer's direction overrides that, and a narrow honest local vault exists. It is the highest-risk group in the review.
* **Failure of a fake object.**
  * A vault that stores credentials and does not apply them: callers believe MCP auth works.
  * Secrets at rest in a file in `state_dir`: the agent CLI runs as the same uid (A9). `protect_dir` stops `PathScope`, not the CLI's own shell, so a prompt-injected agent reads every vault in every principal's session. At-rest secrets must be memory-only, or encrypted with a key that exists only in server memory.
  * Cross-principal use: principal B names principal A's `vault_id` in `sessions.create`. Ownership must be checked on `vault_ids`; a foreign id is a 404.
  * `vault_ids` and `AgentScope.mcp`: a vault credential must be injected only into an MCP server the policy admitted. Otherwise a caller adds an `mcp` tool pointing at their own host and a vault credential for it, and the server sends the credential from the sandbox to anywhere the caller chooses (acceptable for the caller's own secret, a data-exfiltration path for a secret placed in the vault by a *different* operator-provisioned principal).
  * Deleting a vault while a session uses it: the next turn runs unauthenticated without saying so.
* **Local semantics.** Memory-only by default (`differences: ["memory_only"]`; lost on restart, which is a 404, not an empty vault). Owned by the creating principal; counted against `max_vaults`. `delete` fails a running session's next MCP use with an explicit turn error, not silent unauthenticated use. `list`/`retrieve` return `id`, `name`, `metadata`, `created_at` only.
* **Verdict.** IMPLEMENT-AND-LABEL (all five; label `memory_only`).

### 2.12 Vault credentials (5: create, list, retrieve, update, delete)

* **Official.** Three `auth` types: `mcp_oauth` (access token, optional refresh with token endpoint), `static_bearer` (token for an MCP URL), `environment_variable` (placeholder in the sandbox env, secret substituted by an *egress proxy* for allowed hosts, "sandbox code cannot read the real secret"). `networking` is `unrestricted` (needs `environment.network.access: restricted`) or `limited` (`allowed_hosts`).
* **Local.** `static_bearer` and `mcp_oauth` (access token) can be attached to a local CLI's MCP server header through the existing `${VAR}` carrier mechanism (`McpServerSpec.header_var`; secret in child env only, never argv). There is no egress proxy and no network enforcement.
* **Failure of a fake object.**
  * `environment_variable`: the official contract is that sandbox code never sees the secret. Locally the only way to deliver it is to put the real value in the CLI's environment, where agent-executed code can read it. Returning 200 here is a direct inversion of the stated guarantee (R2, R4). The proxy placeholder substitution cannot be faked.
  * `networking.unrestricted` or `limited`: the router cannot enforce host limits for a CLI's traffic. For MCP the one enforceable check is that the credential's `mcp_server_url` host equals the MCP server entry's host at injection time; `unrestricted` depends on a hosted network policy that does not exist.
  * `mcp_oauth.refresh`: the server would call a caller-chosen `token_endpoint` with the refresh token and client secret from the sandbox: SSRF plus credential exfiltration to an attacker's endpoint (the same hazard as caller-supplied `base_url`, 05 section 7). It also needs a background job with no op ID and no scope.
  * Any response containing `access_token`, `token`, `secret_value`, `refresh_token`, a prefix, length, or hash.
  * Error messages that quote the submitted secret (validators that echo `input`).
  * `update`/rotate returning the new secret; `list` with a `secret_name` that is an env var name colliding with a reserved name (`EBX_*`, provider keys).
* **Local semantics.** Only `static_bearer` and `mcp_oauth` without `refresh`. `mcp_server_url` is `https` only, parsed once through `UrlScope` (`block_private=True`, host allowlist); a credential is injected only into an MCP server entry with the same scheme, host and port, and only for sessions that name its vault. The response shows `auth.type`, `mcp_server_url`, `networking` as stored, `created_at`, `updated_at`; never any secret-derived value. Label `secret_in_agent_env` (agent-executed code can read the header value from the CLI's environment: say it on every credential object and in `doctor`).
* **Verdict.** IMPLEMENT-AND-LABEL for `static_bearer` and access-token-only `mcp_oauth` (all five operations). Variant refusals (400): `environment_variable`, `mcp_oauth.refresh`, `networking.unrestricted`, `limited` with hosts other than the credential's own URL host.

### 2.13 Responses (`POST /responses`, `GET`, `DELETE`, `cancel`, `input_items`, `input_tokens`, `compact`, WebSocket `connect`)

* **Official.** The caller sends `model` plus `input`/`instructions`/`tools`/`text`/`include`/`conversation`/`previous_response_id`/`store`/`background`, and gets a `Response` produced by an OpenAI model with OpenAI-hosted tools (web_search, file_search, code_interpreter, computer_use, image_generation, function calling, remote MCP) running as requested.
* **Local.** A turn of a local CLI agent. Tools are the CLI's own. The "model" is whatever the adapter was told. Nothing runs at OpenAI.
* **Failure of a fake object (the core of this review).**
  * `tools: [web_search|file_search|code_interpreter|computer|image_generation|function]` accepted and ignored: the Response carries `tools: [...]` as echoed, the caller believes the tool existed. Echoing request `tools` into `Response.tools` is itself a claim. R6.
  * Output items shaped as `web_search_call`, `function_call`, `code_interpreter_call` or `local_shell_call` synthesized from CLI events: claims an OpenAI tool class ran when the CLI ran something different (D6).
  * `Response.model` echoing the request (`gpt-5`) when the CLI ran `codex` with a configured upstream: lies about which model answered. The model that ran is the adapter's configured one, or unknown.
  * `Response.id` not `resp_`-prefixed, or an id the SDK later retrieves from a different principal. Retrieving an id minted by *OpenAI* (a `resp_...` created elsewhere) must be 404, never a 200 stub.
  * `store: false` accepted but kept in the journal (or `store: true` meaning durable): the local retention is TTL and bounded (05 section 9), not OpenAI's 30 days.
  * `previous_response_id` branching: the CLI session is linear. Branching a non-latest response without saying so would run the new prompt in the wrong conversation state.
  * `conversation`, `prompt` (stored prompt templates), `text.format` json_schema, `include` of `reasoning.encrypted_content`, `file_search_call.results`, `web_search_call.action.sources`, `computer_call_output.output.image_url`: each promises a payload the local runtime cannot produce.
  * `service_tier` echoed as requested; `usage` zeros when unknown; `incomplete_details` null on a CLI that was SIGKILLed by a timeout.
  * `background: true` returning `queued` and never completing after a restart (turns are marked failed on restart, 05 section 9; the Response must be `failed`, not stuck).
  * `compact`: official compaction returns an encrypted compaction item that only OpenAI can read back. A local "compaction" is a summary that does not carry the same meaning. `input_tokens.count`: a local tokenizer count is not the model's count (CLI runs a different model); returning a number is a billing-shaped claim.
  * WebSocket `connect`: a new transport with no op ID, no Host/Origin check in the 15.1 order, and no ticket mechanism; 15.8 says tokens are never accepted in URLs.
  * Retry storms: a 5xx on `POST /responses` is retried by the SDK (default 2) and starts a second CLI turn unless `Idempotency-Key` is honoured; any non-retryable condition must carry `x-should-retry: false`.
* **Local semantics (what is honest).** `model` selects an agent definition or an adapter explicitly (05 A6; never inferred from a real model name; `gpt-5-codex` passes through as the CLI model). `tools`: only `mcp` with `server_label`, `server_url` admitted by `AgentScope.mcp`, and `headers` treated as write-only secrets (per `agents-api.md` 6.4); everything else is `400 unsupported_parameter` with `param: tools[i].type`. `Response.tools` lists only what was actually passed to the CLI, `[]` otherwise. Output items: `message` (assistant), `reasoning` summary when the CLI emitted one, `mcp_call` only for real MCP, `tool_call` or `local_shell_call` only if the official `local_shell_call` shape can be filled faithfully; otherwise a documented extension item. Each carries `x_easy_sandbox`. `Response.model` is the model string actually handed to the CLI or the adapter name with `x_easy_sandbox.model_resolved: false`. `usage` is null when the adapter reports nothing. Execution requires the same exec-effect `AgentScope` as sessions (R3): `responses.create` is **not** a read op just because OpenAI's is.
* **Verdicts, by operation.**
  * `POST /responses` (+ `stream`, `background`): IMPLEMENT-AND-LABEL.
  * `GET /responses/{id}`: IMPLEMENT-AND-LABEL (only for ids this server minted, owner-filtered; others 404).
  * `DELETE /responses/{id}`: IMPLEMENT-AND-LABEL (removes the Response and its turn record; says nothing about the CLI session).
  * `POST /responses/{id}/cancel`: IMPLEMENT-AND-LABEL (only while the turn is running; terminal state reached before returning; otherwise `400`, not 409).
  * `GET /responses/{id}/input_items`: IMPLEMENT-AND-LABEL (items as received; images/files were refused at create so none appear).
  * `POST /responses/input_tokens`: REFUSE (no tokenizer for the model the CLI will call).
  * `POST /responses/compact`: REFUSE (the official artifact is opaque, server-side, model-specific).
  * `WebSocket /responses` (`responses.connect`): REFUSE until the transport has an op ID and the 15.1/15.8 handshake; a mounted socket that answers is a new unaudited exec surface.
  * Variant refusals (400): `tools` other than `mcp`, `conversation`, `prompt`, `text.format` other than `text`, `include` values the runtime cannot fill, `input_image`/`input_file` parts, `previous_response_id` that is not the session's latest.

### 2.14 `GET /v1/models`

* **Official.** The models the account can use; `id`, `object: "model"`, `created`, `owned_by`. Frameworks use the list to decide what to call and what features exist.
* **Local.** Agent definitions and adapters. They are not models; a caller who feeds `codex` to another endpoint gets nonsense.
* **Failure of a fake object.** `owned_by: "openai"` or well-known ids (`gpt-4o`) listed because an upstream gateway happens to serve them: a lie about this server. Listing every definition regardless of principal leaks names. `AgentStore.resolve` registers an ephemeral definition on lookup (D11): `GET /v1/models/{id}` or `POST /responses` with a random string-sized adapter alias mutates server state from a read-shaped call. Listing adapters that are not installed implies `codex` is ready. The list must never include `base_url`, `api_key_env` or the presence of a key (R1).
* **Local semantics.** `owned_by: "easy-sandbox-local"`; only definitions the principal may see plus adapters that are mounted for the principal; `x_easy_sandbox: {kind: "agent_definition"|"adapter", installed: bool}`; `GET /v1/models/{id}` is 404 `model_not_found` for anything not listed and has no side effect; `DELETE /v1/models/{id}` (fine-tune delete in OpenAI) is REFUSE.
* **Verdict.** `list` and `retrieve`: IMPLEMENT-AND-LABEL. `DELETE /v1/models/{id}`: REFUSE.

## 3. Cross-cutting requirements that gate every IMPLEMENT-AND-LABEL row above

1. Principal ownership on sessions, turns, responses, artifacts, environments, vaults, credentials, templates and definitions (D11). A foreign id and an unknown id are byte-identical 404s (15.8). Without this, `list` routes are scope bypasses.
2. One shared `x_easy_sandbox` label builder and one table of difference codes. Tests assert that a local object never contains `compute: "openai_hosted"` and that every IMPLEMENT-AND-LABEL route emits the header.
3. A secret-echo test per object: create with a canary secret in every write-only field (provider key, MCP header and env value, MCP URL query token, git token, vault token, template env, inline file data) and assert the canary is absent from every response, SSE frame, error message, audit record, process `argv` (read from `/proc/<pid>/cmdline` of the fake agent), journal file and artifact listing.
4. `argv` hygiene (D10): reject, at admission, caller `extra_args` that match secret-bearing flags (`--api-key`, `--token`, `--header`), MCP `url` with userinfo or query, and MCP `args` containing a registered secret; carry secrets only by env carrier.
5. Wider env deny list than `_DENIED_ENV` (D9) shared by definitions, environments and templates.
6. All non-retryable failures set `x-should-retry: false`: 400, 401, 403, 404, 409 (idempotency, file exists), 413, 415. 5xx is reserved for genuinely transient server faults.
7. `agents.<a>.*` adapter ops and the generic ops are both required for any route that starts a process (two-level gate, 05 section 3), including `responses.create`; `responses.*` read routes need only the generic op plus ownership.
8. `doctor`/`explain` print the exposure statements: `key is exposed to agent-executed code`, `secret_in_agent_env`, `memory_only`, `not confined by path/command scopes`.

## 4. Differences from `05-agents-api.md` that this review asks the maintainer to accept

* Sections 4/A4 "Not planned: templates, vaults, credentials" and "Out of 0.3.0: Responses" are superseded by the maintainer's direction; this file gives the honest subset for each instead of a route refusal (templates reduced; vaults memory-only; credentials two of three types).
* Section 5 C-6: `environments.create` must not silently convert a *configured* `openai_hosted` request; only an empty one is converted, and the response says `self_hosted`.
* Section 3: `subagents.list` stays empty-and-labelled, but the five detail routes remain refusals for the reason in 2.10, not because "tier cut".
* `traces.list` stays honest-empty by default.

---

## REFUSE rows (route-level: 404 `not_found_error`, `x-should-retry: false`; never 501, never an empty 200)

1. `GET /agents/sessions/{id}/subagents/{subagent_id}` - no subagent exists unless an adapter emitted a native id; none does today (R5).
2. `GET .../subagents/{id}/items` - same reason; items of a subagent that was never emitted would be invented.
3. `GET .../subagents/{id}/turns` - same reason.
4. `GET .../subagents/{id}/turns/{turn_id}` - same reason.
5. `GET .../subagents/{id}/turns/{turn_id}/items` - same reason.
6. `POST /responses/input_tokens` - no tokenizer for the model the CLI will actually call; any number is a fabricated billing figure.
7. `POST /responses/compact` - the official result is an opaque, model-specific server-side artifact that cannot be reproduced locally.
8. `WebSocket /responses` (`responses.connect`) - a new transport with no op ID or 15.1/15.8 handshake; an unaudited exec surface.
9. `DELETE /v1/models/{id}` - no fine-tuned models exist; deleting an adapter or definition through a model route would be a hidden `agents.definitions.delete`.

Variant refusals (400 `invalid_request_error`, `param` set, `x-should-retry: false`) that are part of otherwise implemented rows, not accept-and-ignore:
`environment.type=openai_hosted` on `sessions.create`; environment and template `network`, `packages`, `setup_commands`, `plugins`, `skills`, `desktop`, `container_size`, `environment_template_id`; `files.type=file_id`; credential `type=environment_variable`, `mcp_oauth.refresh`, `networking.unrestricted`; agent/session/response tools other than `mcp`; `multi_agent.enabled=true`; `service_tier` outside `auto|default`; `input.tool_result`, `computer_use_approval_request_result`; `input_image`/`input_file`; Responses `conversation`, `prompt`, non-`text` `text.format`, unfillable `include`.

## IMPLEMENT-AND-LABEL rows (each response carries `x_easy_sandbox` and `X-Easy-Sandbox-Local: 1`)

1. `agents.definitions.create/retrieve/update/list/delete` - local stored spec; only MCP tools are real; update is in place; secrets write-only.
2. `agents.environments.create/retrieve/list` - a local directory binding with `type: self_hosted`; nothing is provisioned or isolated.
3. `agents.environments.files.create/list` - a write and list through the files `PathScope` machinery under the workspace; no overwrite; no `file_id`.
4. `agents.environments.templates.create/retrieve/update/list/delete` - reduced to `{name, env, files}`; not a hosted template.
5. `agents.sessions.create/retrieve/update/list/delete` - local exec-effect process sessions; `AgentScope` required; owner-filtered; metadata-only update.
6. `agents.sessions.send_event` - input is queued, not steered; cancel is SIGTERM to the process group; no tool results.
7. `agents.sessions.stream_events` - live tail with an extension resume; output redaction is best effort.
8. `agents.sessions.list_items`, `turns.list`, `turns.retrieve`, `turns.list_items` - honest item types (native tools are not `mcp_call`), failed stays failed, user items echoed.
9. `agents.sessions.artifacts.list/retrieve/content/delete` - immutable snapshot copies of adapter-reported paths only; delete removes the snapshot, not the file.
10. `agents.sessions.traces.list` - empty by default; optional timing-only spans from the journal, no text or arguments.
11. `agents.sessions.subagents.list` - empty by construction because no adapter emits subagent events; says so.
12. `vaults.create/retrieve/update/list/delete` - memory-only, owner-bound, write-only; lost on restart.
13. `vaults.credentials.create/list/retrieve/update/delete` - `static_bearer` and access-token `mcp_oauth` only, injected into matching MCP servers via env carrier; visible to agent-executed code.
14. `POST /responses` (stream, background), `GET /responses/{id}`, `DELETE /responses/{id}`, `POST /responses/{id}/cancel`, `GET /responses/{id}/input_items` - a local CLI turn with only MCP tools and honest output items; exec-effect gate; never claims a tool ran that did not.
15. `GET /v1/models`, `GET /v1/models/{id}` - agent definitions and adapters labelled as local, principal-filtered, side-effect free.
