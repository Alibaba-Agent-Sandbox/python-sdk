# 05 - Agents API as first-class built-ins

> Part of [Server SDK v2](README.md). Supersedes the *naming, auth, install and policy* parts of the in-flight
> `agents-api.md`; its runtime semantics (sessions/turns/items, queue, event model, process execution) are adopted
> and re-expressed as operations. Reconciliation list: [10](10-implementation-plan.md) section 9.
> **v2.1**: re-verified against the **real `openai` 3.29.0 package** driving the spike (`spikes/agents_sdk_check.py`, 38 checks) after the independent UX/AI review (51 findings).
> Wire shapes, tiers (now **25 / 2 / 5 / 15**), op IDs, adapter selection and install behaviour changed; changes are marked **(v2.1)**.

## 1. What the official API is (counted from the real SDK)

Source of truth: the official `openai` Python SDK, version **3.29.0**, `resources/beta/agents/**` (sync classes; every
request carries `OpenAI-Beta: agents=v1`). Unique HTTP operations, counted by (verb, path):

| Resource | Ops | Paths (relative to the SDK `base_url`, normally `https://api.openai.com/v1`) |
|----------|-----|-----|
| agents | 5 | `POST /agents`, `GET /agents/{agent_id}`, `POST /agents/{agent_id}`, `GET /agents`, `DELETE /agents/{agent_id}` |
| environments | 3 | `POST /agents/environments`, `GET /agents/environments/{id}`, `GET /agents/environments` |
| environment files | 2 | `POST` / `GET /agents/environments/{id}/files` |
| environment templates | 5 | `POST /agents/environments/templates`, `GET|POST|DELETE .../templates/{id}`, `GET .../templates` |
| sessions | 5 | `POST /agents/sessions`, `GET|POST|DELETE /agents/sessions/{id}`, `GET /agents/sessions` |
| session events | 2 | `POST /agents/sessions/{id}/events` (send), `GET .../events` (SSE stream) |
| session items | 1 | `GET .../items` |
| turns | 3 | `GET .../turns`, `GET .../turns/{turn_id}`, `GET .../turns/{turn_id}/items` |
| artifacts | 4 | `GET .../artifacts`, `GET|DELETE .../artifacts/{id}`, `GET .../artifacts/{id}/content` |
| traces | 1 | `GET .../traces` |
| subagents | 6 | `GET .../subagents`, `GET .../subagents/{id}`, `.../subagents/{id}/items`, `.../turns`, `.../turns/{tid}`, `.../turns/{tid}/items` |
| vaults | 5 | `POST /vaults`, `GET|POST|DELETE /vaults/{id}`, `GET /vaults` |
| vault credentials | 5 | `POST|GET /vaults/{id}/credentials`, `GET|POST|DELETE .../credentials/{cid}` |
| **Total** | **47** | agents 5 + environments 10 + sessions 22 + vaults 10 |

Stream/object vocabulary: object types `agent`, `agent.deleted`, `agent.environment`, `agent.session`, `agent.session.turn`,
`agent.session.artifact`, `agent.session.trace`, `agent.session.subagent`; about three dozen `agent.session.*` stream event
types (`agent.session.created|in_progress|idle|failed|requires_action`, `.environment.pending|ready|failed|...`,
`.turn.created|in_progress|completed|failed|cancelled`, `.turn.item.added|done`, `.turn.output_text.delta|done`,
`.turn.reasoning_summary_text.delta|done`, `.turn.content_part.added|done`, `agent.output.command_execution_output.delta`) and
input events `agent.session.input.message|cancel|tool_result|computer_use_approval_request_result`.

The Easy Sandbox **codex-agent-api** template implements **15** of these routes
(sessions 5 + events 2 + items 1 + artifacts 2 (get, delete) + agents CRUD 5), hard-wired to the Codex CLI by a hand-written
`commands.py` with its own routing, no policy, install via `npm -g` at image build, and registration-order-dependent routing.
Its sessions do not survive replays. **(v2.1, C-9, C-17)** The template enforces `X-Access-Token` only when `EBX_SERVER_TOKEN` is set (otherwise it is open), and its `commands.py` is about 1,160 lines (not 1,400). So the
**unmodified `openai` SDK cannot use it when a token is set** (the SDK can only send `Authorization: Bearer` and adds `OpenAI-Beta: agents=v1`), and its object names and event shapes differ from the SDK's (section 9a). The v2 server must make
`OpenAI(base_url="http://<host>:9000/v1", api_key="<server token>").beta.agents.sessions.create(...)` work.

## 2. Decisions

| # | Decision |
|---|----------|
| A1 | The server **hosts adapters** (one runtime for every CLI agent), exposing the official wire shapes. Templates stop shipping their own HTTP code. |
| A2 | Every wire route resolves to a **concrete operation ID** before authorization. Generic wire ops (`agents.sessions.create`) are mapped to the official SDK methods; **adapter ops** (`agents.codex.sessions.create`) are an *additional* gate (two-level, section 3). |
| A3 | Canonical adapter names are identifiers: `codex`, `claude_code`, `qwen_code`, `cursor`, `qoder`, `command:<name>` definitions. Hyphenated names (`claude-code`) are accepted only as wire aliases. |
| A4 | **(v2.1)** Tiering of the 47 official operations (section 4): **25 implemented (tier 1), 2 reserved (environment files), 5 refused (subagent detail routes), 15 not planned**. Everything unimplemented answers an OpenAI-shaped 404 `not_found_error` with `x-should-retry: false`, never a silent 200. |
| A5 | Auth is universal (`Authorization: Bearer` wins over `X-Access-Token`, conflicts are 401; 03 section 5). `OpenAI-Beta: agents=v1` is accepted and ignored. |
| A6 | **(v2.1, C-3)** The **adapter is selected explicitly** (path `/agents/<a>/v1`, header `X-EBX-Adapter`, `model` equal to an adapter name, config `agents.default`, the only mounted adapter) and **never inferred from a real model name**; `gpt-5-codex`, `codex-mini` and any other model string pass through as the upstream LLM model. |
| A7 | The agents group is **disabled by default**. `presets.agent_host(...)` enables adapters one by one. Enabling does **not** install anything (06). |
| A8 | `llm:` (not `provider:`) names the model endpoint an agent CLI talks to. Credentials are env references, write-only over HTTP, never in policy files or audit. |
| A9 | Agent CLIs run with the server user's privileges. **(v2.1, IS-G1)** Agent session ops are **exec-effect** ops that require an explicit `AgentScope`; file/command scopes do not confine them (03 section 15.6). |
| A10 | The unmodified official SDK, taken from the real wheel, is the **contract-test oracle** (`openai==3.29.0` in an isolated venv). |
| A11 | **(v2.1)** `/v1/responses` (and `cancel`, `input_items`) is **out of 0.3.0**; the IDs `agents.<a>.responses.*` are reserved. Cancel of a turn is the input event type `agent.session.input.cancel`. |

## 3. Operation family (v2.1: rewritten, spike-verified)

**Generic ops** (wire-shaped, results filtered to what the caller may see). ID names follow the verb rule: the last segment is a verb (N-2); the official `events.create` is `send_event`.

| Op ID | Official SDK method / binding | Eff | Tier |
|-------|-------------------------------|-----|------|
| `agents.definitions.create/get/update/list/delete` | `agents.create/retrieve/update/list/delete` = `POST/GET/POST/GET/DELETE /v1/agents[/{id}]` | W / R / W / R / D | 1 |
| `agents.environments.create/get/list` | `agents.environments.create/retrieve/list` (create stores a local `self_hosted` environment) | W / R / R | 1 |
| `agents.environments.files.create/list` | reserved op IDs (T-4); `404 not_found_error` until implemented | W / R | R |
| `agents.sessions.create` | `sessions.create` (`stream=True` returns SSE from the POST) | X+N, `AgentScope` required | 1 |
| `agents.sessions.get/update/delete/list` | `sessions.retrieve/update/delete/list` | R / W / D / R | 1 |
| `agents.sessions.send_event` | `sessions.events.create` = `POST .../events`: **HTTP 202, empty body** | X+N, `AgentScope` required | 1 |
| `agents.sessions.stream_events` | `sessions.events.stream` = `GET .../events` with `Accept: text/event-stream` | R | 1 |
| `agents.sessions.list_items` | `sessions.items.list` | R | 1 |
| `agents.sessions.turns.list/get/list_items` | `sessions.turns.list/retrieve/items.list` | R | 1 |
| `agents.sessions.artifacts.list/get/content/delete` | `sessions.artifacts.*` (**tier 1**, T-1: the codex-agent-api template already serves get/delete) | R / R / R / D | 1 |
| `agents.sessions.traces.list`, `agents.sessions.subagents.list` | return an **empty list envelope** (the session has no traces or subagents; an SDK user can call these routinely, T-2) | R | 1 (empty) |
| `agents.sessions.subagents.get/list_items`, `.turns.list/get/list_items` | refused: `404 not_found_error`, `x-should-retry: false` (no subagent exists, so "not found" is the truthful answer) | R | refused |
| `agents.models.list` | `GET /v1/models` (adapters/definitions as model objects) | R | non-official |
| `agents.runtimes.list/doctor` | native `GET /agents/runtimes`, `POST /agents/runtimes/{name}/doctor` (was `agents.list`/`agents.doctor`; N-1: `list` of **runtimes**, not of definitions) | R / R+X | non-official |

**Per-adapter ops** `agents.<a>.*` (`<a>` in the registered adapter set; generated by `register_adapter`, four per adapter):

| Op ID | Binding | Eff | Flags |
|-------|---------|-----|-------|
| `agents.<a>.run` | native `POST /agents/<a>/run` (one-shot turn, no session) | X+N | `AgentScope` required |
| `agents.<a>.sessions.create` | the adapter gate for generic `agents.sessions.create` | X+N | **explicit-only**, `AgentScope` required |
| `agents.<a>.sessions.send_event` | the adapter gate for generic `agents.sessions.send_event` | X+N | `AgentScope` required |
| `agents.<a>.install` | `POST /agents/<a>/install` | N+X+A | **explicit-only**; never in a preset |

**Two-level gate (v2.1, C-3, IS-G1).** A wire call to `POST /v1/agents/sessions` runs generic `agents.sessions.create` **and then** `Server.check_also` for the adapter op
`agents.codex.sessions.create` of the selected adapter; both must be allowed (and both need an `AgentScope`). Read-type generic ops (`sessions.get`, `list_items`, ...) are
gated by the generic op plus session ownership only: they do not start a process. An operator who wants "only codex" mounts the generic ops and the codex adapter ops
and nothing else; an operator who wants "an observer" mounts the read generic ops. The read-side adapter identity needs no per-adapter op because sessions record their adapter at creation (IF-29: the
**per-adapter op family is kept at four ops** instead of the in-flight 18; the 90-op catalog the feasibility review objected to is now 20 adapter ops, and `agents.<a>.**` selector sugar plus generation keep policy and clients short).

**Static refusals are still not addressable beyond their op IDs** (they exist as ops so that policy can name them, but their handler is a fixed OpenAI-shaped body that reads no state).

### Policy examples

```python
# only codex, only for one principal, may not install; bounded concurrency; read-only agent
Policy().allow("agents.definitions.*", "agents.environments.*", "agents.sessions.**", "agents.models.list",
               ops.agents.codex.sessions.create, ops.agents.codex.sessions.send_event,
               principals=["role:dev"], limits=Limits(concurrency=2),
               agents=AgentScope(workdir="/workspace", permissions="read-only",
                                 models=["gpt-5-codex"], max_turns=20))
         .deny(ops.agents.codex.install)
# read-only observer of sessions (no process can start)
Policy().allow(ops.agents.sessions.get, ops.agents.sessions.list, ops.agents.sessions.list_items,
               ops.agents.sessions.stream_events, principals=["role:observer"])
```

## 4. Tiering of the 47 official operations (v2.1)

Counted from the real SDK: `tests/contract/official_47.json` (generated by walking `openai.resources.beta.agents`); the spike encodes the same rows in `catalog.OFFICIAL_47` and `tests_catalog.py` asserts the counts.

| Tier | Meaning | Ops | Count |
|------|---------|-----|-------|
| **1 - implemented** | usable end to end with the official SDK (`agents.create -> sessions.create -> events.create -> events.stream -> items/turns/artifacts`) | agents 5; sessions 5; events 2; items 1; turns 3; artifacts 4; traces 1 (empty list); subagents.list 1 (empty list); environments create/retrieve/list 3 | **25** |
| **Reserved** | op IDs exist (`agents.environments.files.create/list`), answer 404 `not_found_error` until implemented | environment files 2 | **2** |
| **Refused** | a session never has subagents, so the detail routes are 404 `not_found_error` + `x-should-retry: false` (not 501: the SDK retries 5xx, T-2, C-12) | subagents retrieve, list_items, turns.list, turns.get, turns.list_items | **5** |
| **Not planned** | no local equivalent; 404 `not_found_error`, documented | environment templates 5 (OpenAI-hosted; local templates are the Easy Sandbox template system), vaults 5 and vault credentials 5 | **15** |
| | | | **47** (25 + 2 + 5 + 15) |

**Vault wording (T-3).** OpenAI vaults hold **tool credentials** (MCP and bearer secrets, sandbox environment secrets), **not LLM provider keys**. Their local equivalent is therefore the server-side `llm:` configuration for the LLM key (env reference, never exposed) and `AgentScope(mcp=...)` for server-side MCP credentials; there is no `vault_ids` behaviour (sessions return `vault_ids: []`).

Also supported although not among the 47: `GET /v1/models`. **Out of 0.3.0:** `POST /v1/responses` (+ `GET/DELETE`, `/cancel`, `/input_items`; C-10, A11). Not promised: caller-executed tools: input events `agent.session.input.tool_result` and `computer_use_approval_request_result` answer `400 agents.tool_result_unsupported` with a message naming the reason (C-14); `tool_handlers=` in the SDK therefore does not work.

Status of the codex-agent-api template's 15 routes: 15/15 covered by tier 1 with the same paths (the earlier claim relied on artifacts being tier 2; they are tier 1 now, T-1).

## 5. Wire behaviour (what makes the official SDK work; verified against `openai` 3.29.0)

* **Base URL.** `base_url="http://host:9000/v1"` serves `/v1/agents/...`; `base_url=".../agents/codex/v1"` pins the adapter. The SDK sends `OpenAI-Beta: agents=v1` (accepted and ignored).
* **Errors on `/v1/**`**: `{"error": {"message", "type", "param", "code"}}`; `type` maps `invalid_request_error` (400/415/413), `authentication_error` (401), `permission_error` (403), `not_found_error` (404), `rate_limit_error` (429). Permanent errors carry
  `x-should-retry: false`, because the SDK retries 408, 409, 429 and 5xx otherwise (C-12): 404, 403, 400, 401, 501-style refusals and `idempotency.mismatch` are all non-retryable. `install.pending` is a **202**, not a 5xx (06).
* **List envelope (C-2).** `{"object": "list", "data": [...], "first_id", "last_id", "has_more"}` for every list route; query `after` (cursor id), `limit` (1-100, default 20; outside the range is 400), `order` (`asc|desc`, default `desc`). The SDK's auto-pagination terminates
  and sees every item.
* **Agent object (C-1).** Full `Agent`: `id`, `object: "agent"`, `model`, `name`, `instructions`, `tools`, `metadata`, `multi_agent: {enabled: false}`, `created_at`, ... The **session embeds the full Agent** (not just an id): fields `id`, `agent`, `created_at`, `environment` (`{type: "self_hosted", id, remote_url}`),
  `error`, `last_active_at`, `metadata`, `object: "agent.session"`, `required_actions: []`, `status`, `usage`, `vault_ids: []`. Statuses: `idle | in_progress | requires_action | failed` (C-7; `requires_action` is part of the set but never produced because tool results are unsupported).
* **Turn object.** `id`, `agent_id`, `object: "agent.session.turn"`, `session_id`, `status`, `created_at`, `started_at`, `completed_at`, `error`, `subagent_id`, `usage`. **Events** carry an `event_id`; turn events carry `turn_id` and a `turn` object (the SDK's `sessions.stream()` helper de-duplicates by `event_id`).
* **`events.create` (C-5).** `POST /v1/agents/sessions/{id}/events` returns **HTTP 202 with an empty body** (the SDK returns `None`). `Idempotency-Key` is stored with a hash of the canonical request: the same key and the same body replays the 202 without a second turn; the same key and a different body is `409 idempotency.mismatch` with `x-should-retry: false`.
* **`events.stream` (C-4, C-13).** `GET .../events` with `Accept: text/event-stream` **stays open while the session is idle**, starts at "now", delivers the events of the turn(s) that follow and closes after the post-turn `agent.session.idle` (or on `failed`/session delete). The SDK helper `sessions.stream(id, input=...)` subscribes first, then POSTs the input, and works because of this.
  `sessions.create(stream=True)` returns the SSE from the POST. Heartbeats are `: ping` comments every 15 s. **Resume is an EXTENSION**: `?after=<event_id>` replays from the journal; the official docs say streams are not resumable via `Last-Event-ID`, so the SDK never uses it and the doc no longer calls it official.
* **`environment` (C-6).** Required by the SDK on `sessions.create`: `{"type": "none"}` (needs `input`; chat-only, private empty workdir, `read-only`), `{"type": "self_hosted", "workspace_directory": "/abs"}` (must be admitted by the `AgentScope.workdir` `PathScope`),
  `{"type": "openai_hosted"}` -> `400 agents.environment_unsupported`. `agents.environments.create` accepts `openai_hosted` (the only type the SDK type hints offer for create) **or** `self_hosted` and stores a local `self_hosted` environment (documented semantic difference: nothing is hosted by OpenAI).
* **`usage`, `spend_control`, `last_active_at`, `vault_ids`, `remote_url`, `environment.id` (C-15)**: `usage` is `{input_tokens, output_tokens, total_tokens}` as far as the adapter reports it (else zeros); `last_active_at` is updated on every event; `spend_control` is accepted and ignored; `vault_ids` is `[]`; the environment carries a stable `id` and `remote_url` (the server URL).
* **Adapter selection (A6, C-3).** In order: (1) path `/agents/<a>/v1/...` (unknown adapter: 404 `not_found_error`); (2) header `X-EBX-Adapter`; (3) a `model` string equal to an adapter name or wire alias (`codex`, `claude-code`); (4) config `agents.default`; (5) exactly one adapter is mounted for the principal; (6) otherwise `400 agents.adapter_required`
  (or 404 `op.not_enabled` if none is mounted). The `<adapter>/<model>` prefix form is **dropped**: `codex-mini` and `gpt-5-codex` are real model names that pass through, which is what the template's examples and the SDK docs use.
* **Message queue** and cancel: input sent while a turn runs is queued (FIFO, `max_queue` 20); `agent.session.input.cancel` cancels the running turn (SIGTERM to the process group, SIGKILL after 5 s).
* **Lazy install surfaces as environment state and as a 202 job**, never as a blocking 10-minute request (06 section 5): first use emits `agent.session.environment.pending` (with a `job_id`), then `.ready` or `.failed`; non-streaming callers get `202` + `Retry-After` with a status resource and retry `events.create`.
* **Ownership.** Sessions, turns and artifacts belong to the creating principal; a foreign id answers like an unknown id.

## 6. Adapter protocol

```python
class AgentAdapter:                                  # easy_sandbox/server/agents/adapters/base.py
    name: ClassVar[str]                              # "codex"  (identifier grammar)
    wire_names: ClassVar[tuple[str, ...]] = ()       # ("claude-code",)
    binary: ClassVar[str]                            # executable name (resolved via the tools dir, see 06)
    manifest: ClassVar[str]                          # lazy-install manifest name
    capabilities: ClassVar[AdapterCaps]              # resume, deltas, mcp, system_prompt, base_url, models, artifacts
    def validate(self, spec: AgentSpec) -> list[str]
    def build_invocation(self, ctx: TurnContext) -> Invocation   # argv, env additions, stdin, cwd, files; NO secrets in argv
    def new_parser(self, ctx: TurnContext) -> EventParser        # feed(line) / finish(rc) -> neutral RuntimeEvents
    def credential_env(self, llm: LLMConfig) -> dict[str, str]
    def classify_failure(self, rc: int, stderr_tail: str) -> Failure   # -> agents.auth_missing / rate_limited / model_not_found / crashed
    def health_argv(self) -> list[str]
```

Declarative adapters need no Python (`agents.<name>.*` ops are generated from the definition):

```yaml
agents:
  aider:
    adapter: command
    command: ["aider", "--yes", "--message", "{prompt}"]       # argv template; {prompt} placeholder is one argv element
    prompt: argv                                                # argv | stdin
    output: {format: text}                                      # text | jsonl; jsonl takes text_path/error_path/session_path
    resume: {args: ["--restore-chat-history"], session_id_from: null}
    install: {manifest: manifests/aider.json}
    llm_env: {api_key: OPENAI_API_KEY, base_url: OPENAI_API_BASE, model: AIDER_MODEL}
```

Registration paths (in order): built-ins -> entry-point group `easy_sandbox.agent_adapters` **only for names listed in
`agents.load`** -> `agents:` declarative entries in config -> `register_adapter()` in Python. Clashes need
`override=True`.

### Built-in adapters (all lazy-installed, 06)

| Adapter | Binary | Turn invocation (prompt on stdin unless noted) | Resume | Parsed stream | Status |
|---------|--------|------------------------------------------------|--------|---------------|--------|
| `codex` | `codex` (`@openai/codex`) | `codex exec --json --skip-git-repo-check -C <cwd> [-m M] -c sandbox_mode=… -c approval_policy="never" -` | `codex exec resume <thread_id>` | JSONL `thread.started`, `item.*`, `turn.*` (no token deltas; one synthesised delta) | verified in the in-flight design against the template |
| `claude_code` (`claude-code`) | `claude` (`@anthropic-ai/claude-code`) | `claude -p --output-format stream-json --verbose [--append-system-prompt …]` | `--resume <session_id>` | stream-json (`system/init`, `stream_event`, `assistant`, `user`, `result`) | in-flight design |
| `qwen_code` (`qwen-code`) | `qwen` (`@qwen-code/qwen-code`) | like claude (`stream-json`) | `--resume` | stream-json | experimental |
| `cursor` | `cursor-agent` (version-pinned tarball from `downloads.cursor.com`, **not** `curl | bash`) | prompt in argv (prefixed with `Task: ` when it starts with `-`) | `--resume <chat_id>` | stream-json incl. `tool_call` | experimental |
| `qoder` | `qodercli` (npm package `@qoder-ai/qodercli`, bins `qoder` and `qodercli`; C-16; to be re-verified against the installed binary by the adapter owner) | declarative `command` profile: `qodercli -p {prompt}` with text/jsonl auto-detect | none until verified | text | **experimental, unverified**: no binary was available while writing this design; shipped as a declarative profile so that no unverified parser code exists |
| `command` | user | user | user | text/jsonl | stable |

## 7. LLM endpoint (`llm:`) and credentials

```yaml
agents:
  codex:
    llm:
      base_url_env: EBX_LLM_BASE_URL          # or base_url: https://gateway.example.com/v1 (a literal is fine, it is not secret)
      api_key_env:  EBX_LLM_API_KEY           # secrets are *references*; literals are rejected by check-config
      model: gpt-5-codex
      wire_api: responses                     # responses | chat (adapter-specific)
```

* Precedence for each field: request field (if the policy allows `llm_override`, default **off**) > saved definition >
  config `agents.<a>.llm` > adapter fallback env `EBX_LLM_*` > the CLI's own env (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...).
  The `EBX_LLM_*` names are the in-sandbox bridge for the sandbox-provider/credentials design (their variables stay
  `EBX_SERVER_*`/`EBX_LLM_*`; the provider design never needs to know about adapters).
* **Caller-supplied `base_url` is forbidden by default** (SSRF/credential exfiltration: it would send the API key to an
  attacker's host). `AgentScope(llm_hosts=[...])` is an allowlist if a deployment really needs it.
* Secret fields are **write-only** on `agents.definitions.*` (`***` on read), never in audit/logs/errors, never in argv
  (env or stdin only), and children get an allowlisted environment (no inherited `EBX_*`).

## 8. Permissions: what an agent may do

`AgentScope(workdir, permissions, commands=(), models=(), max_turns=None, timeout, max_output, llm_hosts, mcp, env, unconfined_ok=False)` (v2.1: `cwd` is renamed `workdir`; it is a `PathScope`-checked directory; `permissions` has **no default**; `None` is refused at admission; `"full"` needs `unconfined_ok=True`; the presets use `"read-only"`):

| `permissions` | codex | claude_code | qwen_code / cursor |
|---------------|-------|-------------|--------------------|
| `read-only` | `-c sandbox_mode=read-only` | `--permission-mode plan` (or `--allowedTools Read,Grep,Glob`) | adapter mapping or *refused* if the CLI has no read-only mode |
| `workspace-write` | `sandbox_mode=workspace-write` | `--permission-mode acceptEdits` with `--allowedTools` for edits | adapter mapping |
| `full` | `danger-full-access` (only with `unconfined_ok=True`; lint error otherwise) | `--dangerously-skip-permissions` | same |

If an adapter cannot honour the requested level it **refuses** (`policy.agent_option_denied`) rather than running
unconfined. `check-config` lint: "`agents.codex.*` allowed together with `files.*` scoped to `/workspace`: the agent
process is not confined by `PathScope`; use `AgentScope.permissions` and OS isolation."

## 9. Runtime semantics (adopted from the in-flight design)

Sessions hold an ordered list of turns; a turn = one CLI process (own process group, allowlisted env, private `turn_dir`
0700 for per-turn config files, deleted afterwards); items are the neutral event projections (`message`, `reasoning`,
`command`, `mcp`, `file_change`, `web_search`). The **event journal** is an append-only JSONL file per session under
`$EBX_SERVER_STATE_DIR` (v2.1, IS-L1: default `~/.local/state/easy-sandbox/agents` or `/var/lib/easy-sandbox/agents` for root, mode 0700, protected from every PathScope; never `/tmp`; must be writable even on read-only roots; `EBX_AGENTS_STATE_DIR` is accepted as an alias for one minor) with
size/TTL caps (`max_sessions` 50, `session_ttl` 1800 s idle, `journal_max_bytes` 32 MiB); replay = read from `seq`.
Limits: `max_concurrent_turns` (default 4), per-turn `timeout` (default 30 min), stdout line cap 1 MiB, total output cap.
On server restart in-flight turns are marked `failed` (`server.shutting_down`), sessions remain readable until TTL.

## 10. Security

0. **(v2.1)** Session creation is an exec-effect, `AgentScope`-bound, two-level-gated operation; its ids are `secrets.token_urlsafe(16)`; implicit install requires that the same principal could call `install`; the LLM key is visible to agent-executed code in 0.3.0 and `doctor`/`explain` say so (03 section 15.6).
1. Adapter selection from untrusted input cannot enumerate adapters (404 `op.not_enabled`).
2. `argv` never contains secrets or unvalidated caller text beyond the prompt element (prompt via stdin when the CLI allows;
   for argv-only CLIs the prompt is one element, prefixed if it starts with `-`).
3. MCP server definitions from callers are **off** unless `AgentScope(mcp=...)` allows names from a server-side allowlist;
   configs written into the workdir contain `${VAR}` placeholders only.
4. Per-session workdir must lie inside `AgentScope.workdir` (a `PathScope` check), canonicalised.
5. Install happens only through the manifest installer (06); `agents.<a>.install` is an explicit `admin`-effect op.
6. The journal is readable only by principals that may call `agents.sessions.stream_events/list_items` **and** own the session:
   sessions record their creating principal; other principals (even with the same op grants) get `404 agents.not_found` unless they have role `admin` or the
   statement sets `AgentScope(share_sessions=True)`. `Idempotency-Key` entries are namespaced by principal (review round 3).
7. Output redaction: known secret values (from the resolved LLM env) are scrubbed from journal text before it is stored.

## 11. Testing

* **Fake agent binaries** (`tests/fakes/fake_codex`, `fake_claude`, `fake_cursor`, ... small Python scripts that emit
  recorded JSONL transcripts, honour `--resume`, exit codes, slow outputs and crashes) put on `EBX_TOOLS_DIR` so adapters
  run end to end with no network.
* **Official-SDK oracle**: `spikes/agents_sdk_check.py` (38 checks; the same file is promoted to `tests/contract/test_openai_oracle.py`) runs in an isolated venv (`python3 -m virtualenv /tmp/oai-venv && /tmp/oai-venv/bin/pip install openai==3.29.0`; `python3 -m venv` is not available on every runner) and drives
  `OpenAI(base_url=..., api_key=...).beta.agents.{create,list,update,delete,environments.*,sessions.create|stream|retrieve|update|delete|list,sessions.events.create|stream,sessions.items.list,sessions.turns.*,sessions.artifacts.*,sessions.traces.list,sessions.subagents.*,vaults.list}`
  against the server (idle-open stream, 202, pagination, idempotency, adapter selection, two-level gate, refusals as `openai.NotFoundError`). Run it from a directory that is **not** `site-packages` (a `types` module there shadows the stdlib).
* **Policy tests**: per-adapter mounting, 404 oracle tests, principal isolation of sessions, caller `base_url` rejection.
* **Install tests**: with the fake registry (06 section 9).

## 12. Examples (v2.1: every line executed against the spike with the real `openai` package)

Codex endpoint with custom auth (replaces the `codex-agent-api` template's `commands.py`):

```yaml
# template.yaml
server:
  preset: agent-host
  root: /workspace
  agents: [codex]
  auth:
    tokens:
      - {id: app, roles: [dev], token_env: APP_API_KEY}     # must be set and >= 16 characters, or the server refuses to start
  agent:
    codex:
      llm: {base_url_env: LLM_BASE_URL, api_key_env: LLM_API_KEY, model: gpt-5-codex}
      permissions: read-only
  install: {mode: build}                                        # recommended on read-only/FC images (06)
```

```python
from openai import OpenAI

client = OpenAI(base_url="https://9000-<sandbox>.example/agents/codex/v1", api_key=APP_API_KEY)
A = client.beta.agents
agent = A.create(model="gpt-5-codex", name="coder", instructions="Be concise.")   # real model names pass through
sess = A.sessions.create(agent_id=agent.id, environment={"type": "self_hosted", "workspace_directory": "/workspace"})
with A.sessions.stream(sess.id, input="add a README") as stream:                    # subscribes first, then sends, ends after the idle
    for ev in stream:
        print(ev.event_id, ev.type)
A.sessions.events.create(sess.id, events=[{"type": "agent.session.input.message",
                                           "input": [{"role": "user", "content": [{"type": "input_text", "text": "thanks"}]}]}])   # 202, returns None
for item in A.sessions.items.list(sess.id):                                          # auto-paginates the list envelope
    print(item.role)
```

With **more than one adapter mounted**, point each client at `/agents/<adapter>/v1` or send the header `X-EBX-Adapter`; with a single adapter `base_url=".../v1"` is enough.
Parameter names are those of the official SDK 3.29.0: `agents.create(model=, instructions=, name=, tools=, metadata=)`, `sessions.create(environment=, agent_id=|agent=, input=, stream=, vault_ids=)`,
`sessions.stream(session_id, input=...)`, `sessions.events.create(session_id, events=[...], idempotency_key=...)`, `sessions.turns.retrieve(turn_id, session_id=...)`.

Multi-agent host (codex + claude_code, observers can only read): one server, per-principal rules from section 3 (`allow` the generic read ops for `role:observer`; the adapter ops only for `role:dev`).

## 13. Migration from the `codex-agent-api` template (v2.1, C-8)

The migration is **not** wire-compatible and says so: object names change (`session` -> `agent.session`; `agent.session.turn`, `agent.session.artifact`), events gain `event_id`/`turn_id`, `events.create` returns 202 with no body (the template returned a JSON object), lists use the `{object:"list", data, first_id, last_id, has_more}` envelope,
`Authorization: Bearer` is the preferred credential (`X-Access-Token` still works), and `environment` is required on `sessions.create`. Template clients that parse the old shapes must upgrade to the official SDK (a compatibility shim is explicitly **not** planned; see the cut list in 10 section 7). The migration guide (docs `guide/migrating-from-codex-agent-api.md`, WP-12) carries a
field-by-field table generated from the oracle test.
