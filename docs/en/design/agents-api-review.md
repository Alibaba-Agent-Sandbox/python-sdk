# Agents API design — adversarial review log

Design under review: [agents-api.md](agents-api.md).

**Process note (honest disclosure).** The brief asked for two rounds by *fresh
subagents*. The execution environment had no subagent facility, so each round
was carried out as a **separate, lens-restricted adversarial pass by the same
author**, with the explicit rule "try to break the design with evidence": every
finding below was checked against a primary artifact (the installed official
`openai` SDK 3.29 sources, the fetched CLI docs, or the repository code), not
only against intuition. The findings were applied to `agents-api.md` before the
next round started. Treat the independence claim accordingly; the review of a
different human/agent before release is still recommended.

Severity: **H** = would have shipped broken / unsafe, **M** = significant gap,
**L** = polish.

---

## Round 1 — functional completeness, OpenAI-compat fidelity, adapter feasibility

### Evidence gathered

* `openai/lib/streaming/agents/_streams.py` and `lib/beta/agents/_result.py`
  (how the official helper consumes an Agents-API session);
* `openai/types/beta/agent_session*.py`, `agents/sessions/**`, resource methods
  (paths, bodies, headers);
* Codex JSONL tests (`codex-rs/exec/tests/event_processor_with_json_output.rs`),
  Claude Code headless docs, Qwen Code headless docs;
* repository: `server/app.py`, `router.py`, `types.py`.

### Findings and resolutions

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| R1-1 | H | `sessions.stream()` **opens `GET …/events` on an idle session first, then POSTs the input**, and ignores initial idle events. A design where the events stream closes on idle (or replays history) would make the official helper hang or double-count. | §6.6: the events endpoint is a **live tail** that never closes on idle, headers flushed immediately, `?after=`/`Last-Event-ID` replay, unique `event_id` per event (the SDK de-duplicates by `event_id`). Oracle test added to the plan. |
| R1-2 | H | The terminal condition of the SDK helper is `agent.session.idle` **after** a root `turn.completed|failed|cancelled` (or `agent.session.failed`). The first draft only listed the turn events. | §6.3 event order spells out `turn.* → agent.session.idle`; `AgentTurnResultCollector` requires `turn.created` (no `subagent_id`), `item.done` of `message` items with `phase != commentary`, `status == completed`. Mapper emits exactly that. |
| R1-3 | H | Official Agents SDK (`Runner`) is **stateless by default**: it resends the whole transcript including prior `mcp_call`/reasoning items and does not send `previous_response_id`. The first draft took only the last user message ⇒ silently lost context. | §6.6 stateless fallback: bounded transcript preface for the first prompt of a new session; non-message items dropped; docs recommend `auto_previous_response_id=True`/`previous_response_id`. |
| R1-4 | M | Responses SSE events have required fields beyond type/delta (`item_id`, `output_index`, `content_index`, `logprobs`, `sequence_number`; `response.completed` carries the full `Response`). Typed clients validate them. | Mappers are built from the SDK's pydantic models and validated against them in oracle tests (`Response.model_validate`, `ResponseStreamEvent` TypeAdapter). §6.3 notes `usage` is never null on completion. |
| R1-5 | M | Tool activity representation: `function_call`/`local_shell_call` would make OpenAI clients try to execute tools locally. | Decision made explicit in §6.3: all CLI tool activity is a server-executed `mcp_call` item (Responses) / `command_execution`/`mcp_call` (Agents wire). |
| R1-6 | M | Sessions create: `environment` is a *required* field in the official client; `openai_hosted`/`none` are meaningless here. | §6.5/§2: accept `environment` of any shape for `self_hosted`/`none`, always echo a `self_hosted` environment describing the sandbox, reject `openai_hosted` with 400. |
| R1-7 | M | Missing endpoints used by the SDK: `DELETE /v1/responses/{id}` shape, `/v1/models`, `Idempotency-Key` on `events.create`. | Added to §6.4/§6.6. |
| R1-8 | M | `previous_response_id` to a non-latest turn: CLIs cannot fork. | Explicit `400 previous_response_not_latest`; listed as deviation. |
| R1-9 | H | **Codex resume**: `codex exec resume` does not accept `-C`/`-s` on all versions; draft passed them on every turn. | Use process `cwd` always, `-C` only on turn 1, and sandbox/approval via portable `-c sandbox_mode=…`/`-c approval_policy="never"` on both (§5 table). |
| R1-10 | M | Claude Code `bypassPermissions` refuses to run as root; stream-json in `-p` mode requires `--verbose`. | `IS_SANDBOX=1` set when `geteuid()==0` and `full_access`; `--verbose` always passed (documented in §5 table). |
| R1-11 | M | Cursor CLI has no stdin prompt and a prompt beginning with `-` would be parsed as a flag; its `--stream-partial-output` re-emits a consolidated duplicate of the text. | Prefix `Task: ` for dash-prefixed prompts; accumulated-text de-duplication in the cursor parser (§5). Both are fake-binary-tested; live behaviour flagged as an open question. |
| R1-12 | M | Codex `exec --json` emits **no token deltas**; draft implied streaming deltas for all runtimes. | §5/§6.3: a single synthetic delta carrying the whole message so delta consumers work; documented. |
| R1-13 | M | Qwen/Cursor MCP cell in the adapter table was unresolved ("see note"). | Decided: project-scoped config file with `${VAR}` placeholders, merged not overwritten, excluded from git; marked **experimental** (§5). |
| R1-14 | L | Requirement checklist: workspace *retrieval* (get results back) missing. | `AgentHost.diff()` helper + existing `sandbox.files` documented (§7). |
| R1-15 | L | Long non-streaming requests vs edge-proxy timeouts. | §6.6: client streams internally, SSE keep-alive pings, guidance for OpenAI-client users. |
| R1-16 | M | Adapter feasibility honesty: none of the four CLIs can be executed in this environment (no binaries, no keys). | Declared in §1 sources and §12; adapters are contract-tested with fake binaries emitting transcripts derived from the fetched docs/Codex test source; integration tests marked and skipped; `experimental` flag on least-verified paths (cursor, qwen MCP). |

Requirement coverage after round 1: quick config ✔ (agent.yaml, `Agent.*`
shortcuts) · creds/env ✔ · workspace/repo ✔ · sessions ✔ · streaming/events ✔ ·
cancel/limits ✔ · MCP ✔ · model/provider ✔ (cursor `base_url` explicitly
unsupported) · OpenAI compat ✔ with boundary table.

---

## Round 2 — UX/ergonomics, security, backward compatibility, testability

### UX / ergonomics

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| R2-1 | M | "One-liner" still required constructing a full `Agent`. | `sb.agents.run("codex", prompt)` accepts a runtime name; `Agent.codex()/claude_code()/cursor()/qwen_code()/command()` shortcuts (§7). |
| R2-2 | M | First run in a bare sandbox silently takes minutes (pip + npm). | `on_progress` callback, `sb.agents.prepare()`, a pre-baked template Dockerfile in the docs (§7). |
| R2-3 | M | Misconfiguration found only after the sandbox is created and billed. | `agent.validate()` on the client names the missing credential/option before any sandbox call; server-side `validate()` returns the same messages on `PUT /agents/definitions` (§7, §5). |
| R2-4 | L | Printing streamed text required parsing events. | `text_stream()` helper (§7). |
| R2-5 | L | `run_sync` inside notebooks fails obscurely. | Clear error message, documented (§7). |
| R2-6 | M | Default permission `full_access` is surprising. | Kept (inner sandboxes fail in containers; the VM is the boundary) but made loud: logged warning, shown in `GET /agents/health`, documented table of modes and residual risks (§4, §9). |

### Security

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| R2-7 | H | The `agents` group lets any token holder execute arbitrary commands (`runtime: command`, `extra_args`, definitions). A token handed to a less-trusted caller (e.g. an app proxying `/v1/responses`) must not imply that. | `EBX_AGENTS_LOCK_DEFINITIONS=1` (writes → 403), `EBX_AGENTS_ALLOW_COMMAND=0`, documented as RCE-by-design (§9.10). |
| R2-8 | H | Child processes would inherit the server's environment, including `EBX_SERVER_TOKEN` and unrelated secrets. | Env **allowlist** (§9.2) + test that a sentinel variable and the server token never reach the fake binary. |
| R2-9 | H | MCP headers/provider config could land secrets in config files or argv (`--mcp-config '{json}'`). | All config files contain `${VAR}` placeholders only; values in env; test scans argv + written files for secret values (§9.1, §5). |
| R2-10 | M | Argument-injection through `git clone <url>`, agent names, env names, MCP names. | Validation rules and `--` separators (§9.11). |
| R2-11 | M | Redaction by exact match misses URL-encoded/escaped forms. | Redactor matches URL-encoded, JSON-escaped and `Bearer` forms; base64 residual risk documented (§9.12). |
| R2-12 | M | Prompt-injected agent reading its own env. | Documented residual risk with mitigations; warning at registration (§9.13). |
| R2-13 | M | SSE subscriber/thread exhaustion; unbounded event logs. | Subscriber cap per session, ring buffer, session/turn caps, output cap (§6.1, §9.7). |
| R2-14 | L | Persisted items might hold tool-printed secrets. | Persist only redacted items, 0600 file, `EBX_AGENTS_PERSIST=0` switch (§6.1). |

### Backward compatibility

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| R2-15 | M | Adding an enum member changes `GET /capabilities` output and `list_groups()`. | Verified: all existing tests derive expectations from `CapabilityGroup`; the client's template capability tokens (`shell/files/code/...`) are an independent namespace and are untouched. The new group appears as `"agents": false` by default — additive. |
| R2-16 | M | Hardening `_dispatch_streaming` could change behaviour of existing SSE routes. | Only adds `BrokenPipe/ConnectionReset` handling and iterator `close()`; healthy streams are byte-identical (regression test over `/shell/stream`). |
| R2-17 | M | Accepting `Authorization: Bearer` globally would widen the auth surface. | Only for routes whose group is `agents`; test that Bearer on `/health`-less core routes (e.g. `/files/…`) is still 401. |
| R2-18 | L | Concurrent workers edit `router.py`, `app.py`, `api/sandbox.py`. | All logic in new modules; edits are ≤ 10 lines each, re-read immediately before editing, committed separately (§10). |
| R2-19 | L | `sandbox.agents` could shadow a future attribute. | Lazy `cached_property` named `agents`; existing names verified free (`grep`), no import of the new package at `import easy_sandbox`. |

### Testability

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| R2-20 | M | Time-dependent behaviours (timeouts, grace periods, TTL) make tests slow/flaky. | Injectable clock/ids and millisecond-scale limits/grace (§12). |
| R2-21 | M | Fake binaries must be portable (shebang to the test interpreter) and must *record* what they received to assert security properties. | Fake scripts generated at test time with `sys.executable` shebang; record argv/env/stdin to JSON (§12). |
| R2-22 | M | Oracle (`openai` SDK) is not a project dependency. | Optional: `pytest.importorskip` with `OPENAI_SDK_PATH` support; default CI skips, documented command to run it; core wire tests do not need it (hand-written shape assertions mirror the SDK models). |
| R2-23 | L | Streaming tests must not hang CI. | All HTTP tests use short socket timeouts and a hard wall-clock guard fixture. |

### Residual / open after both rounds

1. Live CLI behaviour (flags, JSONL details of `cursor-agent`, Qwen MCP file,
   Codex custom-provider TOML shape across versions) is unverified here.
2. `full_access` default and exfiltration risk need a product decision.
3. `server-sdk` has no YAML parser; server-side config files are JSON.
4. CLI (`ebx`) follow-ups: see [agents-api-cli-followups.md](agents-api-cli-followups.md).
