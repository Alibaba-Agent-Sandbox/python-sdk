# Operation inventory: Agents API, Responses API and everything else the Agents guide needs

Independent inventory review (no recommendations). Prepared for the maintainer who rejected the "25 of 47, responses out" scope cut.
Nothing in application source was edited; the only file written is this report. No commits, no pushes.

## 0. How this was produced

| Item | Value |
|---|---|
| SDK walked | `openai==3.29.0`, installed into a throwaway virtualenv `/tmp/oai-inv-venv` (`python3 -m virtualenv`; not the project venv). `import openai; openai.__version__` printed `3.29.0`, `openai.__file__` = `/tmp/oai-inv-venv/lib/python3.12/site-packages/openai/__init__.py`. Pinned deps: pydantic 2.14.1, httpx2 2.13.1, anyio 4.15.1. |
| Version divergence | **None.** The imported version is exactly 3.29.0, so every count below is 3.29.0. |
| Method 1 (static) | AST walk of every sync (non-`Async*`, non-`WithRawResponse`) class under `openai/resources/beta/agents/**`, `openai/resources/responses/**` and `openai/resources/beta/responses/**`; for each public method the `self._get/_post/_delete/_get_api_list(...)` call gives verb + path template; keyword-only parameters without a default give required fields. `@overload` stubs are collapsed to the implementation `def`. |
| Method 2 (runtime) | Instantiated `OpenAI(api_key="x")` and walked the resource tree by attribute: `client.beta.agents.**` exposes **52** public callables, `client.responses.**` **10**, `client.beta.responses.**` **8**. Reconciliation in section 1.3. |
| Official docs read | `https://developers.openai.com/api/docs/guides/agents-api/{overview,architecture,quickstart,configuration,sessions,sessions/events,sessions/manage,sessions/webhooks,environments/self-hosted,environments/lifecycle,environments/files,environments/openai-hosted,environments/prewarmed,environments/security,tools/vaults,tools/functions,tools/mcp,tools/plugins,errors,observability,tracing,multi-agent}.md` (fetched as Markdown). The guides link to the per-endpoint API reference; endpoint facts were taken from the SDK source, which is generated from the same OpenAPI spec (`# File generated from our OpenAPI spec by Castiron`). |
| Paths | The SDK paths are relative to `base_url` (normally `https://api.openai.com/v1`); the tables show them with the `/v1` prefix. Every Agents request carries `OpenAI-Beta: agents=v1` (e.g. `openai/resources/beta/agents/sessions/sessions.py:341`). |

**OpenAI-cloud dependency legend** (a classification of the *official operation's documented behaviour*, my judgement, not a recommendation):

* `none`: needs nothing hosted by OpenAI beyond a signature secret or a local catalogue.
* `metadata-only`: reads or writes plain records (JSON objects, ordering, pagination, metadata, status). No code execution, no model call, no secret material is created or destroyed by the call.
* `requires OpenAI-hosted compute`: the documented behaviour needs the OpenAI-hosted harness, a hosted sandbox, model inference or hosted storage (e.g. Files API, artifact bytes). This value is used for storage too; the parenthesis says which.
* `requires OpenAI secrets service`: the call creates, rotates or destroys write-only secret material (vault credentials, confidential template values, webhook signing secrets).

## 1. SDK walk

### 1.1 Agents API (`openai.resources.beta.agents`): 47 unique HTTP operations

Counted by unique (verb, path template). Per resource (class, source file, number of operations):

| Resource | SDK class (file) | Ops |
|---|---|---|
| agents | `Agents` (`openai/resources/beta/agents/agents.py`) | 5 |
| environments | `Environments` (`.../agents/environments/environments.py`) | 3 |
| environment files | `Files` (`.../agents/environments/files.py`) | 2 HTTP (+3 non-HTTP helpers) |
| environment templates | `Templates` (`.../agents/environments/templates.py`) | 5 |
| sessions | `Sessions` (`.../agents/sessions/sessions.py`) | 5 (+1 helper `stream`) |
| session events | `Events` (`.../sessions/events.py`) | 2 |
| session items | `Items` (`.../sessions/items.py`) | 1 |
| turns | `Turns` (`.../sessions/turns/turns.py`), `Items` (`.../turns/items.py`) | 2 + 1 = 3 |
| artifacts | `Artifacts` (`.../sessions/artifacts.py`) | 4 (+1 helper `for_result`) |
| traces | `Traces` (`.../sessions/traces.py`) | 1 |
| subagents | `Subagents` (`.../subagents/subagents.py`), `Items` (`.../subagents/items.py`), `Turns` (`.../subagents/turns/turns.py`), `Items` (`.../subagents/turns/items.py`) | 2 + 1 + 2 + 1 = 6 |
| vaults | `Vaults` (`.../agents/vaults/vaults.py`) | 5 |
| vault credentials | `Credentials` (`.../agents/vaults/credentials.py`) | 5 |
| **Total** | | **47** |

There is no separate `cancel` resource under `beta.agents`: turn cancellation is the input event `agent.session.input.cancel` posted through `sessions.events.create` (`openai/types/beta/agent_session_input_param.py:59`). Likewise there is no `responses`, `input_items` or `cancel` nested under `beta.agents`; those live under `openai.resources.responses` (section 1.2).

### 1.2 Responses API (`openai.resources.responses`): 8 unique operations (7 HTTP + 1 WebSocket)

| Resource | SDK class (file) | Ops |
|---|---|---|
| responses | `Responses` (`openai/resources/responses/responses.py`): `create`, `retrieve`, `delete`, `cancel`, `compact`, plus `connect` (WebSocket) | 5 HTTP + 1 WS |
| input_items | `InputItems` (`openai/resources/responses/input_items.py:47`) | 1 |
| input_tokens | `InputTokens` (`openai/resources/responses/input_tokens.py:48`) | 1 |
| **Total** | | **8** (7 HTTP + 1 WS) |

Public methods that are **not** separate operations (they call routes already counted): `Responses.stream` (`responses.py:1109`; `POST /responses` with `stream=true`, or `GET /responses/{id}?stream=true` when given `response_id`) and `Responses.parse` (`responses.py:1334`; `POST /responses` with a structured-output `text_format`). WebSocket client events `response.create` and `response.steer` (`responses.py:5086`, `:5178`) travel over the one `connect` socket; if each client event were counted as an operation the Responses total would be 10.

`openai.resources.beta.responses` mirrors the same 8 methods (`create`, `retrieve`, `delete`, `cancel`, `compact`, `input_items.list`, `input_tokens.count`, `connect`) but appends `?beta=true` to every path (for example `openai/resources/beta/responses/responses.py:1341` posts to `"/responses?beta=true"`), and its WebSocket resource adds an `inject` event (`.../beta/responses/responses.py:5429`). It is the same route set with a query flag, so it is not counted a second time.

### 1.3 Reconciliation of the runtime walk (52 and 10)

* `beta.agents`: 52 public callables = **47 HTTP operations** + 5 helpers that issue no distinct route: `sessions.stream` (`sessions.py:82`, subscribes to `events.stream` then calls `events.create`), `artifacts.for_result` (`artifacts.py:35`, filters `artifacts.list`/`content` to one turn), `environments.files.prepare` (`files.py:36`), `prepare_directory` (`:52`), `upload` (`:72`). The three file helpers call `client.files.create(purpose="user_data")` (`openai/lib/beta/agents/_files.py:183,268`, i.e. the Files API, an operation outside both resources; counted in section 4 as O-03) and then `environments.files.create`.
* `responses`: 10 public callables = 7 HTTP + `connect` (WS) + `parse` + `stream`.

### 1.4 Per-operation detail

The master table in section 4 lists every operation with id, verb, path, SDK method, purpose and dependency. The SDK class.method, `file:line` and the required body/query fields per operation are in **Appendix A**.

## 2. The 15 routes of the `codex-agent-api` template

Source: `05-agents-api.md` section 1 (lines 38-39: "sessions 5 + events 2 + items 1 + artifacts 2 (get, delete) + agents CRUD 5") cross-checked against the template source. The template is not in `/workspace`; a checkout exists at `/tmp/awesome-templates/codex-agent-api/commands.py` (1,159 lines, git `ffc86be`). The `@table.route(...)` decorators found there number exactly 15.

| # | `commands.py` line | Verb | Path | Corresponds to official op | Difference that matters |
|---|---|---|---|---|---|
| T-01 | 654 | POST | `/v1/agents/sessions` | A-16 `sessions.create` | `environment` is not required; own object shapes (streaming = SSE from the POST) |
| T-02 | 762 | GET | `/v1/agents/sessions` | A-19 `sessions.list` | no `after`/`limit`/`order` envelope (`store.list_all()`) |
| T-03 | 775 | GET | `/v1/agents/sessions/{session_id}` | A-17 `sessions.retrieve` | |
| T-04 | 786 | POST | `/v1/agents/sessions/{session_id}` | A-18 `sessions.update` | model / instructions only |
| T-05 | 805 | DELETE | `/v1/agents/sessions/{session_id}` | A-20 `sessions.delete` | |
| T-06 | 815 | POST | `/v1/agents/sessions/{session_id}/events` | A-21 `sessions.events.create` | returns a body (official: 202, empty); handles message and cancel only |
| T-07 | 918 | GET | `/v1/agents/sessions/{session_id}/events` | A-22 `sessions.events.stream` | |
| T-08 | 973 | GET | `/v1/agents/sessions/{session_id}/items` | A-23 `sessions.items.list` | |
| T-09 | 1019 | GET | `/v1/agents/sessions/{session_id}/artifacts/{artifact_id}` | same path as A-28 `artifacts.retrieve`, but behaves like A-30 `artifacts.content` | returns the file text inside a JSON body (`object: "artifact"`, `content`); artifact id is an encoded workspace path; rejects paths outside the workspace with 403 |
| T-10 | 1059 | DELETE | `/v1/agents/sessions/{session_id}/artifacts/{artifact_id}` | A-29 `artifacts.delete` | calls `os.remove` on the real workspace file; official deletes only the artifact record |
| T-11 | 1097 | POST | `/v1/agents` | A-01 `agents.create` | |
| T-12 | 1112 | GET | `/v1/agents` | A-04 `agents.list` | |
| T-13 | 1120 | GET | `/v1/agents/{agent_id}` | A-02 `agents.retrieve` | |
| T-14 | 1131 | POST | `/v1/agents/{agent_id}` | A-03 `agents.update` | |
| T-15 | 1146 | DELETE | `/v1/agents/{agent_id}` | A-05 `agents.delete` | |

Official operations **not** present in the template: all of environments (A-06..A-15), turns (A-24..A-26), artifacts list and content (A-27, A-30), traces (A-31), subagents (A-32..A-37), vaults and credentials (A-38..A-47), all Responses ops (R-01..R-08) and all of group O. The 15 template routes map onto 14 distinct official ops (T-09 is a path-collision, not a clean match; the true official counterpart of its behaviour, A-30, is a different path). Routing hazard recorded in the template itself (`commands.py` comment above line 1097): `/v1/agents/{agent_id}` must be registered after `/v1/agents/sessions...` because `RouteTable` matches in registration order; official `GET /agents/environments` and `GET /agents/sessions` would also match `{agent_id}`.

## 3. What the current server code actually mounts

Code read: `python-sdk/server-sdk/src/easy_sandbox/server/app.py` (604 lines), `router.py`, `routes*.py` and everything under `agents/` (`__init__.py`, `config.py`, `errors.py`, `events.py`, `procenv.py`, `redact.py`, `runtime.py` 1,395 lines, `store.py`, `wire_sessions.py`, `adapters/*`). `git status` shows `agents/` is **untracked** (not committed).

**Verdict: 0 of the 15 routes are mounted on the HTTP app. All of `agents/` is helper code.**

Evidence:

* `app.py:25-31` imports exactly seven route modules: `routes`, `routes_browser`, `routes_devtools`, `routes_files`, `routes_process`, `routes_pty`, `routes_system`. There is no `routes_agents` module in the directory and no import of `easy_sandbox.server.agents` anywhere under `src/` outside `agents/` itself (`rg "server.agents|from .agents"` over `app.py`, `router.py`, `routes*.py` finds nothing).
* `rg '"/v1|/agents/' src` finds no route registration; the only hits are a docstring in `agents/adapters/base.py:38` and the group plumbing below.
* Group plumbing exists but nothing uses it: `router.py:65` declares `CapabilityGroup.AGENTS`, `router.py:69-71` makes it default-disabled, `app.py:51` / `app.py:506-511` let `EBX_SERVER_ENABLED_GROUPS` enable it, and `app.py:92-97` accepts `Authorization: Bearer` for routes whose group is `AGENTS`.
* Run-time check (`PYTHONPATH=server-sdk/src python3`, bytecode writing disabled): after `import easy_sandbox.server.app`, `default_table()` holds **47 routes** (file_ops 12, process 8, browser 8, system 6, terminal 5, core 3, dev_tools 3, commands 2) and **0 with group `agents`, 0 with a `/v1` path**. (The 47 here is the number of existing sandbox routes and is unrelated to the 47 official operations.)
* `server-sdk/tests/` has no test that references `AgentRuntime`, `/v1/agents` or `routes_agents`.

Helper coverage per template route (what exists in `agents/`, none of it reachable over HTTP):

| Template route | Mounted? | Helper in `agents/` | Missing even as a helper |
|---|---|---|---|
| T-01 POST sessions | no | `AgentRuntime.create_session` (`runtime.py:637`), `submit` (`:719`), `wire_sessions.session_object` (`wire_sessions.py:137`), `sse_frame` (`:29`) | HTTP handler |
| T-02 GET sessions | no | `AgentRuntime.list_sessions` (`runtime.py:661`) | list envelope, handler |
| T-03 GET session | no | `get_session` (`runtime.py:653`), `session_object` | handler |
| T-04 POST session (update) | no | none (`Session.metadata` exists, `runtime.py:204`, but no update method) | everything |
| T-05 DELETE session | no | `delete_session` (`runtime.py:666`) | handler |
| T-06 POST events | no | `submit` with `idempotency_key` (`runtime.py:719-728`), `cancel_active` (`:790`), `cancel_turn` (`:776`) | 202 handler, event-type dispatch |
| T-07 GET events (SSE) | no | `Session.subscribe` (`runtime.py:252`), `events_after` (`:246`), `SessionsEventMapper.map` (`wire_sessions.py:200`) | handler, heartbeats |
| T-08 GET items | no | `Item` (`runtime.py:75`), `wire_sessions.item_object` (`:64`) | list query, handler |
| T-09 GET artifact | no | none (`rg -i artifact agents/` = 0 hits) | everything |
| T-10 DELETE artifact | no | none | everything |
| T-11..T-15 agents CRUD | no | `AgentStore.put/get/require/delete/list` (`store.py:55-79`), keyed by **name**, not by `agent_*` id | `Agent` wire object, ids, handler |

Also present only as helpers: `turn_object` (`wire_sessions.py:116`) and `AgentRuntime.find_turn` (`runtime.py:686`) (would serve A-24..A-26), `list_runtimes` / `install` / `doctor` / `health` (`runtime.py:1231`, `1235`, `1272`, `1325`; the native `agents.runtimes.*` ops of the design, not official ops). No Responses wire helper exists (`wire_sessions.py` only defines session, turn and item objects).

## 4. Master table (every operation found)

Dependency values: `none`, `metadata-only`, `requires OpenAI-hosted compute`, `requires OpenAI secrets service` (legend in section 0). The "SDK method" column shows the call path on an `OpenAI` client.

### 4.1 Group A: Agents API (`client.beta.agents`)

| id | group | verb | path | SDK method | purpose (what the caller uses it for) | OpenAI-cloud dependency |
|---|---|---|---|---|---|---|
| A-01 | Agents | POST | `/v1/agents` | `client.beta.agents.create` | Create a reusable agent (model, instructions, tools, multi_agent, reasoning, text) without storing credentials. | metadata-only |
| A-02 | Agents | GET | `/v1/agents/{agent_id}` | `client.beta.agents.retrieve` | Fetch a reusable agent by ID. | metadata-only |
| A-03 | Agents | POST | `/v1/agents/{agent_id}` | `client.beta.agents.update` | Update a reusable agent (all body fields optional). | metadata-only |
| A-04 | Agents | GET | `/v1/agents` | `client.beta.agents.list` | List reusable agents in the project (cursor paging). | metadata-only |
| A-05 | Agents | DELETE | `/v1/agents/{agent_id}` | `client.beta.agents.delete` | Delete a reusable agent. | metadata-only |
| A-06 | Agents | POST | `/v1/agents/environments` | `client.beta.agents.environments.create` | Create an OpenAI-hosted environment (packages, files, setup commands, network policy, desktop) before a session, i.e. pre-warm a sandbox. | requires OpenAI-hosted compute (provisions a hosted sandbox) |
| A-07 | Agents | GET | `/v1/agents/environments/{environment_id}` | `client.beta.agents.environments.retrieve` | Read an environment's connection status and safe installed metadata. | metadata-only |
| A-08 | Agents | GET | `/v1/agents/environments` | `client.beta.agents.environments.list` | List OpenAI-hosted environments owned by the caller. | metadata-only |
| A-09 | Agents | POST | `/v1/agents/environments/{environment_id}/files` | `client.beta.agents.environments.files.create` | Stage one file (Files API id or inline base64) at an absolute `/workspace` path of a connected environment. | requires OpenAI-hosted compute (writes into a live environment; `file_id` form also reads the Files API) |
| A-10 | Agents | GET | `/v1/agents/environments/{environment_id}/files` | `client.beta.agents.environments.files.list` | List live files on a connected environment, optionally filtered by directory, opaque cursor paging. | requires OpenAI-hosted compute (reads a live environment) |
| A-11 | Agents | POST | `/v1/agents/environments/templates` | `client.beta.agents.environments.templates.create` | Save a reusable hosted-environment configuration (packages, files, setup commands, env, network, plugins, skills); confidential setup commands and env values are write-only. | requires OpenAI secrets service |
| A-12 | Agents | GET | `/v1/agents/environments/templates/{environment_template_id}` | `client.beta.agents.environments.templates.retrieve` | Read a template without its confidential values. | metadata-only |
| A-13 | Agents | POST | `/v1/agents/environments/templates/{environment_template_id}` | `client.beta.agents.environments.templates.update` | Update a template; confidential values remain write-only. | requires OpenAI secrets service |
| A-14 | Agents | GET | `/v1/agents/environments/templates` | `client.beta.agents.environments.templates.list` | List templates without confidential values. | metadata-only |
| A-15 | Agents | DELETE | `/v1/agents/environments/templates/{environment_template_id}` | `client.beta.agents.environments.templates.delete` | Delete a template and all its confidential inputs. | requires OpenAI secrets service |
| A-16 | Agents | POST | `/v1/agents/sessions` | `client.beta.agents.sessions.create` | Create a managed agent session (inline `agent` or saved `agent_id`), optionally submit first input; `stream=true` returns the event SSE from the POST. | requires OpenAI-hosted compute (managed harness + model; provisions sandbox for `openai_hosted`; `vault_ids` injects vault secrets) |
| A-17 | Agents | GET | `/v1/agents/sessions/{session_id}` | `client.beta.agents.sessions.retrieve` | Read a session's current state (status, environment, usage, required_actions). | metadata-only |
| A-18 | Agents | POST | `/v1/agents/sessions/{session_id}` | `client.beta.agents.sessions.update` | Update session metadata, model, reasoning effort or service tier. | metadata-only |
| A-19 | Agents | GET | `/v1/agents/sessions` | `client.beta.agents.sessions.list` | List sessions, optionally filtered by `agent_id`. | metadata-only |
| A-20 | Agents | DELETE | `/v1/agents/sessions/{session_id}` | `client.beta.agents.sessions.delete` | Remove a session from the public API (cancels a still-open turn and abandons unpublished outputs); returns a deletion confirmation. | metadata-only |
| A-21 | Agents | POST | `/v1/agents/sessions/{session_id}/events` | `client.beta.agents.sessions.events.create` | Send input events to a session: `input.message` (starts a turn), `input.cancel`, `input.tool_result`, `input.computer_use_approval_request_result`. | requires OpenAI-hosted compute (starts a harness/model turn) |
| A-22 | Agents | GET | `/v1/agents/sessions/{session_id}/events` | `client.beta.agents.sessions.events.stream` | Open the live SSE stream of session events (turn, item, delta, environment and status events). | metadata-only (live read of events produced elsewhere) |
| A-23 | Agents | GET | `/v1/agents/sessions/{session_id}/items` | `client.beta.agents.sessions.items.list` | List items produced by the root agent across the session, including subagent interactions. | metadata-only |
| A-24 | Agents | GET | `/v1/agents/sessions/{session_id}/turns` | `client.beta.agents.sessions.turns.list` | List turns of a session by creation time and ID. | metadata-only |
| A-25 | Agents | GET | `/v1/agents/sessions/{session_id}/turns/{turn_id}` | `client.beta.agents.sessions.turns.retrieve` | Read one turn's status, timestamps, usage and error. | metadata-only |
| A-26 | Agents | GET | `/v1/agents/sessions/{session_id}/turns/{turn_id}/items` | `client.beta.agents.sessions.turns.items.list` | List items of one root-agent turn. | metadata-only |
| A-27 | Agents | GET | `/v1/agents/sessions/{session_id}/artifacts` | `client.beta.agents.sessions.artifacts.list` | List immutable artifacts published by completed hosted session turns. | metadata-only |
| A-28 | Agents | GET | `/v1/agents/sessions/{session_id}/artifacts/{artifact_id}` | `client.beta.agents.sessions.artifacts.retrieve` | Read metadata of one durable session artifact. | metadata-only |
| A-29 | Agents | DELETE | `/v1/agents/sessions/{session_id}/artifacts/{artifact_id}` | `client.beta.agents.sessions.artifacts.delete` | Delete the artifact record (not the live environment file or the original Files API object). | metadata-only |
| A-30 | Agents | GET | `/v1/agents/sessions/{session_id}/artifacts/{artifact_id}/content` | `client.beta.agents.sessions.artifacts.content` | Download artifact bytes, including after the execution environment has expired. | requires OpenAI-hosted compute (OpenAI-hosted artifact storage; only hosted turns publish artifacts) |
| A-31 | Agents | GET | `/v1/agents/sessions/{session_id}/traces` | `client.beta.agents.sessions.traces.list` | List published root-turn traces as OTLP JSON (unpublished traces skipped). | metadata-only |
| A-32 | Agents | GET | `/v1/agents/sessions/{session_id}/subagents` | `client.beta.agents.sessions.subagents.list` | List subagents of a session, including nested and closed ones. | metadata-only |
| A-33 | Agents | GET | `/v1/agents/sessions/{session_id}/subagents/{subagent_id}` | `client.beta.agents.sessions.subagents.retrieve` | Read one subagent of the session. | metadata-only |
| A-34 | Agents | GET | `/v1/agents/sessions/{session_id}/subagents/{subagent_id}/items` | `client.beta.agents.sessions.subagents.items.list` | List a subagent's own items across all its turns. | metadata-only |
| A-35 | Agents | GET | `/v1/agents/sessions/{session_id}/subagents/{subagent_id}/turns` | `client.beta.agents.sessions.subagents.turns.list` | List all turns of a subagent, including after a resume. | metadata-only |
| A-36 | Agents | GET | `/v1/agents/sessions/{session_id}/subagents/{subagent_id}/turns/{turn_id}` | `client.beta.agents.sessions.subagents.turns.retrieve` | Read one turn of a subagent. | metadata-only |
| A-37 | Agents | GET | `/v1/agents/sessions/{session_id}/subagents/{subagent_id}/turns/{turn_id}/items` | `client.beta.agents.sessions.subagents.turns.items.list` | List items of one subagent turn. | metadata-only |
| A-38 | Agents | POST | `/v1/vaults` | `client.beta.agents.vaults.create` | Create a vault (named container of credentials) for the project. | metadata-only |
| A-39 | Agents | GET | `/v1/vaults/{vault_id}` | `client.beta.agents.vaults.retrieve` | Read a vault by ID. | metadata-only |
| A-40 | Agents | POST | `/v1/vaults/{vault_id}` | `client.beta.agents.vaults.update` | Update name or metadata of an active vault. | metadata-only |
| A-41 | Agents | GET | `/v1/vaults` | `client.beta.agents.vaults.list` | List vaults (cursor paging, status/metadata filters). | metadata-only |
| A-42 | Agents | DELETE | `/v1/vaults/{vault_id}` | `client.beta.agents.vaults.delete` | Delete a vault and all its credentials. | requires OpenAI secrets service |
| A-43 | Agents | POST | `/v1/vaults/{vault_id}/credentials` | `client.beta.agents.vaults.credentials.create` | Store a write-only credential (MCP OAuth, static bearer, environment variable) with networking scope. | requires OpenAI secrets service |
| A-44 | Agents | GET | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `client.beta.agents.vaults.credentials.retrieve` | Read credential metadata (never secret values). | metadata-only |
| A-45 | Agents | POST | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `client.beta.agents.vaults.credentials.update` | Update credential metadata or rotate its write-only secret. | requires OpenAI secrets service |
| A-46 | Agents | GET | `/v1/vaults/{vault_id}/credentials` | `client.beta.agents.vaults.credentials.list` | List a vault's credentials (no secret values). | metadata-only |
| A-47 | Agents | DELETE | `/v1/vaults/{vault_id}/credentials/{credential_id}` | `client.beta.agents.vaults.credentials.delete` | Delete a credential. | requires OpenAI secrets service |

### 4.2 Group R: Responses API (`client.responses`)

| id | group | verb | path | SDK method | purpose (what the caller uses it for) | OpenAI-cloud dependency |
|---|---|---|---|---|---|---|
| R-01 | Responses | POST | `/v1/responses` | `client.responses.create` | Generate a model response from text/image/file input, with tools, structured output, `background`, `stream`, conversation state (`previous_response_id`/`conversation`). | requires OpenAI-hosted compute (model inference, hosted tools, stored response state) |
| R-02 | Responses | GET | `/v1/responses/{response_id}` | `client.responses.retrieve` | Fetch a stored response; with `stream=true&starting_after=N` replay or continue its SSE. | metadata-only |
| R-03 | Responses | DELETE | `/v1/responses/{response_id}` | `client.responses.delete` | Delete a stored response. | metadata-only |
| R-04 | Responses | POST | `/v1/responses/{response_id}/cancel` | `client.responses.cancel` | Cancel a response; only responses created with `background=true` can be cancelled. | requires OpenAI-hosted compute (aborts an in-flight background generation) |
| R-05 | Responses | GET | `/v1/responses/{response_id}/input_items` | `client.responses.input_items.list` | List the input items of a stored response. | metadata-only |
| R-06 | Responses | POST | `/v1/responses/input_tokens` | `client.responses.input_tokens.count` | Count input tokens a request would consume, without generating. | requires OpenAI-hosted compute (model-specific tokenization; no generation) |
| R-07 | Responses | POST | `/v1/responses/compact` | `client.responses.compact` | Compact a long conversation into a compacted response object to free context window. | requires OpenAI-hosted compute (model-backed compaction) |
| R-08 | Responses | WS | `/responses (wss://<base_url>/responses)` | `client.responses.connect` | Open a persistent WebSocket; send `response.create` and `response.steer` client events, receive response stream events and steering ack/failure events. | requires OpenAI-hosted compute (model inference over a persistent socket) |

### 4.3 Group O: other operations the Agents guide or the SDK helpers rely on (outside `beta.agents` and `responses`)

| id | group | verb | path | SDK method | purpose (what the caller uses it for) | OpenAI-cloud dependency |
|---|---|---|---|---|---|---|
| O-01 | Other | GET | `/v1/models` | models.list (`client.models.list`) | List models the key can use. The Agents guides never call it; the design (05 sec. 4, line 128) adds it as a non-official convenience. | metadata-only |
| O-02 | Other | GET | `/v1/models/{model}` | models.retrieve (`client.models.retrieve`) | Read one model object. Present only in the older design (`agents-api.md:471`); dropped silently from 05. | metadata-only |
| O-03 | Other | POST | `/v1/files` | files.create (`client.files.create(purpose="user_data")`) | Upload a file whose ID is then used as `{type:"file_id"}` in `environment.files` or `environments.files.create`; the SDK helpers `environments.files.prepare/upload` call it. Agents API validates `file_id`s through it (guide `errors`, `files_api_rate_limit_exceeded`). | requires OpenAI-hosted compute (Files API storage) |
| O-04 | Other | (unpublished) | Environment registration at `https://api.openai.com` (environment id + environment key) | none in SDK (guide `environments/self-hosted`, "Network access") | `codex exec-server` registers the self-hosted executor with the API using `session.environment.id` and a restricted environment key. | requires OpenAI-hosted compute (the hosted harness is the other end) |
| O-05 | Other | WS (unpublished) | `session.environment.remote_url` (`wss://codex-cloud-environments.chatgpt.com`) | none in SDK (guide `environments/self-hosted`) | Outbound executor channel over which the harness sends shell/file/MCP commands and the executor returns results; reconnects on drop. | requires OpenAI-hosted compute (the hosted harness is the other end) |
| O-06 | Other | POST (outbound) | `<caller webhook url>` (e.g. `/webhooks/openai`) | `client.webhooks.verify_signature` / `unwrap` (caller side) | Signed delivery of session/environment lifecycle events (`agent.session.created|in_progress|idle|failed|action_required`, `agent.environment.ready|failed|expired|suspended`); handlers re-read the session. Used for webhook-managed sandboxes. | none (HMAC signature with the endpoint secret; no hosted compute) |
| O-07 | Other | POST | `/webhook_endpoints` | webhooks.create | Register a webhook endpoint (URL + event types, incl. Agents events); guide `sessions/webhooks` points to the shared webhook setup page. | requires OpenAI secrets service (returns a signing secret once) |
| O-08 | Other | GET | `/webhook_endpoints/{webhook_endpoint_id}` | webhooks.retrieve | Read a webhook endpoint. | metadata-only |
| O-09 | Other | POST | `/webhook_endpoints/{webhook_endpoint_id}` | webhooks.update | Change URL, name or subscribed events of an endpoint. | metadata-only |
| O-10 | Other | GET | `/webhook_endpoints` | webhooks.list | List webhook endpoints. | metadata-only |
| O-11 | Other | DELETE | `/webhook_endpoints/{webhook_endpoint_id}` | webhooks.delete | Delete a webhook endpoint. | metadata-only |
| O-12 | Other | POST | `/webhook_endpoints/{webhook_endpoint_id}/rotate_secret` | webhooks.rotate_secret | Rotate an endpoint's signing secret (optionally keep the old one valid 24 h). | requires OpenAI secrets service |
| O-13 | Other | POST | `/webhook_endpoints/{webhook_endpoint_id}/test` | webhooks.test | Send a test event of a chosen type to the endpoint. | metadata-only |
| O-14 | Other | GET | `/webhook_event_types` | webhooks.event_types.list | List webhook event types visible to the project. | metadata-only |

Why each O row is there:

* **O-01, O-02 (models)**: not required by any Agents guide page (`rg -i "/models"` over the 22 fetched guides finds nothing). O-01 is in the previous design as a non-official convenience (`05-agents-api.md:79,128`); O-02 only in the older `agents-api.md:471`.
* **O-03 (Files API)**: required for the `{type:"file_id"}` form of `environment.files` and `environments.files.create` (guide `environments/files`, "Use `type: \"file_id\"` with a `file_id` from the Files API") and by the SDK helpers `environments.files.prepare/upload`. The `inline` form avoids it.
* **O-04, O-05 (executor registration and channel)**: required by the guide for `environment.type = "self_hosted"` (`environments/self-hosted`, "How the connection works": the executor "registers with the API using an environment ID and a restricted API key. It then connects over WebSocket"). Neither is exposed by the SDK and no wire format is published; they are listed because the guide makes them part of the self-hosted flow and the session object carries `environment.id` and `environment.remote_url`.
* **O-06 (webhook delivery)**: the guide's webhook-managed lifecycle (`sessions/webhooks`, `environments/lifecycle`) depends on signed outbound deliveries; this is the only row that is a server-initiated call.
* **O-07..O-14 (webhook endpoint management)**: `openai.resources.webhooks` in 3.29.0. The Agents guide only says "follow the shared webhook setup guide to create an endpoint"; endpoint management is therefore guide-adjacent rather than guide-mandatory (it can also be done in the dashboard).

## 5. Counts

| Group | Count | Counted from |
|---|---|---|
| Agents API (A-01..A-47) | **47** | `openai/resources/beta/agents/**`: agents 5 (`agents.py:85,173,213,304,362`), environments 3 (`environments.py:68,120,160`), environment files 2 (`files.py:186,225`), templates 5 (`templates.py:49,135,180,271,329`), sessions 5 (`sessions.py:327,382,422,478,541`), events 2 (`events.py:44,95`), items 1 (`items.py:44`), turns 3 (`turns/turns.py:55,99`, `turns/items.py:44`), artifacts 4 (`artifacts.py:58,103,168,213`), traces 1 (`traces.py:43`), subagents 6 (`subagents/subagents.py:67,112`, `subagents/items.py:44`, `subagents/turns/turns.py:55,106`, `subagents/turns/items.py:44`), vaults 5 (`vaults.py:58,110,150,206,276`), credentials 5 (`credentials.py:52,112,157,216,289`) |
| Responses API (R-01..R-08) | **8** (7 HTTP + 1 WebSocket) | `openai/resources/responses/responses.py:1013` (create), `:1644` (retrieve), `:1684` (delete), `:1722` (cancel), `:1762` (compact), `:1986` (connect); `input_items.py:47`; `input_tokens.py:48` |
| Other (O-01..O-14) | **14** | models 2 (`openai/resources/models.py:43,81`), Files API 1 (`openai/lib/beta/agents/_files.py:183,268`), executor registration + channel 2 (guide `environments/self-hosted`, no SDK), webhook delivery 1 (guide `sessions/webhooks`, `openai/resources/webhooks/webhooks.py:505`), webhook endpoint management 8 (`openai/resources/webhooks/webhooks.py:70,151,190,277,325,364,413`, `event_types.py:38`) |
| **Grand total** | **69** | 47 + 8 + 14 |

Sub-totals a reader may want instead of 69: SDK-callable HTTP operations only = 47 + 7 + (2 models + 1 files + 8 webhooks) = 65; 47 + 8 = 55 for the two named resources alone.

Sensitivity of the counts to counting conventions (stated, not recommended):

| Convention | Effect |
|---|---|
| Count WebSocket client events (`response.create`, `response.steer`) as operations | Responses 8 becomes 10 |
| Count `beta.responses` (`?beta=true`) as a second route set | +8 routes that differ from R-01..R-08 only by a query flag (+ `inject` event) |
| Count SDK helpers (`sessions.stream`, `artifacts.for_result`, `files.prepare/prepare_directory/upload`, `Responses.stream`, `Responses.parse`) | +7 callables, 0 new routes |
| Drop O-02 (old-design-only) and O-07..O-14 (guide-adjacent) | Other 14 becomes 5 and the grand total 60 |

Dependency tally of the 69 rows (by the legend in section 0):

| Dependency | Agents | Responses | Other | Total |
|---|---|---|---|---|
| none | 0 | 0 | 1 | 1 |
| metadata-only | 34 | 3 | 8 | 45 |
| requires OpenAI-hosted compute | 6 | 5 | 3 | 14 |
| requires OpenAI secrets service | 7 | 0 | 2 | 9 |
| **Total** | 47 | 8 | 14 | 69 |

## 6. Operations the previous design's "47" did not count

The previous design (`05-agents-api.md` sections 1 and 4) counts the 47 operations of `beta.agents`. That count is correct: the 47 above match, one for one, `OFFICIAL_47` in `spikes/ebxp/catalog.py:80-117`. Everything below is outside that 47:

* **Responses**: the design names only `POST /v1/responses` plus `GET`, `DELETE`, `/cancel` and `/input_items` (`05-agents-api.md:59,128`; five routes). It never mentions **R-06 `POST /responses/input_tokens`**, **R-07 `POST /responses/compact`** or **R-08 the `/responses` WebSocket** (`rg -i "compact|input_tokens"` over the design set finds only unrelated token-usage fields).
* **Other**: **O-03 `POST /v1/files`** (needed for `file_id` environment files and the SDK file helpers), **O-04/O-05 the self-hosted executor registration and channel**, **O-06 outbound webhook delivery**, **O-07..O-14 webhook endpoint management**, and **O-02 `GET /v1/models/{model}`** (present in the older `agents-api.md:471`, absent from 05). Only O-01 `GET /v1/models` was mentioned (as "supported although not among the 47").
* The design also invents native, non-official operations (`agents.runtimes.list/doctor`, per-adapter `run`/`install`/`sessions.*`, `/agents/definitions`, `/agents/health`; `05-agents-api.md:79-90`, `agents-api.md:484-486`). They are design-native, are not in any official count, and are not included in the 69.

## 7. Other facts noted while counting (not counted as operations)

* Auth scopes named in the guide (`environments/self-hosted`, "Authentication"): `api.agents.read`, `api.agents.write`, `api.responses.write` (model inference), `api.vaults.read`, `api.vaults.write`; the executor uses a separate environment key created in the dashboard (dashboard-only, no API).
* Dashboard-only features referenced by the guides (tracing UI, environment keys, webhook setup UI) have no SDK route.
* The SDK's `sessions.create` accepts `environment.type` of `none`, `openai_hosted` (`EnvironmentParamOpenAIHosted`) and `self_hosted` (`EnvironmentParamSelfHosted`, requires `workspace_directory`) (`openai/types/beta/environment_param.py`), while `environments.create` accepts only `openai_hosted` in its type hints (`openai/types/beta/agents/environment_create_params.py:79`).
* Throwaway-venv housekeeping: my first attempt used `python3 -m venv /tmp/oai-venv`, a path where an earlier throwaway virtualenv already existed; it failed on `ensurepip` but rewrote that directory's `pyvenv.cfg` (the venv still imports `openai 3.29.0`). All results here come from the separate fresh `/tmp/oai-inv-venv`.

## Appendix A: SDK source and required fields per operation

SDK paths are relative to the installed package directory `/tmp/oai-inv-venv/lib/python3.12/site-packages/`; the line is the implementation `def` (not an `@overload` stub). "Required" lists what the SDK source makes required (keyword-only parameters without default, `Required[...]` TypedDict keys, path parameters).

| id | SDK class.method | source | required body/query/path fields |
|---|---|---|---|
| A-01 | `Agents.create` | `openai/resources/beta/agents/agents.py:85` | body: `model` |
| A-02 | `Agents.retrieve` | `openai/resources/beta/agents/agents.py:173` | path: `agent_id` |
| A-03 | `Agents.update` | `openai/resources/beta/agents/agents.py:213` | path: `agent_id`; body: none required |
| A-04 | `Agents.list` | `openai/resources/beta/agents/agents.py:304` | query (optional): `after`, `limit`, `order` |
| A-05 | `Agents.delete` | `openai/resources/beta/agents/agents.py:362` | path: `agent_id` |
| A-06 | `Environments.create` | `openai/resources/beta/agents/environments/environments.py:68` | body: `environment` (`{type:"openai_hosted", ...}`); optional `vault_ids`; header `Idempotency-Key` |
| A-07 | `Environments.retrieve` | `openai/resources/beta/agents/environments/environments.py:120` | path: `environment_id` |
| A-08 | `Environments.list` | `openai/resources/beta/agents/environments/environments.py:160` | query (optional): `after`, `limit`, `order`, `type` |
| A-09 | `Files.create` | `openai/resources/beta/agents/environments/files.py:186` | path: `environment_id`; body: `type`=`file_id`+`file_id`+`path`, or `type`=`inline`+`data`+`path` |
| A-10 | `Files.list` | `openai/resources/beta/agents/environments/files.py:225` | path: `environment_id`; query (optional): `limit`, `order`, `page`, `path` |
| A-11 | `Templates.create` | `openai/resources/beta/agents/environments/templates.py:49` | body: none required (all optional) |
| A-12 | `Templates.retrieve` | `openai/resources/beta/agents/environments/templates.py:135` | path: `environment_template_id` |
| A-13 | `Templates.update` | `openai/resources/beta/agents/environments/templates.py:180` | path: `environment_template_id`; body: none required |
| A-14 | `Templates.list` | `openai/resources/beta/agents/environments/templates.py:271` | query (optional): `after`, `limit`, `order` |
| A-15 | `Templates.delete` | `openai/resources/beta/agents/environments/templates.py:329` | path: `environment_template_id` |
| A-16 | `Sessions.create` | `openai/resources/beta/agents/sessions/sessions.py:327` | body: `environment` (`none` / `openai_hosted` / `self_hosted`+`workspace_directory`); `agent.model` if no `agent_id`; `input` if env `none` or streaming a non-self-hosted env; with `stream=true` also `stream` |
| A-17 | `Sessions.retrieve` | `openai/resources/beta/agents/sessions/sessions.py:382` | path: `session_id` |
| A-18 | `Sessions.update` | `openai/resources/beta/agents/sessions/sessions.py:422` | path: `session_id`; body: none required |
| A-19 | `Sessions.list` | `openai/resources/beta/agents/sessions/sessions.py:478` | query (optional): `after`, `agent_id`, `limit`, `order` |
| A-20 | `Sessions.delete` | `openai/resources/beta/agents/sessions/sessions.py:541` | path: `session_id` |
| A-21 | `Events.create` | `openai/resources/beta/agents/sessions/events.py:44` | path: `session_id`; body: `events` (each: `type`; message needs `input`; tool_result needs `call_id`,`success`,`turn_id`; approval needs `request_id`,`response`); header `Idempotency-Key` |
| A-22 | `Events.stream` | `openai/resources/beta/agents/sessions/events.py:95` | path: `session_id` |
| A-23 | `Items.list` | `openai/resources/beta/agents/sessions/items.py:44` | path: `session_id`; query (optional): `after`, `limit`, `order` |
| A-24 | `Turns.list` | `openai/resources/beta/agents/sessions/turns/turns.py:99` | path: `session_id`; query (optional): `after`, `limit`, `order` |
| A-25 | `Turns.retrieve` | `openai/resources/beta/agents/sessions/turns/turns.py:55` | path: `session_id`, `turn_id` |
| A-26 | `Items.list` | `openai/resources/beta/agents/sessions/turns/items.py:44` | path: `session_id`, `turn_id`; query (optional): `after`, `limit`, `order` |
| A-27 | `Artifacts.list` | `openai/resources/beta/agents/sessions/artifacts.py:103` | path: `session_id`; query (optional): `after`, `environment_id`, `limit`, `order` |
| A-28 | `Artifacts.retrieve` | `openai/resources/beta/agents/sessions/artifacts.py:58` | path: `session_id`, `artifact_id` |
| A-29 | `Artifacts.delete` | `openai/resources/beta/agents/sessions/artifacts.py:168` | path: `session_id`, `artifact_id` |
| A-30 | `Artifacts.content` | `openai/resources/beta/agents/sessions/artifacts.py:213` | path: `session_id`, `artifact_id` |
| A-31 | `Traces.list` | `openai/resources/beta/agents/sessions/traces.py:43` | path: `session_id`; query (optional): `after`, `limit`, `order` |
| A-32 | `Subagents.list` | `openai/resources/beta/agents/sessions/subagents/subagents.py:112` | path: `session_id`; query (optional): `after`, `limit`, `order` |
| A-33 | `Subagents.retrieve` | `openai/resources/beta/agents/sessions/subagents/subagents.py:67` | path: `session_id`, `subagent_id` |
| A-34 | `Items.list` | `openai/resources/beta/agents/sessions/subagents/items.py:44` | path: `session_id`, `subagent_id`; query (optional): `after`, `limit`, `order` |
| A-35 | `Turns.list` | `openai/resources/beta/agents/sessions/subagents/turns/turns.py:106` | path: `session_id`, `subagent_id`; query (optional): `after`, `limit`, `order` |
| A-36 | `Turns.retrieve` | `openai/resources/beta/agents/sessions/subagents/turns/turns.py:55` | path: `session_id`, `subagent_id`, `turn_id` |
| A-37 | `Items.list` | `openai/resources/beta/agents/sessions/subagents/turns/items.py:44` | path: `session_id`, `subagent_id`, `turn_id`; query (optional): `after`, `limit`, `order` |
| A-38 | `Vaults.create` | `openai/resources/beta/agents/vaults/vaults.py:58` | body: none required (`name`, `metadata` optional) |
| A-39 | `Vaults.retrieve` | `openai/resources/beta/agents/vaults/vaults.py:110` | path: `vault_id` |
| A-40 | `Vaults.update` | `openai/resources/beta/agents/vaults/vaults.py:150` | path: `vault_id`; body: none required |
| A-41 | `Vaults.list` | `openai/resources/beta/agents/vaults/vaults.py:206` | query (optional): `after`, `limit`, `metadata`, `order`, `status` |
| A-42 | `Vaults.delete` | `openai/resources/beta/agents/vaults/vaults.py:276` | path: `vault_id` |
| A-43 | `Credentials.create` | `openai/resources/beta/agents/vaults/credentials.py:52` | path: `vault_id`; body: `auth`, `name` |
| A-44 | `Credentials.retrieve` | `openai/resources/beta/agents/vaults/credentials.py:112` | path: `vault_id`, `credential_id` |
| A-45 | `Credentials.update` | `openai/resources/beta/agents/vaults/credentials.py:157` | path: `vault_id`, `credential_id`; body: none required |
| A-46 | `Credentials.list` | `openai/resources/beta/agents/vaults/credentials.py:216` | path: `vault_id`; query (optional): `after`, `limit`, `metadata`, `order`, `status` |
| A-47 | `Credentials.delete` | `openai/resources/beta/agents/vaults/credentials.py:289` | path: `vault_id`, `credential_id` |
| R-01 | `Responses.create` | `openai/resources/responses/responses.py:1013` | none enforced by the SDK signature (`model` optional because `prompt` can supply it; in practice `input` or `prompt`); `stream=true` returns SSE |
| R-02 | `Responses.retrieve` | `openai/resources/responses/responses.py:1644` | path: `response_id`; query (optional): `include`, `include_obfuscation`, `starting_after`, `stream` |
| R-03 | `Responses.delete` | `openai/resources/responses/responses.py:1684` | path: `response_id` |
| R-04 | `Responses.cancel` | `openai/resources/responses/responses.py:1722` | path: `response_id` |
| R-05 | `InputItems.list` | `openai/resources/responses/input_items.py:47` | path: `response_id`; query (optional): `after`, `include`, `limit`, `order` |
| R-06 | `InputTokens.count` | `openai/resources/responses/input_tokens.py:48` | none required (`model`, `input`, `instructions`, `tools`, ... optional) |
| R-07 | `Responses.compact` | `openai/resources/responses/responses.py:1762` | body: `model` |
| R-08 | `Responses.connect` | `openai/resources/responses/responses.py:1986` | no handshake fields beyond auth; client events: `response.create` (same fields as create), `response.steer` (`input`, `previous_response_id`) |
| O-01 | models.list (`client.models.list`) | `openai/resources/models.py:81` | none |
| O-02 | models.retrieve (`client.models.retrieve`) | `openai/resources/models.py:43` | path: `model` |
| O-03 | files.create (`client.files.create(purpose="user_data")`) | `openai/lib/beta/agents/_files.py:183,268` | multipart `file`, `purpose` |
| O-04 | none in SDK (guide `environments/self-hosted`, "Network access") | guide only (no SDK method) | environment id, environment key (`CODEX_API_KEY`); wire format not published in the SDK or guides |
| O-05 | none in SDK (guide `environments/self-hosted`) | guide only (no SDK method) | `remote_url` used unchanged, environment id; wire format not published |
| O-06 | `client.webhooks.verify_signature` / `unwrap` (caller side) | `openai/resources/webhooks/webhooks.py:505` | payload `data` with session id, `required_action.type` (`environment_connection` / `function_call`); signature headers; 5-minute tolerance |
| O-07 | webhooks.create | `openai/resources/webhooks/webhooks.py:70` | body: `event_types`, `url` |
| O-08 | webhooks.retrieve | `openai/resources/webhooks/webhooks.py:151` | path: `webhook_endpoint_id` |
| O-09 | webhooks.update | `openai/resources/webhooks/webhooks.py:190` | path: `webhook_endpoint_id` |
| O-10 | webhooks.list | `openai/resources/webhooks/webhooks.py:277` | query (optional): cursor paging |
| O-11 | webhooks.delete | `openai/resources/webhooks/webhooks.py:325` | path: `webhook_endpoint_id` |
| O-12 | webhooks.rotate_secret | `openai/resources/webhooks/webhooks.py:364` | path: `webhook_endpoint_id`; body: none required |
| O-13 | webhooks.test | `openai/resources/webhooks/webhooks.py:413` | path: `webhook_endpoint_id`; body: `event_type` |
| O-14 | webhooks.event_types.list | `openai/resources/webhooks/event_types.py:38` | none |

Docstring sources for the one-sentence purposes: `Agents.create` ("Creates a reusable agent without storing credentials."), `Environments.create` ("Creates an OpenAI-hosted environment before creating a session."), `Sessions.create` ("Creates a managed agent session, optionally submits initial input, and returns the session or streams its events when stream is true."), `Responses.create` ("Creates a model response."), `Responses.compact` ("Compact a conversation."), `Responses.connect` ("Connect to a persistent Responses API WebSocket."), `InputTokens.count` ("Returns input token counts of the request."), and the equivalent first sentence of every other method. Where the SDK method has no docstring (`environments.files.create`), the purpose comes from the guide page `environments/files`.

