# Reconciliation: Agents-API worker output vs Server SDK v2

Status note from the worker that built the agents hosting (branch `cursor/agents-api-hosting-6516`, worktree `/home/ubuntu/wt-agents`, pushed to `origin`). It maps what exists to the v2 work packages in [10](../10-implementation-plan.md) (section 3 and 9b). `v2.1-disposition.md` did not exist when this was written; section 5 lists what must be re-checked against it. This note does not edit the v2 set.

## 1. Where the code is

| Location | State |
|---|---|
| `origin/cursor/agents-api-hosting-6516` (worktree `/home/ubuntu/wt-agents`) | **Complete flat v1 implementation**, merged with the fine-grained-capabilities branch: `server/agents/*`, `server/routes_agents.py`, client `easy_sandbox/agents/*`, tests, examples, docs. Server suite: all green except the env-only pip test and two timing flakes of the other workstream; client agents tests 133 passed. |
| `/workspace` (shared checkout, branch `cursor/e2e-foundation-796d`) | An **orphaned early snapshot** (config, errors, events, procenv, redact, adapters; untracked) without `runtime`, `store`, wires or `routes_agents.py`. `app.py` imported the missing `routes_agents`, which broke `import easy_sandbox.server`. The import line was removed (app.py is byte-identical to HEAD again). The untracked `server/agents/` package is inert (nothing imports it). |

## 2. File to work-package map

| Existing file(s) (flat layout, branch above) | v2 WP | Disposition |
|---|---|---|
| `agents/runtime.py`, `store.py` (sessions, turns, items, queue, ring buffer, cancel ladder, limits, persistence) | WP-6 `agents/{runtime,store,journal,queue}.py` | Semantics adopted by v2 (05 header). Re-home, split journal/queue out, add per-principal ownership and principal-namespaced idempotency, move state under `EBX_AGENTS_STATE_DIR` journal. |
| `agents/events.py`, `redact.py`, `procenv.py` | WP-6 / WP-3 (`guards/env.py`) | Reusable almost as is (neutral event model, redactor incl. URL-encoded/JSON-escaped/Bearer forms, child env allowlist). `procenv` should delegate env filtering to `guards/env.py`. |
| `agents/wire_sessions.py` (Agents wire), `wire_responses.py` (Responses wire) | WP-6 `agents/wire_openai.py`, `wire_native.py` | Sessions wire: port to the v2.1 shapes (list envelope `has_more/after/limit/order`, `event_id`/`turn_id`, 202 on events.create, idle-open stream, `agent`/`agent.session` object names). **Responses wire is out of 0.3.0 (decision A11)**: keep as a reserved, disabled module (`agents.<a>.responses.*`), do not mount. |
| `routes_agents.py` (flat `RouteTable` routes, coarse group `agents`) | WP-6 `agents/ops.py` + `resolver.py` | Replace by generated `agents.<adapter>.*` op families and the alias resolver. Flat group, `_G` registration and the Bearer special case in `app.py` go away (universal auth, 03 section 5). |
| `agents/config.py` (`AgentSpec`, `provider:` block, `${VAR}` expansion) | WP-6 (declarative `command` schema from 05 section 6) | Rename `provider` -> `llm` with `*_env` references only; drop `api_key` literals; keep validation, "did you mean", secret separation. |
| `agents/adapters/{codex,claude_code,qwen_code,cursor}.py`, `stream_json.py`, `command.py`, `base.py` | WP-7a..d, WP-6 (`base`, `command`) | Parsers and invocation builders (golden argv/env/files, permission mapping, MCP placeholders, resume) are reusable. **Must change**: remove `install_steps` / `install` route / `EBX_AGENTS_ALLOW_INSTALL`; adapters declare a `manifest` (06); permissions refuse when unsupported; `qoder` (WP-7e) not implemented here. |
| `agents/__main__.py` (`serve|runtimes|doctor|install`) | WP-9 `cli/` | `serve` and `doctor` map to the v2 CLI; `install` is replaced by `prepare`. |
| Client `easy_sandbox/agents/*` (`Agent`, `Runner`, `Session`, `AgentHost`, transport, `connect_openai_environment`) | 9b item 11 / WP-10 client mirror | Keep the public surface; reimplement `AgentHost` over `srv.agents.<adapter>.*`, bootstrap via `prepare` instead of the install POST, `llm=` instead of `provider=` (keep `Provider` as a deprecated alias). Error codes E7100-E7107 are independent of v2 (E3100-E3111 are the server-op family); no clash. |
| Server tests `tests/test_server/agents/*` (231 tests), golden SSE fixtures, fake CLIs | WP-6 / WP-7 gates | Fake-agent-binary harness, queue/replay/idempotency/cancel/limit tests and official-SDK oracle tests transfer once op IDs and shapes are updated. `test_policy_integration.py` targets the flat engine and is superseded by WP-2. |
| Client tests `tests/test_agents/*` (133), `examples/agents/*`, docs `guide/agents.md`, `reference/agents-api.md`, error codes E71xx (en and zh) | client mirror, docs | Docs must be re-pointed to op IDs, `llm:`, no install route, tiering. Examples are valid after the client reimplementation. |
| `docs/en/design/agents-api*.md` (design, review, CLI follow-ups) | superseded in part | Add the "Superseded in part by server-sdk-v2" banner (done in the worktree for en and zh design docs). |

## 3. Known deviations of the existing code from v2 (do not copy forward)

1. `/v1/responses` served (A11 says out of 0.3.0).
2. Coarse `agents` group and `agents_*` endpoint names instead of `agents.<a>.*`; `previous_response_id` semantics tied to that surface.
3. Install route, `install_steps`, `npm i -g`, `curl | bash` for Cursor, `EBX_AGENTS_ALLOW_INSTALL`.
4. `provider:` with literal `api_key`; hyphenated runtime names as canonical (`claude-code`, `qwen-code`).
5. Bearer accepted only on agents routes in the legacy `_check_auth` (either credential suffices there); the policy engine accepts Bearer everywhere. v2: universal, Bearer wins, conflicts 401.
6. Session ownership and idempotency keys are global, not per principal. Default permission `full_access` without an `AgentScope`.
7. Adapter chosen from `model` (name or alias) with an ephemeral default agent; v2 requires explicit selection (A6).
8. List envelopes, `event_id` formats and the 202 acknowledgement follow the v1 design, not v2.1.

## 4. Test and tree state at hand-off

- `/workspace` server-sdk: `import easy_sandbox.server` works; full `-m "not integration"` run with the tree on `PYTHONPATH`: 580 passed, 2 failed before stabilising (env-only `test_pip_returns_structure` and the timing race below). One real race was fixed in `routes_process.py` (process output read returned before the pipe readers had drained, losing the last chunk); that test and `test_routes_process.py` passed 6 of 6 repeated runs afterwards.
- Worktree branch: client-sdk agents tests 133 passed; server agents tests 231 plus policy integration 3; ruff and mypy clean on both packages (client has two pre-existing format diffs in files owned by the providers worker).
- Another timing-sensitive test of the capability worker, `TestAudit.test_deny_mode_logs_only_denials`, reads the audit log immediately after the response is sent (the event is logged in a `finally` after the body); it passes alone and fails occasionally under load.

## 5. To re-check against `v2.1-disposition.md` when it lands

Tier counts (this note follows 05's v2.1 header: 25 / 2 / 5 / 15), the exact `agents.<a>.*` op list and scope names, the `llm:` field names, the manifest format for adapters, and whether `environment` files are reserved or refused.
