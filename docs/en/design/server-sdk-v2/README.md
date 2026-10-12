# Server SDK v2: design and implementation plan

Status: **design v2.1 complete, not implemented** (v2.1 = v2 revised in place after three independent reviews; see section 4a and [reviews/v2.1-disposition.md](reviews/v2.1-disposition.md)). This set is the **authoritative** design for the Easy Sandbox server SDK
(`python-sdk/server-sdk`, import `easy_sandbox.server`) and its matching client surface (`python-sdk/client-sdk`, import `easy_sandbox`).
Where an in-flight design document disagrees with it, the in-flight document changes
([10](10-implementation-plan.md) section 9 lists exactly what).

## 1. One-paragraph summary

Every capability of the server is an **operation** with one dotted ID (`files.download`, `commands.run`, `agents.codex.sessions.create`,
`custom.grade`) declared once with `@op`. HTTP method and path are derived bindings (the 41 legacy routes keep theirs; every op is also at
`POST /ops/{id}`). A **policy** of `allow`/`deny` rules over IDs, namespaces, groups and effects, with path, command, URL and limit scopes, per-principal
rules and veto-only hooks, decides what is mounted (404, no oracle) and what is permitted (403/413/429). The **Agents API** is the official OpenAI Agents
API (47 operations counted from the real SDK; 25 implemented, 2 reserved, 5 refused, 15 not planned) served by adapters over CLI agents, and CLIs are installed
**lazily from checksummed manifests after authorization** (build-time `prepare` is the recommended path on FC). Every allow of a path, command, URL or agent op **must carry its scope**, and an
unset token secret refuses to start (v2.1). The client mirror is generated from the same catalog. The core stays stdlib-only.

```python
from easy_sandbox.server import start, Policy, ops, PathScope

policy = Policy().allow(ops.files.download, ops.files.stat, ops.files.list,
                        paths=PathScope("/data", deny=["**/.env"], max_bytes="10MB"))
start(policy, port=9000)                 # everything else answers 404 op.not_enabled; core.health stays mounted
```

## 2. The product requirements and where each is answered

| # | Requirement | Answer |
|---|---|---|
| 1 | Granular plus coarse capability control; "only download, limited to /tmp" | [03](03-policy-and-permissions.md) sections 1-9; presets: section 4 |
| 2 | Ergonomic stable dotted IDs as attributes/methods, identical on client and server; derived HTTP bindings; discoverable | [02](02-operation-model.md) (grammar, `@op`, bindings, discovery); [07](07-client-mirror.md) |
| 3 | First-class Agents API aligned with OpenAI (count, official SDK, template's 15 routes, adapters, lazy install, base image, console command) | [05](05-agents-api.md), [06](06-lazy-install.md) |
| 4 | Complete, batteries-included but opt-in server SDK | [04](04-builtin-modules.md) (105 ops in the default registry with five adapters; 41 legacy routes) |
| 5 | Multi-round adversarial planning | [reviews/](reviews/) (5 author rounds + 3 independent reviews + [v2.1 disposition](reviews/v2.1-disposition.md)), [spikes/](spikes/) |
| 6 | Explicit answers: custom ops | [02](02-operation-model.md) section 8 |
| | policy composition, hooks, path and command scoping, presets, config sources, hot reload, error model (E3xxx, 403 vs 404), observability | [03](03-policy-and-permissions.md) sections 2-3, 8, 6-7, 4, 10, 11, 14 |
| | API/ID versioning, OpenAPI export | [02](02-operation-model.md) sections 7, 9 |
| | TypeScript and other-language client generation (Node CLI mirror) | [07](07-client-mirror.md) sections 2, 7 |
| 7 | Final code layout, compat imports, stdlib-only core | [10](10-implementation-plan.md) sections 1, 2 |

## 3. Index

| File | Content |
|---|---|
| [01-principles.md](01-principles.md) | Seven rules, scope, vocabulary, compatibility stance |
| [02-operation-model.md](02-operation-model.md) | ID grammar, `@op`, registry, bindings, request pipeline, discovery, custom ops, versioning |
| [03-policy-and-permissions.md](03-policy-and-permissions.md) | Policy model, evaluation, presets, auth, path/command scoping, hooks, limits, config layers, errors, threat model, observability |
| [04-builtin-modules.md](04-builtin-modules.md) | Catalog of built-in ops per namespace, groups, golden lists, behavioural contracts |
| [05-agents-api.md](05-agents-api.md) | OpenAI Agents API: counted scope, op family, wire behaviour, adapters, `llm:`, `AgentScope`, security, tests |
| [06-lazy-install.md](06-lazy-install.md) | Manifests, modes, tools directory, install algorithm, mirrors/offline, `easy-sandbox-server`, read-only FS and base image |
| [07-client-mirror.md](07-client-mirror.md) | Generated `ServerClient`, drift/contract tests, errors E3100-E3111 (one range), parity ledger, Node CLI |
| [08-template-building-ux.md](08-template-building-ux.md) | The `server:` template block, Python flavour, journeys, migration |
| [09-ai-codegen-usability.md](09-ai-codegen-usability.md) | Failure modes of AI-written config, the normative reference card, error catalog, simulation protocol |
| [10-implementation-plan.md](10-implementation-plan.md) | Layout, API/compat surface, work packages, freezes, tests, migration, docs list (en + zh), risks, reconciliation, definition of done |
| [reviews/](reviews/) | Round logs, the three independent reviews, and [v2.1-disposition.md](reviews/v2.1-disposition.md) (all 123 findings) |
| [spikes/](spikes/) | Executable prototype and checks (not the implementation) |

## 4. Decision log

| ID | Decision | Alternatives rejected | Why | Doc |
|---|---|---|---|---|
| D1 | **(amended v2.1)** Identity is a dotted lowercase op ID, grammar `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}$` (up to five segments), no ID is a prefix of another, reserved namespaces | flat names; method+path as identity; deeper nesting | one name for policy, audit, client, CLI; attribute tree stays navigable; 6-segment IDs from the first draft failed the grammar (F1.5) | 02 |
| D2 | Op references are an `OpRef` tree, **not** `str` subclasses | `OpId(str)` | `str` methods shadow verbs (`ops.custom.format`), F1.1 | 02 |
| D3 | HTTP bindings are metadata of `@op`; `POST /ops/{id}` always exists; legacy routes generated from the registry and tested equal to source | hand-kept route sets (`KEEP`-style) | drift; requirement 2 | 02, 04 |
| D4 | **(restated v2.1)** Default-deny policy; not-granted answers **404 `op.not_enabled`**, principal-filtered, byte-identical to unknown; 403 only when an allowed op's arguments are forbidden | 403 everywhere | no existence oracle (F2.3) | 03 |
| D5 | Deny beats allow; OR of allows, most specific wins and supplies limits; hooks are veto/narrow only and fail closed | hooks that can grant; AND-semantics | predictable composition; hooks cannot widen | 03 |
| D6 | **(amended v2.1, see D26)** **Explicit-only ops** are never matched by wildcard/group/effect/preset on the allow side | wildcard includes everything | `agents.codex.**` mounted install (S3.3) | 03 |
| D7 | Paths: `resolve_path` plus race-free `open_beneath` (`O_NOFOLLOW` walk, no `O_TRUNC` at open); policy before existence checks | canonicalise then open | TOCTOU exploit (F1.3); hardlinks documented as a limit | 03 |
| D8 | **(amended v2.1, see D27)** Commands: allowlist-first, typed tokens (`{path}`), `env_pass`/`env_set`, escape-capable lint, launcher not `preexec_fn`; the safest option is a named op | deny-lists; globs for paths; `env_allow` | F1.4, F1.6, S3.1, S3.2 | 03 |
| D9 | **(amended v2.1, see D34)** Limits: effective limit is the minimum; `limit.*` renders 413/429; transport bounds before reading | 403 for limits; per-op only | F2.4, S4.1 | 03 |
| D10 | **(amended v2.1)** Transport checks (step 0) precede authentication, which precedes alias resolution and every 404 | resolve first | route oracle (F4.2) | 02 |
| D11 | Config layers: Python, baked `server.json`, env author inputs, env restrictions, `policy.d`; the last two restrict-only; reload opt-in with an immutable snapshot; the runtime reads JSON only (YAML is compiled by the CLI) | YAML in the runtime; always-on reload | stdlib-only; auditability | 03 |
| D12 | **(amended v2.1, see D25, D35)** `presets.legacy_compat()` = what v1 exposed (loud lints, `system.env.set` only with an env switch) and v1 error renderer; applied only when nothing is configured; **no shipped rollback dispatcher** (strangler on the branch only) | no jail in legacy | silent widening (F2.1), 297 tests (F2.2), rollback (F4.4) | 03, 10 |
| D13 | **(amended v2.1, see D30, D31)** Agents: official wire shape at `/v1` plus `/agents/{adapter}/v1`; 4 ops per adapter plus the generic official ops; adapter selected explicitly (path/header/model-equals-adapter/default); real model names pass through | one coarse `agents` group; deep nesting | policy granularity; grammar | 05 |
| D14 | **(amended v2.1, see D38)** Tiering of the 47 official ops: 25 / 2 / 5 / 15 | claiming full parity | honesty; F4.3 | 05 |
| D15 | `llm:` (not `provider:`) for model endpoints; `*_env` references only; caller `base_url` forbidden | `provider:` | "provider" means sandbox backend elsewhere; credential safety | 05 |
| D16 | **(amended v2.1, see D28)** Universal auth (Bearer preferred, `X-Access-Token` alias; conflicting values rejected) | agents-only exception | the official SDK sends Bearer | 05 |
| D17 | Session ownership per principal, Idempotency-Key namespaced per principal | global keys | S3.4 | 05 |
| D18 | **(amended v2.1, see D32)** Lazy install from checksummed manifests (sha256 mandatory, no TOFU), `requires` DAG, modes `lazy|build|offline|off` (**no `auto`**), tools dir chain, flock plus atomic rename, install only **after** authorization, `serve` never installs at startup | `npm -g`, `curl | bash`, install POST route | supply chain, read-only FS, attribution | 06 |
| D19 | `easy-sandbox-server` subcommands: serve, init, describe, check-config, explain, prepare, doctor, lock, gen-client, healthcheck, sbom, version | ad-hoc scripts | one operator surface | 06 |
| D20 | **(amended v2.1, see D29)** Client mirror is **generated** from the catalog; dynamic fallback from `GET /ops`; no hidden traffic; errors E3100-E3111 only | hand-written client; E8xxx; E9xxx | drift; E8000-E8030 belongs to providers (F2.5) | 07 |
| D21 | Custom commands are `custom.<name>`; `commands.run` is the shell op | `server.commands.*` for both | clash (F2.8) | 04, 07 |
| D22 | Declarative `custom:` ops in YAML with intrinsic path roots (`paths={param: root}`) | arbitrary code in YAML | AI-safe authoring (S3.5) | 02, 08 |
| D23 | **(amended v2.1, see D35)** Public API and positional signatures of `SandboxServer`/`start` preserved; new parameters keyword-only; shims keep v1 module names importable | breaking change | existing deployments (F4.5) | 10 |
| D24 | Contract/drift tests live at the repository root, using the real `openai` 3.29.0 wheel as oracle (isolated venv) | tests inside one package | need both packages; oracle isolation | 10 |
| D25 | **Strangler migration**: baseline-and-port first (WP-A), the v1 dispatcher stays until the v2 pipeline passes the v1 fixtures and the full server suite, the in-flight `PolicyEngine` is stage 1, **compat gate on every WP** (collected count not below the recorded base, 308 at HEAD) | big-bang rewrite behind a legacy snapshot | IF-01, IF-02, IF-08, IF-09 | 10 |
| D26 | **Explicit-only semantics**: allow side = exact id only; deny side = every selector reaches them; set = admin-effect ops, `core.reload`, `system.env.set`, `terminal.create`, `process.signal`, `agents.<a>.install`, `agents.<a>.sessions.create`; `system.env.set` writes an overlay only and is never in a group or preset; ops without `effects=` default to `admin` | explicit-only for all `commands.*`/`files.*` | IS-C2, IS-P4, B-3 | 03 |
| D27 | **Scope-required**: an allow of any op with a path/command/url/agent parameter needs its scope (`403 policy.scope_required` + lint error); escapes are `*.anywhere/unrestricted(unsafe=True)`; deny is at least as strong as allow (canonical paths, every anchor, descendants, `command` xor `argv`, linear glob matcher, non-removable system deny list) | `ctx.paths` fallback; documenting bare grants | IS-P1..P9, IS-F1, B-14 | 03 |
| D28 | **Fail-closed authentication**: unset/empty `token_env`, short or inline secrets and the id `anonymous` refuse to start; open mode refused off-loopback and with exec ops; `Authorization` wins over `X-Access-Token`, different values -> 401; rate limit per credential fingerprint | warn-and-open | IS-A1, IS-A7, IF-17, IF-18 | 03 |
| D29 | **ONE client error range**: server plane `E3100-E3111` (in-flight `E9000-E9005` -> `E3100-E3105`, new `E3106-E3111`); providers keep `E8000-E8030`; in-flight class names/attributes kept, `.code` stays the E-code | E9xxx; E8xxx | IF-10, IF-11 | 07 |
| D30 | **Explicit adapter selection**: path `/agents/<a>/v1`, header `X-EBX-Adapter`, `model` equal to an adapter name, `agents.default`, the only mounted adapter, else `400 agents.adapter_required`; real model names pass through | adapter inferred from any `model` string | C-3 | 02, 05 |
| D31 | **Agent sessions are exec-effect ops** needing an `AgentScope`; generic `agents.sessions.create/send_event` also require the adapter op (two-level gate); install is a separate decision (`deny(install)` is absolute) | agents outside the policy model | IS-G1, IS-L2 | 03, 05, 06 |
| D32 | **Lazy install on read-only/FC**: lock-free fast path, lock in a writable dir after the marker check, slow install -> `202` + job id (20 s wait), build-time `prepare` recommended on FC, PEP 668-safe build snippet, noexec/network probes, state and tools dirs never under `/tmp` | 10-minute blocking default; lock beside the marker | IF-20..24, IS-L1, C-11 | 06 |
| D33 | **Process and state hardening**: `PR_SET_DUMPABLE=0`, `RLIMIT_CORE=0`, env from a startup snapshot, state dir 0700 owned by the server user, protected from every path scope | `/tmp` defaults | IS-C6, IS-L1 | 03 |
| D34 | **Transport order** (step 0): socket timeouts, request-line target checks, Host/Origin allowlists, JSON content type, size before body, bounded pre-auth pool with a reserved health slot | pipeline-only checks | IS-A2, IS-A3, IS-A8, IF-19 | 02, 03 |
| D35 | **0.3.0 cut list and version**: no 2.0 jump (0.3.0 lockstep, version ADR), no shipped rollback dispatcher or alias window, per-adapter ops kept, all five adapters ship (three experimental) | 2.0.0; collapse per-adapter ops | IF-06, IF-29, IF-30 | 10 |
| D36 | **Package naming**: handlers live in `builtin/`; `ops` is only the `OpRef` tree | `ops/` subpackage | IF-03 | 02, 10 |
| D37 | **Parity ledger**: every op has a client counterpart (generated tree) or a documented asymmetry A1-A7; `tests/contract/client_parity.json` | prose parity table | IF-27 | 07 |
| D38 | **Tiering and OpenAI wire**: 25 implemented / 2 reserved / 5 refused / 15 not planned; list envelope, `event_id`/`turn_id`, 202 `events.create`, idle-open stream, artifacts tier 1, vaults carry tool credentials; `/v1/responses` out of 0.3.0 | claims of full parity | T-1..4, C-1..17 | 05 |
| D39 | **Strict config**: unknown keys (any depth) in `server:`/`server.json` are errors with did-you-mean; selector typos raise at construction (`strict=True`); schema version in `server.json`; presets take one `root=` keyword | fail-open `extra="ignore"` | IF-31, B-2, B-8 | 08, 03 |


## 4a. v2.1 changes (changelog)

Design v2.1 revises this set **in place** after three independent adversarial reviews ([security](reviews/independent-security.md): 41 findings, [UX and AI](reviews/independent-ux-and-ai.md): 51, [feasibility](reviews/independent-feasibility.md): 31) and a read of the in-flight code now in the tree
(`policy.py`, `guard.py`, `runtime.py`, `agents/` in the server SDK; `providers/` in the client SDK, whose `E8000-E8030` stays). Every finding has a row in [reviews/v2.1-disposition.md](reviews/v2.1-disposition.md)
(116 accepted, 4 partial, 2 rejected, 1 deferred). New decisions D25-D39; amended: **D1, D4, D6, D8, D9, D10, D12, D13, D14, D16, D18, D20, D23** (marked in the log).

| Area | What changed | Docs | Executable evidence |
|---|---|---|---|
| Security (2 critical, 16 high, all else) | fail-closed auth and open-mode refusals; `system.env.set` explicit-only/overlay-only; **scope-required** allows; deny parity (relative paths, descendants, explicit-only ops, `command` xor `argv`); agent sessions are exec ops with `AgentScope`; state dirs out of `/tmp` and protected; `PR_SET_DUMPABLE`; Host/Origin/Content-Type/timeouts/bad-target transport; strict `UrlScope`; linear glob matcher; `*at()` mutations; frozen hook views | 02 s6, 03 s2-s15, 05 s8, 06 s5 | `spikes/independent-security/run_all.py --strict`: **41 held, 0 vulnerable**; `tests_v21.py` (53) |
| OpenAI wire | list envelope, `event_id`/`turn_id`, full Agent object, 202 `events.create`, idle-open stream, explicit adapter selection (real model names pass through), artifacts tier 1, subagent behaviour, vault wording, `environments.files` ids; tiering **25/2/5/15**; migration table for `codex-agent-api`; `/v1/responses` out of 0.3.0 | 04 s11, 05 s1-s5, s13 | `agents_sdk_check.py` (real `openai` 3.29.0, 38 checks); card examples fixed |
| Migration | **strangler**: WP-A baseline-and-port first, compat gate on every WP, disjoint ownership + integrator, `ops/` -> `builtin/`, new WPs 10b/10c/10d, 0.3.0 cut list, no version jump | 10 | `tests_catalog.py` (41 legacy routes + known in-flight extras) |
| Lazy install | lock after marker check (writable dir), 202 + job instead of a 10-minute wait, `prepare` recommended on FC, PEP 668-safe build snippet, noexec/network probes, resolver trust | 06 | `tests_install.py` (11) |
| Errors | ONE client range E3100-E3111, in-flight E9xxx mapped, wire-code table, `Authorization` vs `X-Access-Token` precedence | 03 s5, 07 s4 | `tests_v21.py` |
| Alignment | parity ledger for all 105 ops (+ `custom.<name>`, `ext.*`), asymmetries A1-A7, `Sandbox.server` dual use | 07 s5-s6 | `tests_parity.py` |
| AI codegen | card rewritten against the real facade (100 columns, `root=` presets), 8 sample template files executable | 08, 09 | `templates/run_all.py`, `card_imports.py` |
| Hygiene | scratch-path literals removed from this set and the spikes | - | `scripts/check-no-local-paths.sh` |

## 5. Numbers that other documents may quote

| Fact | Value | Source of truth |
|---|---|---|
| Official Agents API operations | **47** (implemented 25, reserved 2, refused 5, not planned 15) | [05](05-agents-api.md) section 4; `catalog.OFFICIAL_47` |
| Per-adapter op family | 4 ops (`run`, `install`, `sessions.create`, `sessions.send_event`); five adapters (codex, claude_code stable; qwen_code, cursor, qoder experimental) | [05](05-agents-api.md) section 3 |
| Default registry size | **105 ops** (50 non-agent + 3 generic + 32 official + 5 x 4 adapter) | [04](04-builtin-modules.md) section 11; `spikes/tests_catalog.py` |
| Legacy routes preserved | 41 | [04](04-builtin-modules.md); `spikes/tests_catalog.py` |
| Existing server tests that must pass unmodified | **308 collected** at HEAD (recorded by WP-A as the base; gate on every WP) | [10](10-implementation-plan.md) section 3.1 |
| Client error family | **E3100-E3111 only** (providers E8000-E8030; no E9xxx) | [07](07-client-mirror.md) section 4 |
| Independent findings and dispositions | 123 (116 / 4 / 2 / 1) | [reviews/v2.1-disposition.md](reviews/v2.1-disposition.md) |
| Release number | 0.3.0, lockstep (no 2.0 jump) | [10](10-implementation-plan.md) section 6.7 |
| Work packages | WP-A, WP-0 .. WP-13 (WP-4a-d, WP-7a-e, WP-10b/10c/10d) | [10](10-implementation-plan.md) section 3.3 |

## 6. How the reviews were performed (read this before trusting them)

The brief asked for multi-agent adversarial planning. **No subagent tool was available**, so:

* Each round is a **sequential pass by the lead author wearing one lens at a time** (feasibility, completeness, DX, AI-consumer, security, backward compat, client mirror).
* Wherever a claim could be executed, it was: the spike (`spikes/`) is stdlib-only reference code with 36 unit checks, a catalog test against the pristine legacy source,
  three exploit scripts and eight AI-consumer scenarios (59 checks).
* The **AI-consumer** runs were the author re-reading only the reference card; they are weaker than an independent model run, which is therefore a release gate (WP-11).
* Round files were assembled from the author's working notes at the end of the design; finding IDs are stable and cited in the docs (`F1.1`, `S3.3`, ...). The assignment of a
  finding to a round follows the order of discovery as recorded; the evidence column points at checks that can be re-run now.
* The loop stopped when round 5, run on the final documents with every check re-executed, produced no unresolved material finding. **That conclusion was wrong in two ways** (the independent reviews found 2 critical and 16 high security issues, and 2 blockers in the plan that the author's own rounds missed); v2.1 therefore treats the independent reviews as authoritative and keeps them as release evidence.

| Round | File | Material findings | Outcome |
|---|---|---|---|
| 1 | [feasibility and security](reviews/round-1-feasibility-and-security.md) | F1.1, F1.3, F1.4, F1.5, F1.6 | resolved |
| 2 | [compat, completeness, DX](reviews/round-2-compat-completeness-dx.md) | F2.1-F2.6, F2.8 | resolved |
| 3 | [security and AI-consumer](reviews/round-3-security-and-ai-consumer.md) | S3.1-S3.5, A3.1 | resolved |
| 4 | [pipeline, transport, mirror](reviews/round-4-pipeline-transport-and-mirror.md) | S4.1, F4.2-F4.5 | resolved |
| 5 | [full regression](reviews/round-5-full-regression.md) | none (5 hygiene items fixed) | **clean; stop** (of the author's own process) |
| I-1 | [independent security](reviews/independent-security.md) | 41 (2 critical, 16 high) | all PoCs HELD after v2.1 (1 partial, 1 deferred) |
| I-2 | [independent UX and AI](reviews/independent-ux-and-ai.md) | 51 (16 high) | accepted; B-14 fixed differently |
| I-3 | [independent feasibility](reviews/independent-feasibility.md) | 31 (2 blocker, 12 high) | accepted; IF-29 rejected, IF-10/IF-30 partial |
| v2.1 | [disposition](reviews/v2.1-disposition.md) | 123 rows | counts in section 4a |

## 7. Known limitations and open questions

* Not exercised: real agent CLIs, network installs on the Alibaba base image, the Node CLI generation. The `openai` SDK (3.29.0) was verified against the **spike's echo adapter**, not a real CLI. `qoder`, `qwen_code` and `cursor` are experimental profiles that could not be verified.
* Open after v2.1: the LLM key remains readable by the agent child (`llm.proxy` deferred, IS-S1); `npm-lock` host enforcement is a manifest-review property (IS-L4); `/home/user` persistence and egress on the platform are unknown (`doctor --network`); zh translations of 04 and 07-10 of this set; the independent AI-consumer run is periodic, not blocking.
* Documented residual security limits: hardlinks, privileges of allowed programs, agents not confined by path/command scopes ([03](03-policy-and-permissions.md) section 12).
* Open questions that do not block starting work: [10](10-implementation-plan.md) section 8.
