# Independent review: user experience, AI-codegen usability, OpenAI Agents API compatibility

Reviewer stance: independent and adversarial. I did not write the design.
Scope: README decision log, docs 01-10, `reviews/`, `spikes/`.
Lenses: (A) user experience, (B) AI-codegen usability, (C) OpenAI Agents API compatibility.
Rules observed: no code edits, no branches or commits, this is the only file written, no secrets.

Method, in short:

- Re-ran the spike test suites (`tests_proto` 36/36, `tests_round4` OK, `ai_consumer` S1-S8 all pass). `tests_catalog` reports failures only because the legacy source tree it diffs against is not present in this environment. That is an environment gap, not a design defect.
- Counted the official Agents API operations from the published API reference navigation, from each per-method reference page, and from the paths in the official `openai` Python SDK (3.29.0, installed in a scratch location outside the repository).
- Wrote the 8 requested template server files using only the 09 reference card, and ran each against the spike prototype through a thin shim. The shim re-exports the spike's `api` module as `easy_sandbox.server` and raises `ImportError` for names the card promises but the spike lacks.
- Built throw-away fake servers that serve exactly what the design says it serves, and drove them with the real `openai` SDK (`client.beta.agents.*`, `client.beta.sessions.*`, `sessions.stream()`).
- Read the 15 routes of the `codex-agent-api` template, its README and its `e2e_test.py`.

Severity scale: **Blocker** (design cannot satisfy a stated requirement), **High** (a fresh AI or SDK user will hit it on the first try), **Medium** (wrong or ambiguous, workaround exists), **Low** (polish).

---

## 1. Summary

| Severity | Count |
|---|---|
| Blocker | 0 |
| High | 16 |
| Medium | 26 |
| Low | 9 |
| Total | 51 |

Headline: the policy and operation model is sound and the happy-path one-liners work. The weak parts are (1) the OpenAI wire contract, which is under-specified in exactly the places the official SDK is strict, and (2) a handful of fail-open or silent-failure behaviours that an AI author will trip over because the card promises errors that the prototype does not raise.

---

## 2. Verified official endpoint count (claim: 47)

I counted the operations myself. The design's total of 47 is **correct**, and so is every per-resource count.

| Resource | Operations | Count |
|---|---|---|
| agents | create, retrieve, update, list, delete | 5 |
| environments | create, retrieve, delete | 3 |
| environments.files | create (prepare/upload), list | 2 |
| environments.templates | create, retrieve, update, list, delete | 5 |
| sessions | create, retrieve, update, list, delete | 5 |
| sessions.events | create, stream | 2 |
| sessions.items | list | 1 |
| sessions.turns | create/retrieve/cancel group | 3 |
| sessions.artifacts | list, retrieve, content, delete | 4 |
| sessions.traces | retrieve | 1 |
| sessions.subagents | six operations | 6 |
| vaults | five operations | 5 |
| vaults.credentials | five operations | 5 |
| **Total** | | **47** |

Notes on the count:

- The SDK exposes 52 callables. The 5 extras are client-side helpers that do not add HTTP routes: `environments.files.prepare`, `environments.files.prepare_directory`, `environments.files.upload`, `artifacts.for_result`, and `sessions.stream`. `sessions.stream` is built on `events.stream` plus `events.create`.
- Official paths are under `/v1`. The SDK sends `OpenAI-Beta: agents=v1` on every call.

Tier arithmetic in the README sums correctly:

- 19 implemented = agents 5 + sessions 5 + events 2 + items 1 + turns 3 + environments 3.
- 7 later = artifacts 4 + traces 1 + environment files 2.
- 6 refused = subagents.
- 15 not planned = templates 5 + vaults 5 + credentials 5.

### Tiering corrections and critique

| ID | Severity | Clause | Problem | Fix wording |
|---|---|---|---|---|
| T-1 | High | README tier table; 05 §2 vs the "15/15 template routes covered" claim | The template has artifact list, get, content and delete routes. The design puts all four artifacts in tier 2 ("later") yet claims the template's 15 routes are all covered. Both cannot hold. Migrating the template regresses artifacts. | Either promote `artifacts` (list, retrieve, content, delete) to tier 1 (they are file-backed and cheap), or change the claim to "11 of 15 template routes covered at v2.0; artifacts follow in 2.1". |
| T-2 | Medium | 05 §2 subagents "refused" | Refusing 6 operations with 501 is hostile to the SDK: a session object may reference subagents and an SDK user can call `subagents.list` routinely. | `sessions.subagents.list` should return a valid empty list envelope. The remaining 5 return 404 `not_found_error`, not 501. Keep the "refused" label for create/mutate. |
| T-3 | Medium | 05 §2 vaults "local equivalent `llm.api_key_env`" | Vaults hold MCP and bearer credentials and sandbox environment secrets. They do not hold LLM provider keys. The stated local equivalent is wrong. | Reword to: "Vaults carry tool credentials, not LLM keys. LLM keys come from `llm.api_key_env`. The local equivalent of a vault is `secrets:` in the server config (not planned)." |
| T-4 | Medium | 05 §2 environment files "later" | No op IDs are defined for the two environment file operations, so they cannot be policy-addressed even when they ship. | Reserve `agents.environments.files.create` and `agents.environments.files.list` now, with effects `write` and `read`. |

---

## 3. OpenAI Agents API compatibility (lens C)

All claims below marked "demonstrated" were reproduced with the real `openai` 3.29.0 SDK against a fake server that serves exactly what the design documents.

### 3.1 Findings

| ID | Severity | Clause | Problem | Fix wording |
|---|---|---|---|---|
| C-1 | High | 05 §3-§5 (session and event shapes) | The design never mentions `event_id` on events, `turn_id` and a `turn` object on turn events, or a full `Agent` object on the session. Demonstrated: without them `client.beta.sessions.stream()` fails with "Session event stream ended before the turn reached idle or failed", and `session.agent.model` raises `AttributeError` when `agent` is serialized as a string id. With the full shapes the helper passes. | Add a "Wire shapes" subsection to 05. Every event MUST carry `event_id` (unique, stable across reconnects) and `type`. Turn events MUST carry `turn_id` and a `turn` object with `id, agent_id, created_at, object:"turn", session_id, status` (`subagent_id` null for the root turn). Session objects MUST embed the full Agent object (`id, model, multi_agent, reasoning, service_tier, text, tools`), plus `created_at, environment, last_active_at, metadata, object:"session", required_actions:[], status, vault_ids:[]`. |
| C-2 | High | 05 §6 (list endpoints) | The list envelope is unspecified. Official lists are `{object:"list", data, first_id, last_id, has_more}` with `after`, `limit` (1-100, default 20) and `order` (default `desc`). Demonstrated: a server that ignores `after` and omits `has_more` makes SDK auto-pagination loop without end (stopped manually after 25 requests). The template itself emits lists without `has_more`. | Specify the envelope and the three query parameters for every list op. State that omitting `has_more` is a conformance failure. Add a conformance test that iterates a list with `limit=1` and asserts termination. |
| C-3 | High | 05 §4 (adapter selection by `model`) | The adapter is chosen from the request's `model` string. Any non-adapter model (`gpt-5-codex`, the template's `codex-mini`, any official model name) gives 404 `op.not_enabled`. This contradicts the template README's claim that migration is "only change base_url", and breaks every stock OpenAI SDK snippet. | When exactly one adapter is mounted, or on a per-adapter mount (`/agents/<a>/v1`), treat `model` as the upstream LLM model name and route to that adapter. Only use the model-string prefix to disambiguate when several adapters are mounted, and fall back to the first mounted one with a `Warning` header rather than 404. |
| C-4 | High | 05 §5 (streaming) | "The stream ends with idle or failed" is incomplete. The SDK `sessions.stream()` helper requires the session to be idle at entry, subscribes first, then POSTs the input event with an `Idempotency-Key`. It ignores the initial idle and waits for an idle event after the root turn ended. A server that closes on the first idle breaks it. | State: on subscribe the server keeps the stream open when the session is idle; it closes after the post-turn idle or after `agent.session.failed`. Events are de-duplicated by `event_id`, so replays after reconnect are safe. |
| C-5 | High | 05 §3 (events.create) | The response contract is not stated. The SDK expects `POST .../events` to return HTTP 202 with no body and sends an `Idempotency-Key`. `events.stream` is a GET with `Accept: text/event-stream`. | Specify `202` with an empty body for `events.create`, honour `Idempotency-Key` (replay returns 202 without a second turn), and serve `events.stream` on GET. |
| C-6 | High | 05 §2 (`sessions.create`) | The required input shape is not specified. `environment` is required and its type is one of `none`, `openai_hosted`, `self_hosted`. `none` requires `input`. `agent_id` or an inline `agent{model,...}` is accepted, plus `input`, `metadata`, `stream`, `vault_ids`, `spend_control`. `stream=true` returns SSE from the POST itself. | Add a table of accepted `environment` types and their local meaning: `none` (no workspace), `self_hosted` (this sandbox, return `environment.id` and `remote_url`), `openai_hosted` (reject with 400 `invalid_request_error`). Specify `stream=true` on create. |
| C-7 | Medium | 05 §3 (session status) | The status list omits `requires_action`. The SDK literal set is `idle`, `in_progress`, `requires_action`, `failed`. | List all four. State that `required_actions` is always `[]` while tool results are refused. |
| C-8 | High | 05 §9 and template migration notes | The template migration is not wire-compatible, and the doc understates it. Object name changes (`session` to `agent.session`), the template emits non-official events (`agent.session.turn.started`, `...output_item.added`, `...output_text.delta`, `...done`), fields are flat (`model/instructions/tools`) rather than nested under `agent`, and `agent` may be a plain string id. Its own `e2e_test.py` asserts `object == "session"` and the non-official event name, so it fails after migration. | Add a migration table with old and new shapes and state that the template's e2e must be rewritten. Provide a `compat.legacy_codex_agent_api: true` shim for one release, or state plainly that this is a breaking change. |
| C-9 | Medium | 05 §1 (reason the template "cannot be used by the SDK because of `X-Access-Token`") | Inaccurate. The template only enforces `X-Access-Token` when `EBX_SERVER_TOKEN` is set; otherwise it is open. The real blockers are the shapes in C-8 and the SDK's required `environment` field, which the template README quickstart omits. | Correct the rationale. |
| C-10 | Medium | 05 §7 (Responses API "also supported") | `/v1/responses`, its GET and DELETE, and `input_items` are claimed supported but have no op IDs beyond `run` and `cancel`. Those routes are not policy-addressable, which violates R1 and R2. The wire shapes are unspecified. | Give each route an op ID (`agents.<a>.responses.create/get/delete/input_items`) or state that Responses is out of scope for 2.0. |
| C-11 | Medium | 06 (install wait) | Default `install.wait: true` blocks `sessions.create` or `send` for up to 10 minutes. This conflicts with the 202 semantics (C-5), with the SDK's subscribe-before-send flow (no event stream is open during `create`), and with gateway idle timeouts. Install is also declared at session creation even when no turn ever runs. | Install lazily at the first turn, and make it asynchronous on the `/v1` wire: `sessions.create` returns immediately, the first turn emits an `agent.session.installing` style progress event, and `failed` carries `install.failed`. Keep blocking only for the non-`/v1` convenience routes. |
| C-12 | Medium | 05 §8 (error mapping) | `501 agents.not_supported`, `502 install.failed` and `409` are all retried by the SDK (it retries 408, 409, 429 and 5xx unless `x-should-retry: false`). A permanent refusal would be retried twice with backoff. | Send `x-should-retry: false` on every permanent error. Use official error `type` values on the `/v1` wire (`invalid_request_error`, `not_found_error`, `authentication_error`, `permission_error`) and keep the dotted codes in `error.code`. |
| C-13 | Low | 05 §5 (`Last-Event-ID` and `?after=`) | The official docs say streams are not resumable via `Last-Event-ID` (recovery is by listing items). The design's resume is therefore an extension. It is additive and harmless, but it is not "compatible", and it is not labelled. | Label it "extension (not in the official API)". |
| C-14 | Low | 05 (`tool_result` input events) | The SDK has `sessions.create(tool_handlers=...)` and input event types `tool_result` and `computer_use_approval`. The design rejects these with no stated error. | State that these return 400 `invalid_request_error` with `code: "agents.tool_result_unsupported"`. |
| C-15 | Medium | 05 (`usage`, `spend_control`, `last_active_at`, `vault_ids`, `remote_url`, `environment.id`) | None of these fields are specified. A self-hosted environment requires both `id` and `remote_url` in the official shape. | Add them to the session shape table with fixed local values (`vault_ids: []`, `usage` from adapter or zeros, `spend_control` echoed). |
| C-16 | Low | 06 manifest note | The Qoder package is flagged "name to be verified". It exists as `@qoder-ai/qodercli` with bins `qoder` and `qodercli`. Other bins: `@openai/codex` provides `codex`, `@anthropic-ai/claude-code` provides `claude`, `@qwen-code/qwen-code` provides `qwen`. | Replace the note with the verified name and bins, and pin the version when the manifest is generated. |
| C-17 | Low | 05 §1 ("about 1,400 lines") | The template `commands.py` is 1,159 lines. | Correct to about 1,160 lines. |

### 3.2 Template compatibility (`codex-agent-api`)

- The 15 template route paths map one to one to design ops, so the route table is right. Confirmed.
- Payload and event shapes do not (C-8). Artifacts regress under the current tiering (T-1).
- Env var names differ: the template uses `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `CODEX_MODEL`, `AGENT_MAX_SESSIONS`, `AGENT_SESSION_TTL`; the design uses `LLM_*` and `EBX_LLM_*`. See N-5.
- Official semantics worth stating once in 05: in OpenAI's own `self_hosted` mode the harness runs on OpenAI's side and the sandbox runs an exec server. The design instead runs the agent loop inside the sandbox. That is a deliberate and acceptable divergence, but 05 should say so, because SDK users will read `environment.type = self_hosted` as the former.

---

## 4. AI-codegen usability (lens B): eight template files written from the card

I wrote each file using only the 09 reference card, then ran it against the spike. "Runs" means it loaded and behaved as the card says under the shim.

| # | Scenario | Runs? | Notes |
|---|---|---|---|
| T1 | Download-only `/tmp` | Yes | `presets.download_only(root="/tmp")` works. `.env` gives 403 `policy.path_denied`. Upload and commands give 404 `op.not_enabled`. 2 YAML lines or 3 Python lines. |
| T2 | Commands scoped to git and pytest in `/workspace` | Yes, with guesses | Had to guess the preset keyword (`workspace=` vs `root=`), see B-8. Security issue in B-9. |
| T3 | Codex hosted | Partly | `agent_host` loads. Calling `client.beta.agents.create` returns 404, see B-10. `start(config=)` type is unspecified. |
| T4 | `claude_code` plus `qoder` hosted | Partly | Same as T3. Qoder is experimental but the card does not flag it, see B-16. |
| T5 | Custom op with auth hook | Yes | `@op`, `Policy().authorize(...)`, `Narrow` and veto all behave as documented. Default effects trap, see B-3. |
| T6 | Read-only file browser | Yes | `presets.readonly(paths=...)` works but mounts more than a file browser wants, see B-9. |
| T7 | Multi-tenant, two tokens | Yes | `principals=["id:alice"]` plus `paths="/data/alice"` plus `SandboxServer(policy, authenticate=fn)` works. The `authenticate` signature is undocumented in the card, see B-12. |
| T8 | Migration of a v1 server | Partly | Adding any policy silently unmounts `custom.*` and `ext.*`, see B-6. Also found a spec hole, see B-14. |

Card names that the spike lacks, so a shim was required: `start`, `AgentScope`, `UrlScope`, `configure`, `Registry`. The card promises them but a fresh AI cannot run them. Either implement or remove them from the card before it is published (B-17).

### 4.1 Findings

| ID | Severity | Clause | Problem | Fix wording |
|---|---|---|---|---|
| B-1 | High | README headline policy; 03 §1 example | `Policy().allow(ops.files.download, ...)` leaves `core.health` unmounted (404; confirmed in the spike). R2 says health is "allowed by every preset", but a bare `Policy` is not a preset. The platform `ready_cmd` is the `healthcheck` CLI, so a sandbox built from the headline example would never become ready. | Make `core.health` always mounted for loopback or anonymous callers unless explicitly denied by `deny(ops.core.health)`. If you prefer to keep it explicit, the card must say "start from `presets.minimal()` and add". |
| B-2 | High | 09 §1 ("`Policy.allow` errors on unknown selectors") | A typo such as `Policy().allow("file.list")` constructs silently. Only `.check()` reports it. The card promises an error. | Validate selectors when the `SandboxServer` is constructed, and in `start()`, and raise `PolicyError` with a `did you mean files.list` hint by default. Keep `strict=False` for tests only. |
| B-3 | High | 09 §5 vs 04 §10 vs spike (default effects of `@op`) | Three different defaults: the card says `admin` with a warning, 04 §10 says legacy custom commands default to `exec`, and the spike defaults to `read`. Demonstrated: `@op("custom.x")` with no `effects`, under `Policy().allow("effect:read")`, returns 200 with an empty lint. A forgotten annotation therefore fails open. `explicit=` is also missing from the `@op` signature in 02 §3. | Default to `admin` (fail-closed), emit a lint warning "effects not declared", and require `effects=` in strict mode. Align 02, 04 and 09 and the spike. Add `explicit=` to the 02 §3 signature. |
| B-4 | High | 03 §6 (`deny(paths="/dir")`) | A deny with a non-wildcard path does not cover the subtree. Demonstrated: `deny(paths="/secret")` still lets `/secret/a.txt` through (200, empty lint), because paths containing `/` without wildcards match only the exact path. Conversely, a glob such as `allow(paths=["**/.env"])` is silently accepted as a root. | State and implement: a path with no wildcard characters means "this path and everything below it" for both allow and deny. Lint any glob character in an allow root as an error with the message "allow roots are prefixes; use deny for patterns". |
| B-5 | Medium | 04 §10 and 02 §3 (group for custom ops) | An op registered with `@op` but mounted by no rule is silent: 404 and an empty lint. `full_access()` does not mount `custom.*` in the spike because the op needs `group=`, while 04 says the group `commands` is `custom.*`. Ops in their own namespace (`grader.run`) belong to no group. | Add a lint "op `X` is registered but no rule mounts it" in `check-config` and at startup. State which preset groups include `custom.*` and make `full_access()` include every registered op. |
| B-6 | High | 04 §10 (v1 compatibility) | Adding any policy silently unmounts legacy `custom.*` and `ext.*`. A migrating author sees working routes disappear with no message. | Add `easy-sandbox-server init --from-legacy` (or `migrate`) that emits a policy mounting what v1 exposed. Make `check-config` print a "v1 would have served X, v2 serves Y" diff. Log one startup line per legacy route that is now unmounted. |
| B-7 | Medium | 03 §1 vs 04 §4 vs 02 §7.1 (`files.download_stream`) | Three contradictions: 03 §1 claims `GET /files/download-stream` works under `allow(download, stat, list)`, 04 §4 says it is intentionally unmounted, and the 02 §7.1 sample binds `files.download` to `/files/download-stream` with a `files_download_stream` alias while 04 and 10 map `/download` to `files.download` and `/files/download-stream` to `files.download_stream`. The 03 §4 `download_only` row also lists only `download`, `stat`, `list`. | Pick one. Recommended: `download_stream` is a separate op, mounted by `download_only`, and 02 §7.1 is corrected. |
| B-8 | Medium | 03 §4 (preset keywords) | Each preset names its root differently: `readonly(paths)`, `download_only(root)`, `workspace_jail(root)`, `ci_runner(workspace)`, `agent_host(workspace)`. A wrong keyword is a `TypeError`. A fresh AI guessed wrong on `ci_runner`. | Use one keyword `root=` (accept `paths=` and `workspace=` as aliases) and print the accepted names in the error. |
| B-9 | High | 03 §4 (`ci_runner`, `readonly`) | `ci_runner` mounts 19 ops including `files.upload`, `files.delete`, `files.move`. Allowing `pytest` or `git` while files are writable is arbitrary code execution (a `conftest.py`, `.git/config` or hooks). The lint is silent because the pattern has no absolute-path token. The 03 §4 sample args show `python3 -m ...`, which contradicts the escape-capable lint. `readonly` for a file browser also mounts `system.ports`, `system.packages`, `system.info`, `system.metrics` and `process.*`, and `files.archive` needs read plus write. | Add `presets.commands_only(root, allow=[...])` that mounts no write ops, and `presets.files_readonly(root)` that mounts only `files.list/stat/read/download/download_stream`. Add a lint: "commands allow `git|pytest` while write ops are mounted under the same path: code execution". Remove `python3 -m` from the sample. |
| B-10 | High | 03 §4 (`agent_host` expansion) | The preset mounts only `agents.definitions.list`, not `create`. The first SDK call, `client.beta.agents.create`, returns 404. The generic agents ops are not listed in the 03 §4 expansion. | Spell out the exact expansion for `agent_host` (all of `agents.definitions.*`, `agents.sessions.*`, `agents.environments.*`, plus `agents.<a>.run` for the chosen adapters). Add a test that runs the SDK quickstart against `agent_host`. |
| B-11 | Medium | 09 §3 (Python flavour) | Auth tokens, `llm:`, install mode and audit can only be set through YAML or `config=`. The type of `start(config=)` is unspecified (dict, path, `ServerConfig`?). The card has no `--load server.py` or module-level `policy` convention (only 08 §3 has it). | Add one example to the card showing a complete Python-only server with tokens, `llm` and install mode, and state the `config=` type. |
| B-12 | Medium | 09 §3 (`authenticate=`) | The signature, the header-name case rules and the return type of `authenticate` are undocumented. | Document: `def authenticate(headers: Mapping[str, str]) -> Principal | None`, headers lower-cased, `None` means 401. |
| B-13 | Medium | 03 §1 vs card (preset strings) | 03 §1 uses `"download-only"` (hyphen) while the Python API uses `download_only`. The card does not say which spelling each place accepts. | Accept both spellings everywhere and make the canonical form the underscore. |
| B-14 | High | 03 §7 (`ctx.paths`) | Spec hole. When the winning statement has no `PathScope`, `ctx.paths` is unspecified. Demonstrated: `files.list` under `full_access()` raised `KeyError: 'path'` in the spike, which would surface as a 500. | Define `ctx.paths` as an empty mapping and have handlers fall back to the request's raw path argument after the path guard. Add a regression test for every path-taking op under a statement with no `PathScope`. |
| B-15 | Medium | 03 §9 (per-tenant paths) | No path templating such as `{principal.id}`, so multi-tenant authors write prefix checks in a hook, which is error-prone (for example `/data/alice` vs `/data/alice2`). | Support `PathScope("/data/{principal.id}")` and document that hook prefix checks must compare path components. |
| B-16 | Medium | 03 §4 and 09 (experimental adapters) | `qoder`, `qwen` and `cursor` are experimental but neither the card nor the `agent_host` preset flags this. | Add `experimental` to `agents.list` output and a one-line warning at startup. |
| B-17 | Medium | 09 §3 (card promises vs prototype) | The card names `start`, `AgentScope`, `UrlScope`, `configure`, `Registry`, none of which exist in the prototype. A card that is wrong on first import destroys AI trust. | Gate card publication on a test that imports every name used in the card (an extension of S1-S8). |
| B-18 | Medium | 03 §5 (open mode) | `agent_host` or `ci_runner` with no auth configured yields open mode, with every caller treated as anonymous admin, over a preset that can execute commands. | Refuse to start an exec-capable preset without auth unless `--insecure-open` is passed. |
| B-19 | Low | 03 §6 (principals lint) | No lint for `principals=` ids or roles that no configured token can produce, so a typo silently denies everyone. | Add a lint "no configured token yields principal `X`". |
| B-20 | Medium | README D4 vs 02 pipeline step 4 vs 03 §11 | D4 says `op.unknown` and `op.not_enabled` are byte-identical. The pipeline step and the 03 §11 table give different codes, and the spike returns different bodies. | Restate D4 as "identical status and shape for unauthenticated callers; distinct codes for authenticated callers", or make the bodies identical. |
| B-21 | Low | 09 §3 (card gaps) | The card has no client-mirror section (`ServerClient` is never mentioned), no v1 migration section and no `ext.*` or `table.route` guidance. | Add three short sections. Keep the card under the 82-line budget by moving the agent-CLI details out. |
| B-22 | Low | 09 §3 (line width) | Card lines reach 182 characters, which wrap badly in many viewers and prompts. | Wrap at 100. |

---

## 5. Naming and discoverability (lens A, check 2)

| ID | Severity | Clause | Problem | Fix wording |
|---|---|---|---|---|
| N-1 | Medium | 05 (`agents.list` vs `agents.definitions.list`) | `agents.list` lists runtimes (adapters) while `agents.definitions.list` is the official `GET /v1/agents`. The names are easy to confuse and the first is the more likely to be guessed for the second. | Rename to `agents.runtimes.list` and `agents.runtimes.doctor`. Keep `agents.definitions.*` for the official resource. |
| N-2 | Medium | 05 op IDs (`sessions.events`, `sessions.items`, `sessions.send`) | The first two are nouns, which violates the verb rule in 02, and `sessions.send` maps to the official `events.create`. | Rename to `sessions.list_events` and `sessions.list_items`, and publish a generated mapping table: SDK method, HTTP route, op ID, tier. |
| N-3 | Medium | 07 vs 05 (mirror semantics) | 07 uses `sessions.create(workspace="/workspace")` but 05 requires `environment={...}`. Parameters for `agents.<a>.run` and `sessions.create` are never specified, and the mirror semantics of stream and byte ops (async iterator? bytes?) are unspecified. | Fix the example. Add a "stream and bytes ops" subsection to 07 with signatures for `download`, `stream`, `events`. |
| N-4 | Medium | 03 §10 vs 06, 08, 09 (`explain` flags) | Spelled three ways: `check-config --explain OP --path P`, `explain --op --path --principal`, and `explain --op --arg k=v`. | Keep one: `explain --op OP [--arg k=v ...] [--principal ID]`. Make `--path` shorthand for `--arg path=`. Remove `check-config --explain`. |
| N-5 | Medium | 06 and 05 (env var names) | `EBX_INSTALL_MODE` vs `EBX_SERVER_INSTALL_MODE`, and `EBX_LLM_*` vs `LLM_*` vs the template's `OPENAI_*`. | Choose the `EBX_SERVER_*` prefix for server settings and `EBX_LLM_*` for LLM settings. Accept `OPENAI_API_KEY` and `OPENAI_BASE_URL` as documented fallbacks, so the template's env still works. |
| N-6 | Medium | 02 §6 (404 `op.not_enabled` body) | A disabled op returns a body with no hint. In development a fresh AI sees only 404 and cannot tell "typo" from "policy". | Add `serve --explain-denials`, bound to loopback only, where 404 and 403 bodies include the rule or lack of rule that decided. Keep production bodies terse. |
| N-7 | Low | 02 §4 (legacy underscore aliases) | Both `files_download_stream` and `files.download_stream` appear in the docs without a rule for which to use in new code. | State that underscore names are accepted only in v1 config and are reported by `check-config` as "deprecated alias". |
| N-8 | Low | 07 (error codes E3100-E3111) | The error code table is not cross-referenced to the wire codes (`op.not_enabled`, `policy.path_denied`, `limit.*`). | Add a two-column table: wire code to client exception class to E-code. |

What works for discoverability: typo hints (`did you mean files.list`), `describe()` listing mounted ops, and `check-config` messages that name the rule index. These are actionable. The gap is that none of them run at construction time (B-2).

---

## 6. Time to first template (lens A, check 4)

| Template | Config lines | Concepts to learn |
|---|---|---|
| Download-only | 2 YAML, or 3 Python | 2 (preset, root) |
| Git plus pytest CI | about 7 YAML | 4 (preset, rules, command patterns, typed tokens) |
| Codex hosted | 13 in the doc, about 6 minimal | 5 (preset, adapter, llm, install mode, auth) |
| Custom op with hook | about 14 | 8 (`@op`, effects, group, policy, authorize, Narrow, principal, ctx) |
| v1 `codex-agent-api` template | 1,159 lines of `commands.py` | n/a |

The reduction from 1,159 lines to about 6 is real and is the strongest argument for the design. The risk is on the second half of the curve: the custom op plus hook case needs 8 concepts, and 3 of them (effects default, group, ctx.paths) are exactly where B-3, B-5 and B-14 bite.

---

## 7. What held up

- The 47-operation count, every per-resource count and the `/v1` paths match the official reference and SDK. The tier arithmetic is correct.
- The 15 template route paths map one to one to design ops.
- Preset one-liners work as documented. The 404 vs 403 split, deny-over-allow, hooks (veto, `Narrow`, fail-closed on an exception), `.without()`, per-principal rules and `did you mean` hints all behave as designed in the spike.
- `agents.codex.**` does not grant the explicit-only `agents.codex.install`. `serve` never installs.
- The `build` mode plus `prepare` design satisfies "no codex download unless used".
- Universal Bearer auth plus `base_url` is the correct choice for the OpenAI SDK.
- `Last-Event-ID` resume is purely additive (see C-13 for labelling).
- Spike suites pass: `tests_proto` 36/36, `tests_round4` OK, `ai_consumer` S1-S8 (59 checks). All eight of my card-derived files load; T1, T5, T6 and T7 behave correctly end to end.
- Operation IDs and attributes (`ops.files.list`, `ops.agents.codex.*`) removed the need for raw method and path tuples in every file I wrote. None needed them.

---

## 8. Limitations of this review

- Most of the OpenAI behaviour was tested against fake servers built from the design text, not against the real service. Where I say "demonstrated", I mean the SDK behaved that way against such a server.
- The official docs were read as published at the time of review; the SDK version used was 3.29.0. A newer SDK may tighten or relax some required fields.
- The spike lacks `start`, `AgentScope`, `UrlScope`, `configure` and `Registry`, so T3 and T4 could be validated only up to policy loading and the `agents.*` mounts, not against a running adapter.
- Severity counts in section 1 include every table row in sections 2-5.
- I did not review security beyond what bears on user experience; rounds 1 and 3 cover that.
