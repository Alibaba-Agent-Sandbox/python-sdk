# Agents API — Hosting Coding Agents in Easy Sandbox

> Status: **implemented** (design revised after two review rounds, see
> [agents-api-review.md](agents-api-review.md)). CLI follow-ups:
> [agents-api-cli-followups.md](agents-api-cli-followups.md).
> Chinese version: not yet translated; this English page is the current text.

Easy Sandbox gains an **agent hosting layer**: a coding agent CLI (Codex CLI,
Cursor `cursor-agent`, Claude Code, Qwen Code, or any custom command) runs
*inside* a sandbox, is configured declaratively, and is driven either through a
Python client that mirrors the OpenAI Agents SDK, or through HTTP surfaces that
mirror OpenAI's Responses API and (a documented subset of) OpenAI's Agents API
so the official `openai` Python client can talk to it.

---

## 1. What "the Agents API" is (research summary)

"OpenAI Agents API" is overloaded. The research (fetched 2026-10-12) found
**four distinct surfaces**; the design treats each differently.

| # | Surface | What it is | Our relation |
|---|---------|-----------|--------------|
| 1 | **Agents API** (beta, `/v1/agents/sessions`, header `OpenAI-Beta: agents=v1`) | A *managed Codex harness*. A **session** holds a conversation, **turns** run the agent, **items** (`message`, `reasoning`, `command_execution`, `mcp_call`, `function_call`, ...) are the saved work, **events** (`agent.session.*`, `agent.output.command_execution_output.delta`, `error`) are streamed as SSE. Execution environments: `none`, `openai_hosted`, `self_hosted` (the customer runs `codex exec-server --remote <url> --environment-id <id>` with `CODEX_API_KEY` inside their own sandbox). Inputs are events: `agent.session.input.message`, `.cancel`, `.tool_result`. | The closest conceptual match to "host a coding agent in a sandbox". We serve a **subset of this wire** (sessions/turns/items/events) from the sandbox, and we ship a small helper to connect an Easy Sandbox as a `self_hosted` environment of OpenAI's own service. |
| 2 | **Responses API** (`/v1/responses`) | Stateless-by-default model API with agentic tool use: `input`, `instructions`, `previous_response_id`, `store`, `background`, `stream`, SSE `response.*` events with `sequence_number`, `/cancel`, stream resume with `starting_after`. | The *lingua franca*: every OpenAI client and the Agents SDK can use it via `base_url`. We serve a **faithful subset** with one coding agent turn = one response. |
| 3 | **OpenAI Agents SDK** (`openai-agents-python`) | Client library: `Agent`, `Runner.run / run_sync / run_streamed`, `RunResult(.final_output, .new_items, .last_response_id)`, stream events (`RawResponsesStreamEvent`, `RunItemStreamEvent`, `AgentUpdatedStreamEvent`), `Session` memory protocol, handoffs, guardrails, tracing, MCP server classes, `SandboxAgent`, experimental `codex_tool`, custom models through `OpenAIResponsesModel(AsyncOpenAI(base_url=...))`. | We mirror **names and shapes** of `Agent`, `Runner`, `RunResult`, stream events and `Session` in `easy_sandbox.agents`, *without* depending on the package. Because surface 2 is served, the real Agents SDK also works against a sandbox via `base_url`. |
| 4 | **Assistants API** (deprecated, sunset 2026) | Threads/runs. | Out of scope (deprecated; migration guide points to Responses/Conversations). |

### Sources

OpenAI (all fetched via the `.md` variants listed in
<https://developers.openai.com/api/docs/llms.txt>):

* Agents API overview, architecture, sessions, events and items, errors,
  self-hosted environments, MCP, vaults, webhooks, observability —
  <https://developers.openai.com/api/docs/guides/agents-api/overview.md>,
  `.../architecture.md`, `.../sessions.md`, `.../sessions/events.md`,
  `.../sessions/manage.md`, `.../errors.md`,
  `.../environments/self-hosted.md`, `.../environments/providers/e2b.md`,
  `.../tools/mcp.md`, `.../tools/functions.md`, `.../tools/vaults.md`,
  `.../observability.md`.
* Wire schemas taken from the official `openai` Python SDK 3.29.0
  (`openai/types/beta/agent_session*.py`, `types/beta/agents/**`,
  `resources/beta/agents/sessions/**`, `lib/streaming/agents/_streams.py`,
  `lib/beta/agents/_result.py`). The SDK is also used as a **compatibility
  oracle in tests** (section 12).
* Responses API reference and streaming events —
  <https://platform.openai.com/docs/api-reference/responses> (create, retrieve,
  cancel, streaming events).
* Agents SDK — <https://openai.github.io/openai-agents-python/> (running agents,
  streaming, sessions, tools, MCP, sandbox agents) and the experimental
  `codex_tool` extension in `openai/openai-agents-python`.
* Codex non-interactive mode and JSONL event processor —
  `openai/codex` (`codex-rs/exec`, `event_processor_with_json_output`),
  <https://developers.openai.com/codex/> (advanced configuration, CLI reference).

Coding agents:

* Claude Code headless / Agent SDK —
  <https://code.claude.com/docs/en/headless> (`claude -p`, `--output-format
  stream-json`, `--include-partial-messages`, `--resume`, `--mcp-config`,
  `--permission-mode`, `--bare`, `--append-system-prompt`), and the Agent SDK
  reference.
* Qwen Code headless mode —
  <https://qwenlm.github.io/qwen-code-docs/en/users/features/headless/>
  (`--prompt`, `--output-format stream-json`, `--include-partial-messages`,
  `--resume`, `--append-system-prompt`).
* Cursor CLI headless (`cursor-agent -p --output-format stream-json`,
  `--stream-partial-output`, `--force`, `--resume`, `CURSOR_API_KEY`) —
  <https://cursor.com/docs/cli/headless>. *Not re-verified against a live
  binary in this environment* (see open questions in the review doc).

---

## 2. Scope decisions

### In scope

1. **Runtime adapters** (server side): `codex`, `claude-code`, `cursor`,
   `qwen-code`, and generic `command`; third-party adapters through a plugin
   interface.
2. **Hosted agent runtime** (`easy_sandbox.server.agents`), a new capability
   group `agents` of the sandbox HTTP server. **Disabled by default.** It
   spawns agent CLIs per turn, keeps sessions, normalises their output to a
   common event model, enforces limits, redacts secrets.
3. **Two HTTP wires** over that runtime:
   * **Responses wire** — `POST /v1/responses` (+ `GET`, `DELETE`, `/cancel`,
     `input_items`, `GET /v1/models`) with streaming SSE.
   * **Agents wire (subset)** — `/v1/agents/sessions` (create, retrieve, list,
     delete), `/events` (post inputs, stream events), `/turns`, `/items`.
4. **Python client** `easy_sandbox.agents`: `Agent`/`AgentConfig`, `Runner`,
   `RunResult`, stream events, `Session`, declarative `agent.yaml`,
   `AgentHost` (bootstrap + connection), one-liner `sandbox.agents.run(...)`.
5. **OpenAI self-hosted environment helper**: run
   `codex exec-server --remote … --environment-id …` in an Easy Sandbox so the
   *OpenAI-hosted* Agents API can use it.
6. Docs (en/zh), examples, offline tests with fake agent binaries.

### Out of scope (and why)

| Item | Reason |
|------|--------|
| Vaults, webhooks, traces, artifacts, subagents, `computer_use`, `openai_hosted` environments of the Agents wire | Not meaningful for a self-contained sandbox; return 404/400 with a clear error. |
| Client-executed **function tools** (`tool_result` input, `requires_action`) | The CLIs execute their tools internally; there is no hook to pause a CLI turn and return a result. Rejected with `400 unsupported_parameter`. MCP tools are the supported extension point. |
| Hosting a *model* (`/v1/chat/completions`) | We host agents, not models; model/provider is passed through to the CLI. |
| Mid-turn steering | CLIs are one-shot processes per turn; extra input is **queued** (the Agents API also has a `queued` turn status). Documented deviation. |
| Persisting full event history across server restarts | Only session records, native resume ids and final items are persisted (no secrets). |
| Memory limits via rlimits | `RLIMIT_AS` breaks Node/V8; use sandbox sizing. We ship wall-clock, idle, output-size and CPU-seconds limits. |

### Why the server hosts the adapters (single source of truth)

Alternative considered: the client would drive CLIs through
`sandbox.commands.stream` and parse output locally. Rejected: (a) the
parser/adapter logic would have to exist twice if we also want an in-sandbox
HTTP surface; (b) the `openai` client and non-Python callers could not use it;
(c) sessions would die with the client. Instead: **adapters live only in
`easy-sandbox-server`**; the Python client is a thin HTTP client plus bootstrap.
Server-sdk stays stdlib-only (YAML is optional there; JSON is the wire format).

---

## 3. Architecture

```
 your code ── easy_sandbox.agents (Agent / Runner / Session) ─┐
 openai.OpenAI(base_url=…/v1) ───────────────────────────────┤  HTTPS + X-Access-Token / Bearer
 openai-agents (OpenAIResponsesModel) ───────────────────────┘
                                                              ▼
 ┌─────────────────────────── sandbox ──────────────────────────────────┐
 │ SandboxServer  (group "agents" enabled)                               │
 │  /v1/responses   /v1/agents/sessions/**   /v1/models   /agents/**     │
 │        │ wires: responses_wire.py / sessions_wire.py (pure mappers)   │
 │        ▼                                                              │
 │  AgentRuntime ── SessionStore ── Turn worker threads                  │
 │        │ Invocation(argv, env, stdin, cwd, files)                     │
 │        ▼                                                              │
 │  AgentAdapter (codex | claude-code | cursor | qwen-code | command | ext)│
 │        │ subprocess (own process group, allowlisted env)              │
 │        ▼  JSONL on stdout ──► adapter parser ──► RuntimeEvent         │
 └──────────────────────────────────────────────────────────────────────┘
```

Layering (respects `AGENTS.md`): `easy_sandbox.server.agents` imports only the
stdlib and `easy_sandbox.server.{router,types}`; `easy_sandbox.agents` (client)
never imports `easy_sandbox.server`.

### Enabling the group

`CapabilityGroup.AGENTS = "agents"` is added to the default-disabled set (like
`dev_tools`, `browser`). Ways to enable:

* `EBX_SERVER_ENABLED_GROUPS=agents` (new generic env var read by
  `SandboxServer`, mirror of `EBX_SERVER_DISABLED_GROUPS`);
* `python -m easy_sandbox.server.agents serve --port 9100` (starts a dedicated
  server instance with the group enabled — what the client bootstrap uses so it
  never has to touch a template's existing server);
* programmatic: `default_table().enable_group(CapabilityGroup.AGENTS)`.

With the group disabled all `/v1/responses`, `/v1/agents/**`, `/agents/**`
routes answer `404 … is disabled` (existing dispatcher behaviour). No other
default behaviour changes.

### Authentication

Existing routes keep `X-Access-Token` only. For routes of group `agents`, the
server **additionally accepts `Authorization: Bearer <token>`** (same token,
constant-time compare), because the official `openai` client can only send
`Authorization`. With no token configured the server is open (existing local
mode). Bootstrap always sets a random token on the dedicated instance.

---

## 4. Agent configuration

One schema, three spellings: Python, YAML/JSON file, HTTP JSON.

```yaml
# agent.yaml
name: reviewer                     # unique id on the host; used as the OpenAI "model"
runtime: codex                     # codex | claude-code | cursor | qwen-code | command | <plugin>
model: gpt-5-codex                 # passed to the CLI (optional → CLI default)
instructions: |                    # system-level instructions
  You are a careful code reviewer.
provider:                          # model endpoint for the CLI
  base_url: https://llm.example.com/v1
  api_key: ${OPENAI_API_KEY}       # resolved on the *client*; ends up in memory only
  wire_api: responses              # codex only: responses | chat
workspace:
  path: /workspace/repo            # cwd of the agent (default /workspace)
  git: {url: https://github.com/o/r.git, ref: main, token: ${GITHUB_TOKEN}}
  upload: ./                       # client-side directory to upload (skips .git, node_modules, .env …)
env: {LOG_LEVEL: debug}            # non-secret child env
secrets: {NPM_TOKEN: ${NPM_TOKEN}} # secret child env: never logged, never returned
mcp_servers:
  docs:  {url: https://mcp.example.com/mcp, headers: {Authorization: "Bearer ${DOCS_TOKEN}"}}
  files: {command: npx, args: ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]}
permissions: full_access           # read_only | workspace_write | full_access (default)
limits:
  turn_timeout_s: 1800
  idle_timeout_s: 300
  max_turns: 40                    # CLI-side agent-turn cap where supported
  max_budget_usd: 5                # claude only
  max_output_bytes: 8388608
  cpu_seconds: null
extra_args: ["--some-flag"]        # appended verbatim (escape hatch)
```

* `${VAR}` is expanded by whoever *loads* the file: the Python client expands
  from the local environment (so the file in git has no secrets); a server-side
  file (`EBX_AGENTS_CONFIG`) expands from the server's environment. An unset
  variable is a configuration error naming the variable, never an empty string.
* **Secret classification** (the only place secrets can live): `provider.api_key`,
  `workspace.git.token`, `secrets.*`, and `mcp_servers.*.headers` values that
  contain `${…}` or are marked `{secret: true}`. They are separated at load into
  a `SecretBag` that is **kept in process memory only**, is redacted from every
  event/log/error, is never serialised by any GET, and is not written to disk.
* **Permissions** are normalised and mapped per adapter:

  | normalised | meaning | codex | claude-code | qwen-code | cursor |
  |---|---|---|---|---|---|
  | `read_only` | inspect only | `sandbox_mode="read-only"` | `--permission-mode plan` | `--approval-mode plan` | `--mode ask` (no `--force`) |
  | `workspace_write` | edit + run inside workspace | `sandbox_mode="workspace-write"` | `--permission-mode acceptEdits` + `--allowedTools Read,Edit,Write,Bash` | `--approval-mode auto-edit` | `--force` |
  | `full_access` *(default)* | the sandbox is the isolation boundary | `sandbox_mode="danger-full-access"` | `--permission-mode bypassPermissions` (+ `IS_SANDBOX=1` when root) | `--approval-mode yolo` | `--force` |

  The default is `full_access` because (1) the CLI's own inner sandbox
  (Landlock/seccomp) commonly fails inside containers, and (2) the *Easy Sandbox
  VM is the security boundary*; the real risk is credential exposure, handled
  by the env allowlist (section 9).

### Python spelling

```python
from easy_sandbox.agents import Agent, Provider, Workspace, MCPServer, Limits

agent = Agent(
    name="reviewer", runtime="codex", model="gpt-5-codex",
    instructions="You are a careful code reviewer.",
    provider=Provider(base_url="https://llm.example.com/v1", api_key=os.environ["OPENAI_API_KEY"]),
    workspace=Workspace(git="https://github.com/o/r.git", ref="main"),
    mcp_servers={"docs": MCPServer(url="https://mcp.example.com/mcp", headers={"Authorization": f"Bearer {tok}"})},
    limits=Limits(turn_timeout_s=900),
)
agent = Agent.from_yaml("agent.yaml")          # needs the `declarative` extra (PyYAML)
agent = Agent.from_dict({...})
```

### Credential defaults

If `provider.api_key` is omitted the client leaves the choice to the runtime's
conventional environment: `OPENAI_API_KEY`/`CODEX_API_KEY` (codex),
`ANTHROPIC_API_KEY` (claude-code), `CURSOR_API_KEY` (cursor), `OPENAI_API_KEY`
(qwen-code), read from the **local** environment by `Agent.with_env_credentials()`
(explicit, never implicit). The server never forwards its own environment to the
child except the allowlist.

---

## 5. Runtime adapter interface

```python
class AgentAdapter(ABC):
    name: ClassVar[str]                    # "codex"
    aliases: ClassVar[tuple[str, ...]] = ()  # ("claude", "cursor-agent", ...)
    binary: ClassVar[str]                  # executable looked up on PATH
    install_steps: ClassVar[tuple[tuple[str, ...], ...]] = ()  # e.g. (("npm","i","-g","@openai/codex"),)
    capabilities: ClassVar[AdapterCapabilities]   # resume, partial_deltas, mcp, system_prompt, base_url, max_turns, budget
    prompt_transport: ClassVar[Literal["stdin", "argv"]] = "stdin"

    def validate(self, spec: AgentSpec) -> list[str]: ...        # config errors (e.g. cursor + base_url)
    def build_invocation(self, ctx: TurnContext) -> Invocation: ...
    def new_parser(self, ctx: TurnContext) -> EventParser: ...
    def health_argv(self) -> list[str]: ...                      # default [binary, "--version"]
    def credential_env(self, spec) -> dict[str, str]: ...        # provider → env mapping (secret values)
    def classify_failure(self, returncode, stderr_tail) -> RuntimeErrorInfo: ...  # → code/message
```

* `TurnContext`: `spec` (resolved, with `SecretBag`), `prompt`, `native_session_id`
  (None on first turn), `is_first_turn`, `workdir`, `turn_dir` (private temp dir
  for per-turn config files, mode 0700, deleted afterwards), `limits`.
* `Invocation`: `argv`, `env` (additions only), `stdin: bytes|None`, `cwd`,
  `files: {relpath-in-turn_dir: (bytes, mode)}`. **Never** contains secrets in
  `argv`; secrets travel only in `env` (or `stdin` for the prompt).
* `EventParser.feed(line: str) -> Iterable[ParsedEvent]` and
  `.finish(returncode) -> Iterable[ParsedEvent]`; must be tolerant: non-JSON lines
  become `log` events, unknown JSON types are ignored (forward compatibility),
  exceptions in a parser fail the turn with `internal_error`, not the server.
* `ParsedEvent` kinds (adapter-neutral): `session(id)`, `text_delta(item_id,text)`,
  `message(item_id,text)`, `reasoning(item_id,text)`,
  `tool_start(item_id,kind,name,arguments,command)`, `tool_output(item_id,delta)`,
  `tool_end(item_id,status,output,exit_code,error)`, `usage(...)`,
  `error(code,message,fatal)`, `result(ok,text,stop_reason)`.

### Third-party extension

```python
# my_pkg/adapter.py
from easy_sandbox.server.agents import AgentAdapter, register_adapter

class AiderAdapter(AgentAdapter): ...
register_adapter(AiderAdapter)
```

Discovery order: built-ins → `importlib.metadata` entry-point group
`easy_sandbox.agent_adapters` (value `module:Class`) → modules named in
`EBX_AGENTS_ADAPTER_MODULES` (comma list, imported at server start) →
`register_adapter()` at runtime. Name clashes: later registration wins only if
`override=True`, otherwise error. A *declarative* adapter needs no code:
`runtime: command` with `command: {argv: [...], parser: "text"|"jsonl-claude"|"jsonl-codex", resume_argv: [...]}`
covers most "prompt in, text/JSONL out" tools.

### Built-in adapters

| | codex | claude-code | qwen-code | cursor | command |
|---|---|---|---|---|---|
| binary / install | `codex` · `npm i -g @openai/codex` | `claude` · `npm i -g @anthropic-ai/claude-code` | `qwen` · `npm i -g @qwen-code/qwen-code` | `cursor-agent` · `curl https://cursor.com/install -fsS \| bash` | user supplied |
| invocation (turn 1) | `codex exec --json --skip-git-repo-check -C <cwd> [-m M] -c sandbox_mode=… -c approval_policy="never" [-c k=v…] -` (cwd is also the process cwd; `-C` and `-s` are *not* passed on `resume`, where only `-c` overrides are portable) | `claude -p --output-format stream-json --verbose --include-partial-messages [--model M] [--permission-mode …] [--append-system-prompt …] [--mcp-config F] [--max-turns N] [--max-budget-usd X]` | `qwen -p … --output-format stream-json --include-partial-messages [--model M] [--approval-mode …] [--append-system-prompt …]` | `cursor-agent -p --output-format stream-json --stream-partial-output [--model M] [--force] <prompt>` |
| resume | `codex exec resume <thread_id> …` | `--resume <session_id>` | `--resume <session_id>` | `--resume <chat_id>` | `resume_argv` or none |
| prompt via | stdin (`-`) | stdin | stdin | argv (no stdin support); a prompt starting with `-` is prefixed with `Task: ` so it cannot be parsed as a flag | stdin or argv |
| native session id | `thread.started.thread_id` | `system/init.session_id` / `result.session_id` | `system/session_start.session_id` | `system/init.session_id` | n/a |
| credentials | `CODEX_API_KEY` (+ custom provider block `-c model_providers.ebx={name,base_url,env_key,wire_api}` `-c model_provider="ebx"`) | `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, optional `ANTHROPIC_AUTH_TOKEN`; `CLAUDE_CODE_OAUTH_TOKEN` | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `--auth-type openai` | `CURSOR_API_KEY`; **base_url unsupported** (validation error) | none |
| MCP | `-c mcp_servers.<n>.command/args/url/bearer_token_env_var/env_http_headers` | `--mcp-config <turn_dir>/mcp.json` with `${VAR}` placeholders | `<workdir>/.qwen/settings.json` `mcpServers` (placeholders) — experimental | `<workdir>/.cursor/mcp.json` (`${env:VAR}` placeholders) — experimental | n/a |
| system prompt | preamble on first turn | `--append-system-prompt` | `--append-system-prompt` | preamble on first turn | preamble |
| exit semantics | 0 ok | 0 ok, `result.is_error` | 0 ok, 53 turn limit, 55 budget, 130 interrupted | 0 ok | 0 ok |

*Qwen/Cursor MCP note*: those CLIs have no per-invocation MCP flag, so the
adapter writes a **project-scoped** config file each turn
(`<workdir>/.qwen/settings.json`, `<workdir>/.cursor/mcp.json`) that contains
only `${VAR}` placeholders for secrets (the values travel in the child env).
The adapter merges only the `mcpServers` key, never overwrites a file it did not
create without merging, and adds the path to `.git/info/exclude` when the
workdir is a git repo. These two paths are the least verified (no live binary
here) and are marked `experimental` in `GET /agents/runtimes`.

Codex JSONL → events: `thread.started` → `session`; `item.started/completed`
with `item.type` ∈ `agent_message` (→ `message`), `reasoning` (→ `reasoning`),
`command_execution` (→ `tool_start/tool_end kind=command`, `aggregated_output`,
`exit_code`), `mcp_tool_call` (→ `kind=mcp`, `server`,`tool`,`arguments`,
`result`/`error`), `file_change` (→ `kind=file_change`), `web_search`,
`todo_list`; `turn.completed.usage` → `usage`; `turn.failed`/`error` → `error`.
Codex has **no token deltas** in `exec --json`; messages arrive complete
(the wires synthesise a single delta, see 6.3).

Claude/Qwen stream-json: `system/init` → `session`; `stream_event` with
`content_block_delta.text_delta` → `text_delta`, `thinking_delta` → reasoning
delta; `assistant` messages with `tool_use` blocks → `tool_start`, `text` blocks
→ `message` (de-duplicated against streamed deltas by message id); `user`
messages with `tool_result` → `tool_end`; `result` → `usage` + `result`.
Cursor: `system/init`, `assistant` (partial deltas when `--stream-partial-output`,
then one consolidated duplicate that is dropped by accumulated-text comparison),
`tool_call` `started/completed` (`call_id`, `<name>ToolCall.{args,result}`),
`result`.

### Install & health

* `GET /agents/runtimes` → `[{name, installed, path, version, experimental, auth_env_present, capabilities}]`
  (runs `<binary> --version`, 10 s timeout, no network).
* `POST /agents/runtimes/{name}/install` runs `install_steps` (600 s timeout)
  and returns the redacted log tail. Enabled only when the server has
  `EBX_AGENTS_ALLOW_INSTALL=1` (bootstrap sets it) — an authenticated caller
  can already run arbitrary commands via `/shell`, but the default of an
  *agents-only* server should not be able to.
* `POST /agents/runtimes/{name}/doctor` → health + config validation for a named
  agent (no model call). `python -m easy_sandbox.server.agents doctor [name]` is
  the same locally.

---

## 6. Runtime semantics

### 6.1 Sessions, turns, items

```
Session  id=agsess_<hex>  agent=<name>  status idle|in_progress|failed
  native_session_id (resume handle)   created_at  last_active_at  metadata
  turns: Turn id=turn_<hex>  status queued|in_progress|completed|failed|cancelled
         started_at completed_at  error{code,message}  usage
         items: message | reasoning | command_execution | mcp_call | file_change
  events: ring buffer of RuntimeEvent(seq, type, turn_id, item_id, data)  (default 20 000)
```

* One active turn per session; further inputs create `queued` turns executed
  FIFO. Server-wide concurrency cap `max_concurrent_turns` (default 4) → excess
  turns stay `queued`.
* Continuity = the CLI's own resume mechanism, driven by `native_session_id`
  captured from the first turn. If a CLI loses the session (e.g. `HOME` wiped)
  the resumed turn fails with `invalid_request` + hint; no silent history
  replay (would double-bill and diverge).
* Cancel: `SIGINT` to the process group → 5 s grace → `SIGTERM` → 3 s →
  `SIGKILL`. Status `cancelled`; partial items are kept with
  `status: incomplete`.
* Retention: sessions idle > `session_ttl_s` (24 h) or beyond `max_sessions`
  (200, LRU among idle) are evicted; running sessions are never evicted.
* Persistence: `$EBX_AGENTS_STATE_DIR` (default `~/.easy-sandbox/agents`) holds
  `sessions.json` (atomic write, 0600): session records, native ids and
  completed items, **no secrets, no event history**. On start the runtime
  reloads them (turns that were in flight are marked `failed:
  internal_error "server restarted"`).

### 6.2 Process execution

`subprocess.Popen(argv, cwd, env, stdin=PIPE|DEVNULL, stdout=PIPE, stderr=PIPE,
start_new_session=True)`; one reader thread per pipe; a watchdog enforces
`turn_timeout_s`, `idle_timeout_s` (no stdout/stderr bytes) and
`max_output_bytes`; stderr kept as a redacted ring (last 16 KiB) used only for
failure classification and `error.message`. Lines longer than 4 MiB are
truncated. Exit-code/parse failures are mapped by
`adapter.classify_failure()` to the Agents-API error code set
(`authentication_error`, `rate_limit_exceeded`, `request_timeout`,
`context_length_exceeded`, `sandbox_error` (binary missing/not executable),
`invalid_request`, `internal_error`, …). Two extra codes exist on the Responses
wire only: `runtime_not_installed`, `output_limit_exceeded` (the Agents wire
maps them to `sandbox_error`).

### 6.3 Event model (neutral) and wire mapping

`RuntimeEvent` types: `turn.queued`, `turn.started`, `item.added`,
`item.text.delta`, `item.reasoning.delta`, `item.output.delta`, `item.done`,
`usage`, `turn.completed|failed|cancelled`, `log` (redacted, debug only).

**Responses wire** (`stream:true`, SSE `event: <type>\ndata: {…}\n\n`, every
event has `sequence_number`):

```
response.created → response.in_progress
  per item:  response.output_item.added
             [message]   response.content_part.added → response.output_text.delta* → response.output_text.done → response.content_part.done
             [reasoning] response.reasoning_summary_part.added → response.reasoning_summary_text.delta* → …done
             [tool]      (mcp_call) response.mcp_call.in_progress → response.mcp_call_arguments.done → response.mcp_call.completed|failed
             response.output_item.done
→ response.completed | response.failed | response.incomplete   (then `data: [DONE]` is NOT sent; OpenAI does not)
```

Item mapping: assistant text → `message` (`output_text`); reasoning summary →
`reasoning` (`summary`); *every* CLI tool activity → `mcp_call` with
`server_label=<runtime>` (e.g. `codex`), `name` ∈ `command_execution`,
`file_change`, `web_search`, or the real MCP tool name for MCP calls,
`arguments` (JSON string), `output`, `error`, `status`. Rationale: `mcp_call`
is a *server-executed* item, so the OpenAI clients/Agents SDK treat it as
already done and never try to execute it locally (`function_call` or
`local_shell_call` would trigger client-side execution/errors).
Codex delivers whole messages: we emit one `output_text.delta` carrying the
full text, then `done`, so delta consumers work unchanged.
`usage` → `response.usage` (`input_tokens`, `output_tokens`, `total_tokens`,
details). Unknown token info → zeros (`usage` is never `null` on completed to
satisfy typed clients).

**Agents wire** (`/v1/agents/sessions/{id}/events` SSE, `data` = event JSON
with `type` and `event_id`):

```
agent.session.created (create only) → agent.session.in_progress
→ agent.session.turn.created → agent.session.turn.in_progress
→ agent.session.turn.item.added → [content_part.added → output_text.delta* → output_text.done]
→ agent.session.turn.item.done            (message | reasoning | command_execution | mcp_call)
   agent.output.command_execution_output.delta  (streamed command output)
→ agent.session.turn.completed|failed|cancelled → agent.session.idle  (or agent.session.failed)
→ `error` events for non-terminal problems
```
The official SDK's `AgentSessionStream.get_final_result()` and
`AgentTurnResultCollector` consume exactly this (turn created → item.done
messages → turn completed → idle) and are used as an oracle.

### 6.4 HTTP endpoints

All under group `agents`. JSON errors on `/v1/**` use the OpenAI envelope
`{"error": {"message", "type", "param", "code"}}`; native `/agents/**` routes
use the existing Easy Sandbox `{"error", "type"}` shape.

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/models`, `/v1/models/{id}` | registered agents as `model` objects (`owned_by: "easy-sandbox"`) |
| POST | `/v1/responses` | run one turn (stream or not, `background` supported) |
| GET | `/v1/responses/{id}` | retrieve; `?stream=true&starting_after=N` replays/continues SSE |
| DELETE | `/v1/responses/{id}` | forget response (and its turn) |
| POST | `/v1/responses/{id}/cancel` | cancel a running/background response |
| GET | `/v1/responses/{id}/input_items` | the prompt items of the turn |
| POST | `/v1/agents/sessions` | create session; optional `input` (+ `stream`) |
| GET | `/v1/agents/sessions` · `/{id}` | list (`limit`, `after`, `order`) · retrieve |
| DELETE | `/v1/agents/sessions/{id}` | delete (kills active turn) |
| POST | `/v1/agents/sessions/{id}/events` | `{"events":[{type:"agent.session.input.message",input:[…]} \| {type:"agent.session.input.cancel"}]}` |
| GET | `/v1/agents/sessions/{id}/events` | SSE stream (`Last-Event-ID`/`?after=` resume) |
| GET | `/v1/agents/sessions/{id}/turns` · `/{turn_id}` | turns |
| GET | `/v1/agents/sessions/{id}/items` · `/turns/{turn_id}/items` | items |
| GET | `/agents/runtimes` · POST `/agents/runtimes/{name}/install` · `/doctor` | adapters / install / health |
| GET PUT DELETE | `/agents/definitions[/{name}]` | register agent definitions (secrets are write-only) |
| GET | `/agents/health` | runtime summary (no secrets) |

#### `/v1/responses` request handling

* `model` → agent name (registered definition), else an adapter name/alias
  (creates an ephemeral default agent for that runtime), else
  `404 model_not_found`.
* `input` string | list of message items. The **last user message** is the
  prompt; earlier `developer`/`system` messages are prefixed as extra
  instructions; `input_image`/`input_file` parts → `400 unsupported_parameter`.
* `instructions`: appended to the agent's instructions for this turn.
* `previous_response_id` → continue that response's session. It must be the
  session's latest turn, otherwise `400 previous_response_not_latest`
  (no branching; documented deviation). Unknown id → `404`.
* `stream`, `background`, `metadata`, `user`, `store` (`false` ⇒ response and
  turn deleted when finished; session retained for continuity), `service_tier`,
  `include`: accepted.
* `tools`: only `{"type":"mcp","server_label","server_url","headers","allowed_tools"}`
  (→ per-turn MCP passthrough; `headers` treated as secrets). Anything else
  (`function`, `file_search`, `web_search`, `computer`, `code_interpreter`…) →
  `400 unsupported_parameter`; `tool_choice` `auto`/`none` accepted, others 400.
* `text.format` other than `text`, `conversation`, `prompt`, `reasoning`
  (accepted, mapped to codex `model_reasoning_effort` when set; ignored
  elsewhere) — `json_schema` formats and `conversation` → 400.
* Sampling params (`temperature`, `top_p`, `max_output_tokens`, `truncation`,
  `parallel_tool_calls`, …) are **accepted and ignored**; ignored names are
  returned in response header `X-Easy-Sandbox-Ignored-Params`.
* Response object: all fields the official `openai.types.responses.Response`
  model requires (`id, created_at, model, object, output, parallel_tool_calls,
  tool_choice, tools, status, usage, error, incomplete_details, metadata,
  instructions, temperature, top_p …`); `output_text` is computed by the client
  library from `output`.

### 6.5 Compatibility boundary (summary)

| Area | Faithful | Documented deviation |
|---|---|---|
| Responses create / retrieve / cancel / delete / stream | request fields above; object shape and event names/order/`sequence_number`; `starting_after` resume; `background` | `previous_response_id` must be latest; function tools & structured output rejected; sampling params ignored; tool activity is `mcp_call` items; codex has no token deltas; `store` semantics limited to this server's memory/state dir |
| Responses `GET /models` | list/retrieve | ids are agent names |
| Agents sessions (subset) | create/retrieve/list/delete, input.message, input.cancel, events SSE, turns, items, status machine, error codes, pagination envelope, `OpenAI-Beta` header tolerated | only `self_hosted`-shaped environment; no vaults/artifacts/subagents/traces/webhooks/tool_result/requires_action; `agent.model` selects a model *within* the registered agent's runtime; steering → queued |
| Agents SDK (Python client) | `Agent`, `Runner.run/run_sync/run_streamed`, `RunResult(final_output, new_items, last_response_id, raw_responses?, usage)`, stream events (`raw_response_event`, `run_item_stream_event`, `agent_updated_stream_event`), `Session` protocol | no handoffs/guardrails/tracing/function tools (runtime tools are the CLI's); `Agent.tools` takes MCP servers only; `output_type` limited to `str` and Pydantic models parsed from final text |

### 6.6 Streaming semantics, stateless callers and idempotency

* **SSE framing**: `event: <type>\ndata: <json>\n\n`, plus `id: <seq>` on
  Agents-wire events. Headers are flushed before the first event; a `: ping`
  comment is sent every 15 s so intermediaries do not drop idle streams;
  the connection closes after the terminal event of a Responses stream.
* **`GET /v1/agents/sessions/{id}/events` is a live tail**: it subscribes at the
  current sequence number (what `openai`'s `sessions.stream()` relies on: it opens
  the stream on an *idle* session first and only then posts the input), never
  closes on idle, supports `?after=<seq>` / `Last-Event-ID` replay from the ring
  buffer, and stays open until the client disconnects.
* `event_id`s are unique per session (`evt_<seq>` zero-padded) — the SDK de-duplicates
  by `event_id`.
* **Stateless callers** (the OpenAI Agents SDK sends the whole transcript every
  turn unless `previous_response_id`/`auto_previous_response_id` is used): with
  no `previous_response_id`, earlier `user`/`assistant` messages in `input` are
  rendered into a bounded (64 KiB, newest kept) "conversation so far" preface of
  the *first* prompt of a **new** session; non-message items (`mcp_call`, `reasoning`)
  are dropped. Recommended and documented usage for real continuity is
  `previous_response_id`.
* **Idempotency**: `POST …/events` honours `Idempotency-Key` per session (24 h,
  bounded to 256 keys): a repeat returns the original acknowledgement without
  queueing another turn. `POST /v1/responses` honours it the same way.
* Non-streaming `POST /v1/responses` holds the connection until the turn ends;
  because sandbox edge proxies may time out long idle requests, the Python client
  always streams internally and OpenAI-client users should prefer `stream=True`
  or `background=True` + polling for long turns.

---

## 7. Python client (`easy_sandbox.agents`)

```python
from easy_sandbox import Sandbox
from easy_sandbox.agents import Agent, Runner, Session

async with await Sandbox.create(template="base") as sb:
    agent = Agent.from_yaml("agent.yaml")

    # one-liner (a runtime name is enough: sb.agents.run("codex", "…") uses Agent.codex())
    result = await sb.agents.run(agent, "Fix the failing tests")        # bootstraps + runs
    print(result.final_output)
    print(await sb.agents.host(agent).diff())                          # git diff of the workspace

    # explicit host (reuse across calls; sessions keep conversation continuity)
    async with sb.agents.host(agent) as host:                         # AgentHost
        session = Session(host)                                        # sessions mirror Agents SDK
        r1 = await Runner.run(agent, "Add a CLI flag --json", host=host, session=session)
        r2 = await Runner.run(agent, "Now write tests for it", host=host, session=session)

        stream = Runner.run_streamed(agent, "Refactor utils.py", host=host)
        async for ev in stream.stream_events():
            if ev.type == "raw_response_event" and ev.data.type == "response.output_text.delta":
                print(ev.data.delta, end="")
        await stream.cancel()   # or stream.final_output after iteration
```

Already have a URL? `AgentHost.connect(url, token=…)` skips the bootstrap
(also works for hosts started outside the SDK, or a process on the laptop).

* Shortcuts: `Agent.codex(model=…)`, `Agent.claude_code(…)`, `Agent.cursor(…)`,
  `Agent.qwen_code(…)`, `Agent.command(argv=[…])`; `agent.validate()` runs on
  the client before any sandbox work and names the missing credential/option
  (`set OPENAI_API_KEY or Provider(api_key=…)`). `Agent.with_env_credentials()`
  copies the runtime's conventional variables from the local environment.
* `RunResultStreaming.text_stream()` yields assistant text deltas only (for the
  common "print as it types" case); `stream_events()` yields the full typed events.
* `AgentHost(on_progress=callable)` reports bootstrap steps (`installing server`,
  `installing codex`, `cloning repo`, `starting`) because the first run in a
  bare sandbox takes minutes; `sb.agents.prepare(agent)` does the bootstrap
  separately and the docs show a template `Dockerfile` that pre-bakes the server
  and CLIs.
* `Runner.run_sync` raises a clear error inside a running event loop
  (notebooks: `await Runner.run`).
* `Runner.run(agent, input, *, host|sandbox, session=None, previous_response_id=None, max_turns=None, timeout=None) -> RunResult`;
  `Runner.run_sync` (event loop helper), `Runner.run_streamed -> RunResultStreaming`
  with `stream_events()`, `cancel()`, `final_output`, `usage`.
* `RunResult`: `final_output` (str or parsed `output_type`), `new_items`
  (`MessageOutputItem`, `ReasoningItem`, `ToolCallItem`, `ToolCallOutputItem`
  dataclasses mirroring the SDK names), `last_response_id`, `response_ids`,
  `usage`, `session_id`, `turn_id`, `status`, `to_input_list()` (for SDK parity).
* Transport = HTTP to the hosted runtime using the **Responses wire** (so the
  client is itself an exerciser of the compatible surface). Sessions use
  `previous_response_id` chaining; `Session` stores the last id plus agent name
  (`Session.id`, `get_items()`, `clear_session()` match the Agents SDK
  `Session` protocol where meaningful).
* Errors: `AgentError` base; `AgentRunError(code, message, response)`,
  `AgentTimeoutError`, `AgentCancelledError`, `AgentNotInstalledError`,
  `AgentConfigError`.

### Bootstrap (`AgentHost` via `sandbox.agents.host(agent)`)

1. `commands.run("python3 -c 'import easy_sandbox.server'")`; if missing and
   `install=True` (default) → `pip install easy-sandbox-server==<client version>`
   (lockstep releases; configurable `server_package=`/`index_url`).
2. Ensure the runtime CLI: `GET /agents/runtimes` after the server is up; if not
   installed and `install=True` → `POST …/install`.
3. Write the agent definition: `PUT /agents/definitions/{name}` (secrets in the
   body, TLS to the sandbox endpoint, write-only).
4. Start: `commands.start("python3 -m easy_sandbox.server.agents serve --port 9100")`
   with env `EBX_SERVER_TOKEN=<random 32 B>`, `EBX_AGENTS_ALLOW_INSTALL=1`
   (never on argv). Wait for `/health`.
5. Workspace: `git clone` through `GIT_CONFIG_COUNT/KEY/VALUE` env
   (`http.extraHeader`) — token never on argv, never in `.git/config`; or upload
   a local directory via `sandbox.files` (same skip list as `DeployModule`:
   `.git`, `node_modules`, `.venv`, `__pycache__`, `.tox`, `.env`).
6. URL = `sandbox.network.get_url(9100)`; auth = the random bootstrap token
   (`Authorization: Bearer`) plus `sandbox.network.get_access_headers()`.

### Existing wrappers

`agent/builtin.py` and `api/deploy.py` are **unchanged**; they remain the
"run a one-shot agent via `commands.run`" path. `easy_sandbox.agents` is
documented as the richer successor (sessions, streaming, cancel).
`BUILTIN_AGENTS` names map to adapter names (`codex-agent-api`→`codex`,
`claude-code`→`claude-code`, `qwen-code-deploy`→`qwen-code`) in
`easy_sandbox.agents.runtimes.from_builtin(name)` for migration.

### OpenAI self-hosted environment helper

```python
from easy_sandbox.agents import connect_openai_environment
proc = await connect_openai_environment(sb, session.environment.remote_url,
                                        session.environment.id,
                                        executor_api_key=os.environ["OPENAI_EXECUTOR_API_KEY"])
```
Installs `@openai/codex@alpha` if needed and starts
`codex exec-server --remote <url> --environment-id <id>` with `CODEX_API_KEY`
only in the process env. Lets users drive *OpenAI's* hosted harness with an
Easy Sandbox as the executor — the complementary direction to hosting the CLI.

---

## 8. Failure modes

| Failure | Behaviour |
|---|---|
| Binary missing | turn fails `runtime_not_installed` (Agents wire: `sandbox_error`), message includes the install hint; `GET /agents/runtimes` shows it before running |
| Bad credentials / 401/403 on stderr or `result.is_error` | `authentication_error`, redacted message |
| 429 / overloaded | `rate_limit_exceeded` / `server_overloaded` |
| Timeout (wall/idle) | process group killed, `request_timeout`; partial items retained |
| Output too large | killed, `output_limit_exceeded` |
| Parser exception / malformed JSONL | line logged as `log`, tolerated; fatal parser error → `internal_error` |
| Client disconnect mid-SSE | stream handler ends; the **turn keeps running** (sessions are server-owned); re-attach via `GET …/events?after=` or `GET /v1/responses/{id}?stream=true&starting_after=` |
| Server restart | in-flight turns marked failed; sessions reload; CLI-native resume still works |
| Cancel race | idempotent; terminal state wins |
| Disk/HOME wiped | resume fails → `invalid_request` with hint |
| Prompt starts with `-` (argv transport, cursor) | prefixed with `Task: `; stdin used wherever the CLI supports it |
| Two clients post to one session | second is queued; no interleaving |

## 9. Security

1. **No secrets on argv.** Secrets only in child `env` (and for MCP/provider
   config files only `${VAR}` placeholders). Prompt via stdin where supported
   (argv for cursor, which cannot read stdin; prompts are not secrets by
   policy, and are visible to `ps` inside the sandbox).
2. **Child env allowlist**: `PATH, HOME, USER, LOGNAME, SHELL, LANG, LC_*, TERM,
   TMPDIR, TZ, SSL_CERT_FILE, SSL_CERT_DIR, REQUESTS_CA_BUNDLE, NODE_EXTRA_CA_CERTS,
   HTTP(S)_PROXY, NO_PROXY, NPM_CONFIG_*`, plus names in
   `EBX_AGENTS_PASSTHROUGH_ENV`, plus adapter credential env, plus spec
   `env`/`secrets`. `EBX_SERVER_TOKEN` and every other server variable are
   **not** inherited.
3. **Redaction**: `Redactor(secret_values)` replaces any secret value (≥ 6
   chars) and common token shapes (`sk-…`, `ghp_…`, `Bearer …`, `x-api-key`) in
   every event text, tool output, stderr tail, error message and persisted
   item. The server logs no request bodies.
4. **Write-only secrets**: `GET /agents/definitions` returns secret *names*
   (`provider.api_key: "***"`), never values; the state dir contains none.
5. **Workspace confinement** for `workspace.path`: must be absolute, no `..`,
   created if absent; the agent itself is not confined (`full_access`) —
   documented.
6. **Auth**: Bearer accepted only on `agents` routes; constant-time compare;
   bootstrap token is per host and random.
7. **Resource abuse**: body size cap (existing 10 MB), session/turn caps,
   concurrency cap, output cap, SSE per-session subscriber cap (32).
8. **State files** 0600; per-turn temp dir 0700 and removed; MCP config files
   contain placeholders only.
9. Install endpoint disabled unless `EBX_AGENTS_ALLOW_INSTALL=1`.
10. **The `agents` group is remote code execution by design** (it runs a CLI
    that runs shell commands). Therefore: default-disabled; when
    `EBX_AGENTS_LOCK_DEFINITIONS=1` the `/agents/definitions` write routes return
    403 and only definitions from `EBX_AGENTS_CONFIG` can be run (use this when a
    token is handed to a less-trusted caller); `runtime: command` and `extra_args`
    can be disabled with `EBX_AGENTS_ALLOW_COMMAND=0` (default `1`).
11. **Input validation**: agent names `[A-Za-z0-9._-]{1,64}`; adapter names from
    the registry only; `workspace.git.url` scheme ∈ {https, ssh, git} and must not
    start with `-` (clone uses `git clone -- <url>`); `workspace.path` absolute,
    no `..`; env var names `[A-Za-z_][A-Za-z0-9_]*` and not in a deny list
    (`LD_PRELOAD`, `LD_LIBRARY_PATH`, `PATH` overrides are allowed only through
    explicit `env`, never via `secrets`); MCP server names `[A-Za-z0-9_-]{1,40}`.
12. **Redaction covers encodings**: each secret is also matched URL-encoded,
    JSON-escaped and as `Bearer <secret>`; base64 or arbitrarily transformed
    copies are *not* detectable (documented residual risk).
13. **Residual risks (documented, not solved)**: with `full_access` the agent's
    own shell tool may read the CLI's environment, so a prompt-injected agent can
    exfiltrate `provider.api_key`/`secrets`. Mitigations: Codex excludes
    `*KEY*/*SECRET*/*TOKEN*` variables from its tool shells by default; prefer
    short-lived/scoped keys, a model gateway key, sandbox egress policy, and
    `workspace_write`/`read_only`. A server warning is logged when an agent is
    registered with `full_access` *and* secrets.

## 10. Backward compatibility

* New files only, apart from small localized edits: `router.py` (enum member +
  default-disabled), `app.py` (route import, `EBX_SERVER_ENABLED_GROUPS`,
  Bearer for `agents`, SSE write-failure hardening that is a no-op for healthy
  streams), `server/__init__.py` (exports), client `api/sandbox.py` (an
  `agents` cached property — import-lazy).
* No new dependency in either package (YAML stays under the existing
  `declarative` extra on the client; JSON on the server).
* Existing groups, routes, auth and tests are unchanged.

## 11. Examples (`examples/agents/`)

`01_quickstart.py` (one-liner), `02_agent_yaml.py` + `agent.yaml`,
`03_streaming.py`, `04_session_continuity.py`, `05_openai_client.py` (official
`openai` client → sandbox), `06_mcp_and_secrets.py`, `07_custom_adapter.py`,
`08_openai_self_hosted_env.py`. All run offline-safe `--dry-run`/fake mode where
possible.

## 12. Testing strategy

* **Fake agent binaries** (`tests/.../fake_agents/`): small Python scripts
  `codex`, `claude`, `qwen`, `cursor-agent` placed first on `PATH`; they read
  prompt (stdin/argv), honour resume flags with a counter file, record `argv`,
  `env` and stdin to a JSON file for assertions (**secrets must not be in argv**,
  **only allowlisted env**), and emit canned JSONL transcripts (codex JSONL,
  claude/qwen stream-json with partial deltas, cursor with the duplicate final
  message), plus failure modes (`FAKE_MODE=auth_error|hang|flood|crash|slow`).
* Unit: config parsing/validation/secret separation, redaction, each adapter's
  `build_invocation` (golden argv/env/files per permission mode, resume, MCP,
  provider), each parser against transcripts including unknown-event tolerance.
* Runtime: turn lifecycle, queueing, cancel, timeouts, idle, output cap,
  concurrency cap, persistence reload, eviction.
* Wires: pure mapper tests; **real HTTP** tests with an in-process
  `SandboxServer` on an ephemeral port: SSE parsed frame by frame (event order,
  `sequence_number` monotonic, resume with `starting_after`, client disconnect
  keeps the turn alive), auth (Bearer, X-Access-Token, none), group disabled by
  default (404), OpenAI error envelope.
* Determinism: `AgentRuntime(clock=…, id_factory=…, kill_grace_s=…)` are injectable,
  limits can be set to milliseconds, so timeout/cancel tests take well under a second.
* **Oracle**: when the official `openai` SDK is importable (`pip install openai`
  or `OPENAI_SDK_PATH=/path/to/site-packages`), tests drive the in-process server with
  `OpenAI(base_url=…).responses.create/stream`, `beta.agents.sessions.*` and the
  SDK's `sessions.stream(...).get_final_result()`; skipped otherwise.
* Client: `Runner.run/run_streamed/run_sync`, `Session`, YAML load, bootstrap
  against a fake `Sandbox` (records `commands.*` calls, asserts no secrets in
  commands), `connect_openai_environment` command construction.
* Default-behaviour regression: full existing suites + a test that
  `agents` is disabled by default and that other routes' behaviour/auth is
  unchanged.
* Integration (marked `integration`, not run here): real CLIs with real keys.
