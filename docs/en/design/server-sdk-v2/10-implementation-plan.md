# 10 - Implementation plan (v2.1)

> Part of [Server SDK v2](README.md). Everything an implementer needs without guessing: the **strangler** migration, final layout, public API and
> compatibility surface, independently assignable work packages (owner, exclusive files, dependencies, tests, **E2E gate**, `.agents` note), the
> **0.3.0 cut list**, freezes, test strategy and repository gates, migration notes, docs list (en + zh), risks, and the **reconciliation instructions** for
> the in-flight workers (section 9). Rewritten in v2.1 after the independent feasibility review (31 findings: IF-01..IF-31; see
> [reviews/v2.1-disposition.md](reviews/v2.1-disposition.md)).

## 0. What changed from the first plan

| Was | Is (v2.1) | Finding |
|-----|-----------|---------|
| Rewrite behind a "legacy preset" snapshot; WP-5 compat late (M2) | **Strangler**: v1 dispatcher stays until the v2 pipeline passes the v1 fixtures and the full server test suite; the in-flight `PolicyEngine` is stage 1; compat is a **standing gate on every WP** | IF-01, IF-02 |
| No WP for the ~16k in-flight lines; no green baseline | **WP-A baseline-and-port first**: commit the in-flight state with a green suite, record the base counts, add the import test (the `routes_agents` circular import was observed once), generate the v1 fixtures from HEAD | IF-08, IF-09, IF-04 |
| `ops/` subpackage next to the `ops` tree | the handler package is **`builtin/`**; `ops` is only the `OpRef` tree; import test | IF-03 |
| Overlapping file ownership; shared files owned by WP-0 | disjoint ownership map (3.5), an **integrator** role owns generated/shared files and the merge queue | IF-12 |
| WP-10 too big, missing client-side build path | split into 10 (codegen), **10b (template compile + docker build + decorator + agent builtin)**, **10c (`Sandbox.server*` + `ServerClient`)**, **10d (Node CLI, downstream)** | IF-13, IF-28 |
| Missing edges | WP-1 -> 6/9/13, WP-5 -> 13, client mirror starts at M1 | IF-14 |
| Release gate omitted the repo gates | DoD lists ruff, mypy, hygiene, repo-health, packaging/server-only/version tests, en/zh parity, `make gen-check` | IF-15 |
| Version `2.0.0` | **no jump: 0.3.0 lockstep** (ADR, section 6.7); E9xxx and E8xxx for the server plane dropped: **E3100-E3111** | IF-06, IF-10 |
| Everything ships in the first release | explicit **0.3.0 cut list** (3.2) | IF-30 |

## 1. Strangler migration and final code layout (server-sdk)

### 1.1 Stages (each stage ends green on the compat gate)

| Stage | State | Done when |
|-------|-------|-----------|
| **S0** (WP-A) | the in-flight tree committed as the baseline: v1 dispatcher (`app.py`, `router.py`, `routes_*.py`), in-flight capability engine (`policy.py`, `guard.py`, `runtime.py`), `agents/`, client `ServerClient` | `pytest server-sdk/tests` green at the recorded counts; v1 fixtures generated from HEAD; `import easy_sandbox.server` test; lint/type gates green |
| **S1** (WP-0, 2, 3) | `core/` registry + `Policy` + guards land **beside** the old code; every v1 route is also registered as an op whose handler calls the existing `routes_*` function (`builtin/<ns>.py` wrappers); the in-flight `PolicyEngine` and the new `Policy` are bridged (`Policy.from_engine`) so one decision source answers both | v1 routes unchanged byte-for-byte; ops callable through `POST /ops/{id}` |
| **S2** (WP-1) | the v2 pipeline serves `POST /ops/{id}`, `/capabilities`, the new native and `/v1` routes; the legacy routes are still dispatched by the v1 dispatcher but consult the same `Policy` | v1 replay fixtures + full suite green with the pipeline flag on in CI |
| **S3** (WP-5, standing) | legacy routes switch to the v2 pipeline with the **compat renderer** (v1 statuses/messages under `legacy_compat`); handlers move from `routes_*` into `builtin/*` one namespace at a time (WP-4a..d) | every WP keeps the gate green; the old `routes_*` helper names stay importable |
| **S4** (release) | the v1 dispatcher is deleted; only the pipeline remains (the flag `EBX_SERVER_PIPELINE` exists on the branch only; there is **no shipped rollback dispatcher**, IF-30) | gates of section 5 |

### 1.2 Mapping of in-flight files (approx. 12.6k lines in `server-sdk`, plus the client work) to the target

| In-flight file | Lines | Target | Owner WP | Notes |
|---|---|---|---|---|
| `server/policy.py` | 830 | `policy/` package (`engine.py`, `model.py`, `loader.py`, ...) | WP-2 | `policy.py` and `policy/` cannot coexist: WP-2 converts it in one PR and `policy/__init__` re-exports every name the existing tests import |
| `server/guard.py` | 230 | `guards/{paths,commands,env}.py` | WP-3 | same re-export rule; the spike's guards (`spikes/ebxp/guards.py`) are the reference |
| `server/runtime.py` (`PolicyEngine`, buckets, audit, discovery) | 708 | `core/{dispatch,limits,audit}.py`, discovery in `core/http.py` | WP-1 | stage-1 engine; extract `limits.py`/`audit.py` first |
| `server/app.py`, `router.py`, `registry.py`, `routes.py`, `types.py`, `_coerce.py`, `_compat.py` | ~1.9k | stay importable (v1 names); become `compat/` thin modules at S4 | WP-5 | |
| `server/routes_{files,process,pty,system,devtools,browser}.py` | ~3.8k | handlers move to `builtin/{files,process,terminal,system,devtools,browser}.py`; the `routes_*` names keep exporting helpers used by tests | WP-4a..d | one namespace per PR |
| `server/agents/{runtime,store,events,config,procenv,redact,errors,wire_sessions}.py`, `adapters/*` | ~3.6k | `agents/` (same place); `wire_sessions.py` -> `wire_openai.py`; `config.py` -> `llm`/`AgentScope` mapping | WP-6, WP-7a..e | adopt the queue/replay/idempotency semantics; add the 47-op wire (spike `agents_wire.py` is the reference) |
| `server/contract.py` + server capabilities | 40 | `core/http.py` discovery (union body, IF-26) | WP-1 | |
| client `api/server_client.py` (hand-written, ~1.2k), `models/server.py`, `models/errors.py` (E9xxx) | | generated `api/server/`; alias module `api/server_client.py`; E31xx | WP-10c | aliases of old method names, 07 section 1 |
| client `models/template.py` (`validate_server_block`, `extra="ignore"`) | | strict v2 vocabulary | WP-10b | 08 section 2 |

### 1.3 Final layout (target of S4)

```
server-sdk/src/easy_sandbox/server/
  __init__.py              # public surface + compat re-exports (section 2)          [integrator]
  __main__.py  _version.py  py.typed
  core/                    # STDLIB ONLY
    ids.py refs.py         # id grammar {1,4}, OpRef/OpTree (the `ops` object), alias table      [WP-0]
    registry.py context.py errors.py                                                           [WP-0]
    dispatch.py router.py http.py audit.py limits.py config.py reload.py                       [WP-1]
  policy/                  # model.py engine.py selectors.py presets.py hooks.py lint.py explain.py loader.py     [WP-2]
  guards/                  # paths.py commands.py env.py launcher.py urls.py harden.py                          [WP-3]
  builtin/                 # (was `ops/`, IF-03) one module per namespace; registers on import; imported lazily
    core.py files.py commands.py process.py terminal.py system.py devtools.py browser.py custom.py ext.py declarative.py
  agents/                  # runtime.py store.py events.py wire_openai.py wire_native.py resolver.py ops.py   [WP-6]
    adapters/              # base.py command.py codex.py claude_code.py qwen_code.py cursor.py qoder.py       [WP-7a..e]
  install/                 # manifest.py resolver.py lock.py fetch.py extract.py progress.py jobs.py           [WP-8]
    drivers/ tarball.py npm_lock.py system.py (0.3.0) pip_hashes.py playwright.py (later)                    [WP-8]
    manifests/ codex/ claude_code/ qwen_code/ cursor.json node-runtime.json ...                              [WP-7*]
  cli/                     # main.py serve.py describe.py check_config.py explain.py prepare.py doctor.py healthcheck.py  [WP-9]
  catalog/                 # operations.json openapi.json server_schema.json _ops.pyi (generated, committed)   [integrator via `make gen`]
  compat/                  # v1 shims (app, router, registry, routes*, types, _coerce, _compat)                 [WP-5]
```

`easy_sandbox.server.ops` is the `OpTree` object defined in `core/refs.py` and re-exported by `__init__`; **no module or package is named `ops`** (IF-03). `server/{app,router,registry,routes*,types,_coerce,_compat}.py` remain importable at
their old paths. `policy.py`/`guard.py`/`runtime.py` flat files disappear only when WP-2/3/1 convert them (section 1.2).

Dependencies: runtime `websockets>=12` stays (PTY) but is imported lazily inside `builtin/terminal.py`; `core/`, `policy/`, `guards/`, `install/`, `agents/` import only the stdlib (import-linter test; `tests/test_server_only_import.py`
and `tests/test_packaging.py` already enforce related rules and must stay green). Optional extras: `browser` (playwright), `yaml` (PyYAML for `init`/`describe --yaml`; the runtime reads JSON only), `dev`.

client-sdk additions: `easy_sandbox/api/server/{__init__,client,_generated,capabilities,transport}.py` (+ alias module `api/server_client.py`), `easy_sandbox/ops.py` (generated tree), errors E3100-E3111 in `models/errors.py`
(07 section 4), `models/template.py` strict `server:` validation (generated `models/_server_config.py`), `Sandbox.server` namespace. cli (Node) additions: downstream, WP-10d.

## 2. Public API surface and compatibility

`easy_sandbox.server.__all__` (documented list; every name below importable from the package root):

v1 (unchanged): `SandboxServer start enable_builtin disable_builtin is_builtin_enabled get_enabled_builtins CommandArg CommandRegistry RegisteredCommand
default_registry ServerRequest ServerResponse SSEResponse RouteTable RouteInfo CapabilityGroup default_table PtySession PtySessionManager pty_session_manager
start_pty_server`.

v2 (new, all present in the spike facade `ebxp.api` and in the card): `ops op Registry Policy presets PathScope CommandScope UrlScope AgentScope Limits Deny Narrow Principal PolicyError ConfigError from_config configure OpError Stream Bytes`.

**D23 restated (amended in v2.1).** Public names and the **positional** signatures of `SandboxServer` and `start` are preserved; every new parameter is keyword-only. Two *defaults* intentionally change and are documented
as breaking-by-design for an unreleased line: `start(host=...)` keeps `"0.0.0.0"` positionally but **open mode (no auth) is refused on a non-loopback bind** (`config.open_non_loopback`) and when exec/admin ops are mounted
(`config.open_exec`), unless `allow_open=True`; a policy that does not mention `core.health` still mounts it.

```python
SandboxServer(host="0.0.0.0", registry=None, route_table=None, pty_port=None, *, policy=None, preset=None, root=None,
              config=None, authenticate=None, tokens=None, strict=True, state_dir=None, verbose=False, allow_open=False)
start(port=9000, host="0.0.0.0", registry=None, *, policy=None, preset=None, root=None, config=None, allow_open=False,
      allowed_hosts=(), allowed_origins=(), block=True)
SandboxServer.serve(port=9000)   .call(op_id, principal=None, **args)   .explain(op, args, principal)   .check()   .authenticate(headers)   .auth_token (the legacy single token)
```

(The spike facade is shaped for tests: `SandboxServer(policy, ...)`, `start(policy, ...)` returning `(server, httpd)`; the shipped signatures above are the authority and the card's calls work with both.)

## 3. Work packages

### 3.1 Rules for every WP

1. **Owner**: one agent or person per WP; the owner holds the files listed in 3.5 exclusively. Shared and generated files (`__init__.py`, `pyproject.toml`, `Makefile`, `catalog/*`, generated client/TS files, `CHANGELOG.md`, `docs` indexes) belong to the **integrator**, who merges through a PR queue and runs `make gen`; a WP asks for a change by PR against the integrator's queue, never by editing the file in its own branch.
2. **Compat gate (every WP, every PR)**: `cd server-sdk && pytest tests` passes with the **collected count not below the base recorded by WP-A** (`tests/BASELINE.json`; 308 collected at HEAD, one environment-dependent test needs `pip`), **no existing test file is edited or moved** (tests may be added; a change needs integrator approval and a note in the PR), the v1 replay fixtures pass, `tests/test_packaging.py`, `tests/test_server_only_import.py` pass.
3. **E2E gate (repo Definition of Done, `.agents/notes/DEFINITION-OF-DONE.md`)**: a WP is done only when verified against real components (a real listener and real client/`openai` package; real CLI binaries and real network where the WP needs them) and the run is recorded in `.agents/evidence/verify/YYYY-MM-DD-<topic>.md`; a WP that cannot reach a real component records **Blocked E2E** as the DoD describes (never "done with mocks").
4. **`.agents` note per WP** (DoD item 4): an ADR/note under `.agents/notes/proposed/<architecture|feature|process>/YYYY-MM-DD-<slug>.md` (moved to `implemented/` when it lands), docs en + zh, and a `CHANGELOG.md` `[Unreleased]` fragment (integrator merges).
5. **Spike parity**: where a spike exists (`spikes/`), its checks are ported as tests of the WP; the spike remains the executable reference until the WP's gate is green.

### 3.2 The 0.3.0 cut list (IF-30, requirement 7)

| Ships in 0.3.0 | Later (not blocking; reserved in the design) |
|---|---|
| Dotted op IDs, `ops` tree, `@op`, dotted IDs mirrored on the generated Python client (`srv.files.list`, ...) and the parity ledger | TypeScript/OpenAPI client generation beyond `openapi.json` export (WP-10d may ship after) |
| Group switches (`group:`, `enable_builtin`) **and** fine-grained allow/deny, selectors, effects, presets (with `legacy_compat`) | rule `shadowing` lint depth, `explain` UI polish |
| Path scopes (`PathScope`, deny parity, race-free opens), command scopes (`CommandScope`, typed tokens, launcher), `UrlScope` (literal hosts + leading `*.` label) | `UrlScope` with arbitrary globs/CIDR lists beyond literal-plus-wildcard-label |
| Simple custom hooks (veto/narrow only), per-principal limits, audit to stderr/file | hooks with external calls, OTel exporter wiring beyond the existing facade |
| Auth hardening (fail-closed tokens, precedence, rate limit, open-mode refusals, transport hardening, `PR_SET_DUMPABLE`) | hot reload (`SIGHUP`), operator `policy.d` drop-ins beyond restrict-only env switches |
| Built-in **agents API**: official 47-op tiering **25 implemented**, adapters **codex, claude_code** (stable) and **qwen_code, cursor, qoder** (experimental, flagged) | `/v1/responses`, `agents.environments.files.*`, subagent ops (refused), vaults/credentials/templates (not planned) |
| Lazy install: manifests `tarball`, `npm-lock`, `system`; modes `lazy|build|offline|off`; 202 job protocol; `prepare` at build time; PEP 668 safe build snippet | manifest types `pip-hashes`, `playwright-browser` (browser ops keep the current in-image Playwright), `llm.proxy` key injection, `sbom` |
| CLI: `serve healthcheck check-config describe explain prepare doctor` | `init`, `gen-client` (internal `make gen` only), `lock` (maintainer script), `sbom` |
| Template `server:` compile with strict keys, builder injection (PEP 668), declarative decorator integration, `Sandbox.server` surface | Node CLI `ebx server ...` consuming `operations.json` (WP-10d, separate release train) |
| Errors E3100-E3111 | zh translations of 04, 07-10 of this set (README, 01-03, 05, 06 first) |
| **Dropped** from the first draft: rollback dispatcher `EBX_SERVER_LEGACY_DISPATCH`, a shipped `compat/` rollback package, the two-minor alias window for unreleased names, collapsing per-adapter ops (rejected, IF-29) | |
| Independent AI-consumer run: **periodic, non-blocking** (the scripts are the oracle) | |

### 3.3 Work package table (hand-off ready)

Owner = a role to assign to exactly one agent/person. "Tests" = new tests the WP adds (the compat gate applies to all). "E2E gate" = what must run against real components. ".agents note" = slug and type of the ADR/note (DoD item 4).

| WP | Title / owner role | Owns (exclusive; see 3.5) | Depends on | Tests (new) | E2E gate | `.agents` note |
|----|--------------------|---------------------------|------------|-------------|----------|----------------|
| **WP-A** | Baseline-and-port / *baseline engineer* | `tests/BASELINE.json`, `tests/fixtures/v1_replay/*`, `tests/test_import_surface.py`, lazy-import fix for the `agents` group in `routes.py`/`__init__.py`, repo gate fixes in the in-flight files | - (FIRST; blocks all) | import test (`import easy_sandbox.server` and `...server.agents` in a clean interpreter), baseline counts, v1 fixtures generated from HEAD (one request/response per legacy binding incl. error shapes and the `traversal` message, IF-04), `ruff`/`mypy`/hygiene clean | start the HEAD server on loopback, replay all fixtures with the real client `ServerClient`; run `make ci` | `proposed/process/<date>-server-v2-baseline-and-port.md` |
| **WP-0** | Core model / *core engineer* | `core/{ids,refs,registry,context,errors}.py`, catalog generator under `core/catalog_gen.py`, `tests/test_core/*` | WP-A | grammar `{1,4}`/prefix/alias; `ops` tree incl. `ops.custom.format`; import test (`ops` is an `OpTree` after importing all `builtin.*`); schema generation; effects default `admin`; registry freeze message; name mangling table (IF-05); catalog/openapi emit; import-time budget | `python -m easy_sandbox.server describe --json` in a clean venv equals the committed catalog | `proposed/architecture/<date>-server-operation-model.md` |
| **WP-1** | Dispatch + HTTP (strangler S2) / *pipeline engineer* | `core/{dispatch,router,http,audit,limits,config,reload}.py`, `tests/test_dispatch/*` | WP-0; **WP-2/WP-3 interfaces (frozen at M1)**; must run before WP-6/9/13 | step-0 transport order (timeouts, bad target, host/origin, content-type, size), 401 before 404, one `op.not_enabled` body, rate limit by credential fingerprint, reserved health slot, discovery union body (IF-26), SSE/NDJSON/bytes, wire renderers, concurrency caps; **v1 replay fixtures with the pipeline flag on** | real listener on loopback: `curl`, the real `ServerClient`, a slow-loris script and the DNS-rebinding PoC (`spikes/independent-security`) | `proposed/architecture/<date>-server-request-pipeline.md` |
| **WP-2** | Policy engine / *policy engineer* | `policy/*`, `tests/test_policy/*`, `tests/golden/{groups,presets}.json` | WP-0, WP-A | deny parity (every selector, explicit-only ops, relative paths, descendants), scope-required, explicit-only allow side, presets with `root=`, `legacy_compat` + `legacy_diff`, loader strict keys, layering (restrict-only), lint set (03 section 15.5), `explain` parity, hook return types; port `spikes/tests_proto.py`, `tests_v21.py` | `check-config --strict` on the eight sample templates (`spikes/templates/t1..t8` as config fixtures) | `proposed/architecture/<date>-server-policy-model.md` |
| **WP-3** | Guards / *guards engineer* | `guards/*` (incl. `urls.py`, `harden.py`), `tests/test_guards/*`, `tests/bypass/*` (guard cases) | WP-A | port all of `spikes/ebxp/guards.py` checks, `attack1-3`, **all 41 independent-security PoCs** (`run_all.py --strict` equivalent as `tests/bypass/test_independent_security.py`), fuzz for glob matcher/`resolve_path`/`UrlScope` parser, launcher rlimit, FIFO/hardlink/parent-swap race tests | run the PoC suite against the real server process (not the spike) with `PR_SET_DUMPABLE` verified through `/proc/<pid>/environ` as another user | `proposed/architecture/<date>-server-guards.md` |
| **WP-4a** | Ops: files / *files engineer* | `builtin/files.py`, `tests/test_ops/test_files.py` | WP-0, 2, 3, 1(S2) | legacy bodies byte-compatible (fixtures), `files.watch`, `*at()` mutations, list/search re-check, limits, `download_stream`/`upload_stream` | real files in a temp tree, via the real client | `proposed/feature/<date>-server-files-ops.md` |
| **WP-4b** | Ops: commands/process/terminal / *process engineer* | `builtin/{commands,process,terminal}.py`, `guards/launcher.py` use | WP-0, 2, 3 | launcher exec, bounded output, process ownership, signals allowlist, scope-required for `cwd`, PTY ticket (15.8) | real processes and a real PTY WebSocket client | `proposed/feature/<date>-server-exec-ops.md` |
| **WP-4c** | Ops: core/system/custom/ext/declarative / *platform engineer* | `builtin/{core,system,custom,ext,declarative}.py` | WP-0, 2 | `server.custom:` compile, `ext.*` default admin, `system.env.set` overlay-only, discovery ops, name mangling | real `POST /commands/{name}` for mangled names | `proposed/feature/<date>-server-core-system-ops.md` |
| **WP-4d** | Ops: devtools/browser / *tools engineer* | `builtin/{devtools,browser}.py` | WP-0, 2, 3 (`UrlScope`) | `UrlScope` use, languages scope, lazy Playwright import, `fetch` re-check of resolved addresses | real git repo; browser E2E only where Playwright exists (else Blocked E2E) | `proposed/feature/<date>-server-devtools-browser-ops.md` |
| **WP-5** | Compat layer (**standing gate**, not a late WP) / *compat engineer* | `compat/*`, `tests/test_compat/*`; owns the gate scripts | WP-A, runs through the whole project | legacy name mangling, `RouteTable.route` -> `ext.*`, `CommandRegistry` -> `custom.*`, legacy renderer, `legacy_compat`, replay fixtures v1 vs v2, import paths | replay all fixtures against the HEAD checkout and the new build in one job | `proposed/process/<date>-server-v2-compat-gate.md` |
| **WP-6** | Agents runtime / *agents engineer* | `agents/{runtime,store,events,wire_openai,wire_native,resolver,ops}.py`, `agents/adapters/{base,command}.py`, `tests/test_agents/*` | WP-0, 2, 1; WP-A (port in-flight) | the 47-op wire (25/2/5/15), list envelope, `event_id`/`turn_id`, 202 `events.create`, idle-open stream, adapter selection (path/header/model/default/only), two-level gate, `AgentScope` required, idempotency mismatch, ownership; **port `spikes/agents_sdk_check.py` as `tests/oracle/test_openai_oracle.py`** | the real `openai` package (isolated venv job) against the real server with a fake agent binary | `proposed/feature/<date>-server-agents-api.md` |
| **WP-7a..e** | Adapters (codex, claude_code, qwen_code, cursor, qoder; one owner each) / *adapter owners* | `agents/adapters/<name>.py`, `install/manifests/<tool>*`, `tests/fakes/fake_<tool>` | WP-6, WP-8 | recorded-transcript parser tests, permission mapping, refusal when unsupported, `tested_versions`; experimental flag for qwen_code/cursor/qoder | real CLI binary + a real prompt where available (codex, claude_code); others record **Blocked E2E** | `proposed/feature/<date>-server-adapter-<name>.md` |
| **WP-8** | Lazy install / *install engineer* | `install/*`, `install/drivers/*`, `tests/test_install/*` | WP-0 | port `spikes/tests_install.py`; lock-free fast path, writable-dir lock, 202 job, PEP 668 build, noexec/network probes, state-dir rules, tool resolver trust (IS-L3), checksum/kill -9/offline/read-only/unauthorized-never-fetches | real build of an image from the base image with `prepare`, then a read-only-rootfs run; one real first-use install over the network | `proposed/architecture/<date>-server-lazy-install.md` |
| **WP-9** | CLI / *cli engineer* | `cli/*`, `__main__.py`, `tests/test_cli/*` | WP-2, WP-8 (prepare/doctor), WP-1 (healthcheck stdlib fast path, IF-25) | `serve healthcheck check-config describe explain prepare doctor`, exit codes, `prepare --dry-run` equals derived set, `doctor` fixtures, `healthcheck` imports only the stdlib | run in the real base image as `start_cmd`/`ready_cmd` | `proposed/feature/<date>-easy-sandbox-server-cli.md` |
| **WP-10** | Codegen + drift / *codegen engineer* | `core/catalog_gen.py` consumers, `scripts/gen_*`, `tests/contract/{cases.py,client_parity.json}`, `tests/gen_check/*`, `Makefile` `gen`/`gen-check` (via integrator) | WP-0, 4*, WP-9 | drift tests, parity ledger test (07 section 6), `server_schema.json` generation, `operations.json` release asset | `make gen-check` in CI on a clean checkout | `proposed/process/<date>-server-codegen-and-drift.md` |
| **WP-10b** | Template compile + build + decorator / *template engineer* | `client-sdk/.../models/template.py`, `api/template.py`, `api/docker_builder.py`, `api/deploy.py`, `declarative/decorator.py`, `agent/builtin.py`, `models/_server_config.py` | WP-2 (schema), WP-8 (build snippet), WP-10 | strict `server:` (unknown top-level and nested keys; the in-flight vocabulary error), `server.json` schema version, builder renders the PEP 668 Dockerfile for three bases, decorator forms compile to one `server.json` (08) | real `docker build` of a template with the injected wheel, run the image, `healthcheck` | `proposed/feature/<date>-template-server-block-and-build.md` |
| **WP-10c** | Client surface / *client engineer* | `client-sdk/.../api/server/*`, `api/server_client.py` (alias), `ops.py`, `models/errors.py` (E31xx), `models/server.py`, `Sandbox.server*` | WP-0 (catalog), WP-10 | contract test over every catalog op, error mapping table tests (07 section 4), `Sandbox.server` dual use, alias methods resolve to op ids, credentials rule (one header), `tests/test_error_codes_unique.py` | the generated client against a real in-sandbox server on a real sandbox (the repo `e2e/` suite) | `proposed/feature/<date>-client-server-surface.md` |
| **WP-10d** | Node CLI downstream / *cli (Node) engineer*, other repo | `cli/src/server/*` (cross-repo) | WP-10 (release asset) | `tsc`, unit tests, digest drift | black-box E2E in the CLI repo | CLI repo note; link from here |
| **WP-11** | Test infrastructure / *test engineer* | `tests/fakes/*`, `tests/oracle/*`, `benchmarks/*`, `tests/ai_consumer/` (moved from `spikes/`), `tests/templates/` (the 8 sample files) | WP-3 early; rolling | fakes, oracle venv job, performance budget, sample templates as tests, periodic independent AI run | the periodic run against the real implementation | `proposed/process/<date>-server-test-infrastructure.md` |
| **WP-12** | Docs and templates / *docs engineer* | `docs/en|zh/**` per section 7, `llms.txt`, `SKILL.md`, `AGENTS.md` (server-sdk), `examples/`, `codex-agent-api` migration | rolling | every code block in the cookbook is a test; en/zh parity | docs build; migrated template runs in the real sandbox | `proposed/process/<date>-server-docs.md` |
| **WP-13** | Security gate / *security reviewer* | none (review) | WP-1, 2, 3, 5, 6, 8, 10 | review checklist (section 8 of 03), `run_all.py --strict` equivalent green against the real code | pen-test results attached to the release evidence | evidence file only |

### 3.4 Order and milestones

WP-A first (alone). Then WP-0 and WP-3 start together; WP-2 starts when WP-0's `Operation` dataclass lands (interface freeze: dataclass fields in `core/registry.py`); WP-8 starts with WP-0; WP-4* after the guards API freeze; WP-1 follows WP-0/2/3 interface freeze (it is the strangler S2 step); WP-6 can start with fakes before adapters; **the client mirror (WP-10, 10c) starts at M1** against the catalog, not after the CLI.

**M0** WP-A (green baseline, fixtures) -> **M1** core + policy + guards + files (spike parity, golden files; PoC bypass tests green) -> **M2** pipeline S2 and compat S3 for files/commands (suite + fixtures green with the flag on) -> **M3** agents with fakes + oracle -> **M4** install + adapters + CLI -> **M5** client/template/build + contract tests -> **M6** docs, security gate, v1 dispatcher removed (S4) -> release **0.3.0** (server and client in lockstep; Node CLI follows).

### 3.5 File ownership map (disjoint)

| Path | Owner |
|------|-------|
| `core/{ids,refs,registry,context,errors}.py`, `core/catalog_gen.py` | WP-0 |
| `core/{dispatch,router,http,audit,limits,config,reload}.py` | WP-1 |
| `policy/*` | WP-2 |
| `guards/*` (incl. `urls.py`, `harden.py`, `launcher.py`) | WP-3 |
| `builtin/files.py` / `builtin/{commands,process,terminal}.py` / `builtin/{core,system,custom,ext,declarative}.py` / `builtin/{devtools,browser}.py` | WP-4a / 4b / 4c / 4d |
| `compat/*`, gate scripts | WP-5 |
| `agents/*` except `adapters/<name>.py` | WP-6 |
| `agents/adapters/<name>.py`, `install/manifests/<tool>*` | WP-7a..e |
| `install/*`, `install/drivers/*` | WP-8 (manifests directory is WP-7) |
| `cli/*`, `__main__.py` | WP-9 |
| `tests/contract/*`, `tests/gen_check/*`, `scripts/gen_*` | WP-10 |
| client `models/template.py`, `api/{template,docker_builder,deploy}.py`, `declarative/decorator.py`, `agent/builtin.py`, `models/_server_config.py` | WP-10b |
| client `api/server/*`, `api/server_client.py`, `ops.py`, `models/errors.py`, `models/server.py`, Sandbox surface | WP-10c |
| `tests/fakes/*`, `tests/oracle/*`, `benchmarks/*`, `tests/ai_consumer/*`, `tests/templates/*` | WP-11 |
| `__init__.py`, `pyproject.toml`, `Makefile`, `catalog/*` (generated), `CHANGELOG.md`, docs indexes | **integrator** |
| existing `tests/test_server/*`, `test_packaging.py`, `test_server_only_import.py` | nobody (frozen; changes only via the integrator with a note) |

## 4. Interface freezes (so WPs do not guess)

1. `Operation` dataclass fields and `Registry.op(...)` keyword names (incl. `effects` default `admin`, `explicit`, `agent_scope`, `urls`): [02](02-operation-model.md) section 3 (frozen at WP-0 merge).
2. `Policy.decide(op, args, principal) -> Decision` fields: `allowed, status, code, message, rule, resolved, limits, argv, executable, env, scope`; `Policy.explain` trace shape.
3. `PathScope`, `CommandScope`, `UrlScope`, `AgentScope`, `Limits`, `Deny`, `Narrow` constructor signatures: [03](03-policy-and-permissions.md) sections 6-9, 15 and the reference card.
4. `AgentAdapter` protocol: [05](05-agents-api.md) section 6; manifest JSON schema: [06](06-lazy-install.md) section 3; install job protocol: 06 section 4.
5. Catalog JSON schema: [02](02-operation-model.md) section 7.1 (versioned by `catalog_version`); `server_schema.json` for strict `server:` keys.
6. Error codes: [03](03-policy-and-permissions.md) section 11 is data in `core/errors.py` and the source of the client's E3100-E3111 mapping ([07](07-client-mirror.md) section 4).
7. Credentials: `Authorization: Bearer` wins; `X-Access-Token` alias; both different -> 401 (03 section 5).

## 5. Test strategy and gates

| Layer | What | Where |
|-------|------|-------|
| Unit | registry, ids, schema, selectors, rule algebra, matchers, parsers, manifests | per WP |
| **Bypass matrix** (WP-3/WP-2/WP-11) | `..` and `//` and trailing-slash variants; symlink in/out/chains/dir symlink swap races (thread + `os.rename` loop); hardlink (documented limit, asserted as such); `/proc/self/*`; NUL/newline/over-long paths; glob-in-argument; short/long flag aliases; `--` and option-looking `{path}`; `env` PATH/LD_* injection; shell metacharacters with `shell=False`; script-write+run pair; interpreter allow patterns; hook exception/timeout; deny-vs-allow ordering; principal confusion (`role:` vs `id:`); alias routing (`POST /commands/x`, `/v1/...`) vs authorization; unmounted-op oracle bodies byte-identical; 401-before-404; oversized bodies; request smuggling basics (duplicate headers, `Content-Length` + chunked); agents: unknown adapter, caller `base_url`, session of another principal, workdir escape | `tests/bypass/` (each case: attack, expected code, regression note) |
| Contract (client <-> server from the registry) | for every catalog op: start `full_access` server (+fake agents), call the **generated client** with fixture args, assert result keys/status/error mapping; unknown-op case; capability pre-check cases; `ops` tree equality server vs client | repo root `tests/contract/` |
| Drift | regenerate `operations.json`, `openapi.json`, `_ops.pyi`, client `_generated.py`, TS files, docs tables; fail on diff | CI job `gen-check` |
| Golden | `groups.json` (group -> ids), `presets.json` (preset -> allow rules), legacy `/capabilities` body | `tests/golden/` |
| Compat | the existing server tests unchanged (baseline recorded by WP-A: 308 collected); old import paths; `RouteTable`/`CommandRegistry` flows; legacy preset byte-compat responses (recorded v1 fixtures **generated from HEAD by WP-A before any change**: one request/response per legacy binding incl. the error shapes; replayed against v1 and v2) | `tests/test_compat/`, `tests/fixtures/v1_replay/` |
| Fake agent binaries | small Python scripts `fake_codex`, `fake_claude`, `fake_cursor`, `fake_qwen`, `fake_aider(command)` emitting recorded JSONL, honouring `--resume`, exit codes, slow streams, crash, secret echo (to test redaction) | `tests/fakes/` on `EBX_TOOLS_DIR` |
| Official-SDK oracle | `openai>=3.29` in an isolated venv job; tier-1 flows; payload validation with `openai.types.beta.agents.*`; refusals | `tests/oracle/` |
| Install | fixture HTTP server, concurrency, crash, offline, read-only, mirror host policy, unauthorized never fetches | `tests/test_install/` |
| Performance | import time (< 40 ms core), p50/p99 latency of `core.health` and `files.download` 1 MiB vs v1 baseline (<= +10%), memory under 64 concurrent 10 MiB uploads | `benchmarks/` |
| Fuzz | stdlib-random fuzzers for `resolve_path` (never returns outside root) and `match_argv` (never admits a non-matching argv; terminates) | `tests/test_guards/fuzz_*.py` |
| AI-consumer | scenario scripts S1-S8 (+ more) run by an independent model reading only the card; results archived per release | `tests/ai_consumer/` |
| Platform | python 3.10-3.13, Linux amd64+arm64; one run on the official base image (`doctor` + smoke) | CI matrix |

Coverage gate: guards and policy >= 95 % line + branch; core >= 90 %; others >= 85 %.

## 6. Migration and compatibility notes

1. **Default behaviour of a server started the old way (v1 = released 0.2.x)** is reproduced by `presets.legacy_compat()`: the same groups, bodies and statuses on the legacy bindings (compat renderer) and the v1 `BASE_DIR` jail. It
   is **applied only when no policy, preset or config is given** and it is **loud**: lint errors for its unsafe scopes (it needs `allow_open` for open mode on a non-loopback bind) and **`system.env.set` is excluded unless `EBX_SERVER_LEGACY_ENV_SET=1`** (IS-C2). Adding any policy unmounts `custom.*`/`ext.*` unless allowed; `check-config --legacy-diff` lists the dropped ids (B-6).
   New response keys are additive (`code`, `api/ops/revision/principal`).
2. **Credentials**: `Authorization: Bearer` is preferred; `X-Access-Token` stays as an alias; both different -> `401 auth.conflicting_credentials` (IF-17). `auth_token` attribute kept; `EBX_SERVER_TOKEN` becomes an admin token (must be >= 16 chars); an unset `token_env` refuses to start.
3. **Shims**: `RouteTable.route/register/enable_group/disable_group` register ops (`ext.*`, effects default `admin`, explicit-only); `CommandRegistry.command` registers `custom.<mangled>` with an alias table so `POST /commands/{original-name}` is unchanged (IF-05); `default_table()`/`default_registry()` return process-wide defaults so module-level `start()` scripts keep working; `routes_*` modules keep exporting `handle_upload`, `handle_download`, `handle_shell`, `_resolve_safe_path`, ... used by tests. **Correction (IF-04):** the first draft claimed the legacy jail message contains "traversal"; WP-A's fixtures record the *actual* v1 messages and the compat renderer reproduces those, not the quoted word.
4. **Aliases**: aliases of **released** v1 route names remain bindings indefinitely. Underscore names of the **unreleased** in-flight capability design are accepted in policy files until the 0.3.0 release candidate and then removed (ADR no-backward-compat-capability applies; no two-minor window).
5. **Deprecations**: `enable_builtin/disable_builtin` stay supported (convenience over `Policy`); `CapabilityGroup` is the `group:` selector indefinitely.
6. **Template migration**: [08](08-template-building-ux.md) section 6. `codex-agent-api` becomes the first migrated template and doubles as an integration test (WP-12).
7. **Versioning and the ADR (IF-06).** The design generation is called "v2"; the **release number does not jump**: `easy-sandbox-server` and `easy-sandbox` stay in lockstep at **0.3.0** (`_version.py`, `test_version_lockstep`), `catalog_version = 1`, `api = "easy-sandbox/2"`.
   The existing ADR `2026-09-03-no-backward-compat-capability` (the unreleased in-flight capability model needs no compatibility) is **kept** for the in-flight vocabulary and **narrowed** by the new version ADR (WP-A writes it:
   `proposed/architecture/<date>-server-v2-version-and-compat.md`): the *released* 0.2.x routes stay compatible through `legacy_compat`; the in-flight `endpoints/defaults/groups` schema, `E9xxx` and `E8xxx`-for-server are removed without a window.
8. **Rollback**: none shipped. During development the branch flag `EBX_SERVER_PIPELINE=v1|v2` selects the dispatcher (strangler stages); S4 deletes it (cut list).
9. **PyPI/wheel**: `easy-sandbox-server` console script, package data (`catalog/*.json`, `install/manifests/**`, `_ops.pyi`), `py.typed` retained; the server wheel is what the builder injects (08 section 2).

## 7. Docs-update list (en and zh; every `docs/en/...` file has a `docs/zh/...` twin)

| Doc | Change |
|-----|--------|
| `docs/{en,zh}/guide/server-policy.md` (new) | cookbook: presets, download-only, grader, per-principal, hooks, audit, reload |
| `docs/{en,zh}/guide/server-agents.md` (new) | hosting codex/claude_code/..., official SDK usage, lazy install, permissions |
| `docs/{en,zh}/reference/server-operations.md` (new, generated) | op catalog tables (04) |
| `docs/{en,zh}/reference/server-config.md` (new) | `server.json`/`template.yaml server:` schema, env vars, layers |
| `docs/{en,zh}/reference/error-codes.md` | add E3100-E3111 and the server `code` strings |
| `docs/{en,zh}/design/server-api.md` | rewrite as a pointer to this set + legacy route table (kept) |
| `docs/{en,zh}/design/server-sdk-v2/*` | this set; zh translation of README, 01, 02, 03, 05, 06 first (the rest summarised) |
| `docs/{en,zh}/guide/` template/Dockerfile guides | `server:` block, `easy-sandbox-server prepare`, official base image |
| `docs/{en,zh}/explanation/` capability model page | operations/effects/policy concepts |
| `server-sdk/{README,README.zh-CN,llms.txt,SKILL.md,AGENTS.md,CHANGELOG.md}` | card, layering rules, `@op` guidance, changelog |
| `client-sdk/{README,README.zh-CN,llms.txt,SKILL.md}` | `sandbox.server` client, `ops`, errors |
| `cli/docs/{en,zh}`, `cli/README*` | `ebx server ...`, template `server:` support |
| `.agents/notes/proposed/...` (python-sdk repo) | one ADR/note per WP (section 3.4) in the repo's ADR format, plus the **version ADR** (section 6.7) that supersedes the conflicting parts of `2026-09-03-capability-model` / `no-backward-compat-capability` |

## 8. Risks and open questions

| # | Risk / question | Mitigation / owner |
|---|-----------------|--------------------|
| R1 | Three code paths for security-critical path/command handling regress | single `guards/` module, bypass matrix in CI, WP-13 gate |
| R2 | Legacy compat renderer drift | recorded v1 replay fixtures in CI |
| R3 | Catalog churn breaks client/Node CLI | drift tests + `catalog_version` policy |
| R4 | Agent CLIs change flags/JSON formats | fake binaries + recorded transcripts per version; adapters declare `tested_versions`; `doctor` warns on untested versions |
| R5 | Manifest pins go stale (security fixes) | `lock` command + scheduled CI job opening PRs; `sbom` shows pins |
| R6 | `qoder` CLI facts: package `@qoder-ai/qodercli` (bins `qoder`, `qodercli`) is known but flags are unverified | experimental profile (also `qwen_code`, `cursor`) until an owner with the binary verifies; flagged in `agents.runtimes.list` |
| R7 | `/home/user` persistence and egress on the official platform unknown | `doctor --network`, documented fallbacks; open question to the platform team |
| R8 | Official OpenAI beta API may change (`agents=v1`) | oracle test pinned to a version range; wire layer isolated in `wire_openai.py` |
| R9 | Python 3.10 floor limits (`tomllib`, typing) | JSON runtime config; no new syntax beyond 3.10 |
| R10 | Count of ops grows (105 in the default registry with five adapters; rejected collapse into one family, IF-29) | generated catalogs, `agents.<a>.**` selector sugar, `describe --namespace` |
| R11 | **(v2.1)** ~16k in-flight lines are ported by many workers at once | WP-A baseline first; strangler stages; compat gate on every WP; integrator queue for shared files |
| R12 | **(v2.1)** LLM key readable by the agent child | documented in 05/03; `llm.proxy` deferred (disposition IS-S1) |
| R13 | **(v2.1)** Lazy install default on FC | recommended `mode: build` + `prepare`; 202 job protocol; `doctor` states the mode |

## 9. Reconciliation instructions for the in-flight workers

> This document set is **authoritative**. Where an in-flight document or code disagrees, the in-flight item changes. Workers must not
> edit this set; open an issue against it. **v2.1 note:** the in-flight work now in the tree (server `policy.py`/`guard.py`/`runtime.py`/`agents/`, client `providers/`
> with `E8000-E8030`, the provider design documents) was read; the providers package is **untouched** by this design.

### 9-0. In-flight code that must change (checklist)

| # | Where | Change | WP |
|---|-------|--------|----|
| 1 | `client-sdk/.../models/errors.py` | `E9000-E9005` -> `E3100-E3105`; add `ServerInstallError`, `ServerAgentError`, `ServerUnavailableError`, `ServerInternalError`, `ContractMismatchError`, `ServerConfigError`, `ServerArgumentError`; keep class names/attributes; add `op/request_id/details/status`; header comment | 10c |
| 2 | `client-sdk/.../api/server_client.py` | map by wire `code` (07 section 4); alias module over the generated tree | 10c |
| 3 | `client-sdk/tests/test_api/server_e2e/*` (3 hits) and docs en/zh `reference/error-codes.md`, `reference/api-reference.md`, `design/fine-grained-capabilities.md`, `client-server-alignment.md`, `cli-followups.md`, `CHANGELOG.md` | `E9xxx`/`E8xxx`-for-server -> `E3100-E3111` | 10c, 12 |
| 4 | `client-sdk/.../models/template.py` | `server:` strict; v2 vocabulary; `extra` handling of the `server` subtree | 10b |
| 5 | `server/policy.py`, `guard.py`, `runtime.py` | converted to packages (section 1.2), names re-exported | 2, 3, 1 |
| 6 | `server/agents/*` | 47-op wire; `provider` word absent; `AgentScope` required; install via manifests; remove `npm i -g` | 6, 7, 8 |
| 7 | `server/__init__.py`, `routes.py` | lazy import of the agents group (circular import risk) + import test | A |
| 8 | server capabilities body | union body for two minors | 1 |
| 9 | repo gates | fix the 5 scratch-path hits in this design set; `make gen`/`gen-check` targets | integrator |

### 9a. Worker (a): fine-grained capabilities, client/server alignment, base image

1. **Identity**: replace the flat endpoint names with dotted op IDs everywhere (docs, policy examples, tests, error bodies). Keep the old names as **aliases**
   only. Mapping: `health`->`core.health`; `capabilities`->`core.capabilities`; `capabilities_check`->`core.check`; `list_commands`->`custom.list`;
   `run_command`->`custom.<name>`; `upload`->`files.upload`; `download`->`files.download`; `shell`->`commands.run`; `shell_stream`->`commands.stream`;
   `files_list|stat|mkdir|delete|move|search|archive|watch`->`files.list|stat|mkdir|delete|move|search|archive|watch`; `files_upload_stream`->`files.upload_stream`;
   `files_download_stream`->`files.download_stream`; `process_start|list|detail|signal|stdin|output`->`process.start|list|get|signal|stdin|output`;
   `pty_create_session|list_sessions|delete_session|detail|resize`->`terminal.create|list|delete|get|resize`; `system_info|system_metrics|ports|packages`->`system.info|metrics|ports|packages`;
   `env_get|env_set`->`system.env.get|system.env.set`; `code_run`->`devtools.code.run`; `git_status|git_diff`->`devtools.git.status|diff`; `browser_<x>`->`browser.<x>`.
2. **Naming clash**: `server.commands.*` (custom commands) becomes `custom.*`; `commands.run` is the shell op. Rename `ServerClient.commands` accordingly
   (`srv.custom.<name>(...)`, `srv.commands.run(...)`).
3. **Scopes** (`files:read`, ...) are **not primitives**; reduce section 3.2 to a derived-sugar table compiled into `effect:`/ID-selector rules, or drop it. The
   authoritative model is rules over IDs ([03](03-policy-and-permissions.md)). Remove the endpoint-rules/scope duality.
4. **Request pipeline** (section 5): replace with [02](02-operation-model.md) section 6 (transport step 0, authenticate before 404; principal-filtered mounted check; policy before
   existence checks; alias resolution after authentication).
5. **Path scoping**: replace the canonicalise-then-open description with `resolve_path` + `open_beneath` ([03](03-policy-and-permissions.md) section 6); drop any
   `O_TRUNC` open-then-verify approach (proved unsafe). **Command scoping**: typed tokens (`{path}`) instead of glob path arguments; `env_pass`/`env_set`;
   allowlist-first; escape-capable lint; launcher not `preexec_fn`.
6. **Errors**: the client exception family `E8000-E8005` collides with the providers design (E8000-E8030) and the working tree's `E9000-E9005` is a third scheme. Use **E3100-E3111 only** ([07](07-client-mirror.md) section 4, D29); `E9xxx` is dropped;
   server `code` strings are the dotted families of [03](03-policy-and-permissions.md) section 11 (`policy.path_not_allowed`, not `path_not_allowed`).
   `404 endpoint_disabled` becomes `404 op.not_enabled` (principal-filtered).
7. **Config surfaces**: file `server-policy.json` -> `server.json` (the old name is still auto-read as `{"policy": ...}`); keep `EBX_SERVER_*` names and add the new ones
   (`EBX_SERVER_CONFIG`, `_PRESET`, `_ENABLED_OPS`, `_DISABLED_OPS`, `_READONLY`, `_RESTRICT_PATHS`, `_POLICY_RELOAD`, `_AUDIT`, `_INSTALL_MODE`); layering/restrict-only rules from
   03 section 10; the template `server:` block uses the schema of [08](08-template-building-ux.md) section 2.
8. **Client**: `ServerClient`/`ServerCapabilities` keep their no-hidden-traffic contract but are **generated** from the catalog; method names equal op IDs; `Sandbox.server`
   stays. `discover()`, `can()`, `require()`, `limit()` remain; `check_path` becomes `check(op, **args)`.
9. **Layout**: do not create `server/policy.py`, `server/guard.py`, `server/runtime.py` as flat files; their content goes to `policy/`, `guards/`, `core/` per section 1.2.
   Base image doc: keep the Dockerfile contract and `serve/healthcheck`; replace `check-config` text with the 06 subcommand table; `--commands` becomes an alias of `--load`; the auto-load
   path is `/etc/easy-sandbox/server.json`.
10. **Review log**: keep `fine-grained-capabilities-review.md` as history; add a "Superseded by server-sdk-v2" banner to the three documents.

### 9b. Worker (b): OpenAI-compatible agents API

1. **Operations**: every route resolves to a generic op (`agents.definitions.*|environments.*|sessions.*|runtimes.*|models.list`, 32 official ids) that **also** requires the adapter op `agents.<a>.run|install|sessions.create|sessions.send_event` ([05](05-agents-api.md) sections 3-4); the alias resolver runs after authentication and before authorization. Replace the single coarse `agents` group by `agents.**` (group `agents`
   expands to exactly that); `enable_builtin(..., AGENTS)` is sugar for allowing `agents.<registered adapter>.**` **without** `install`.
2. **Naming**: canonical adapter names `claude_code`, `qwen_code` (identifier grammar); hyphenated names only as wire/`model` aliases. Add `qoder` (declarative profile, experimental).
3. **`provider:` -> `llm:`** for the model endpoint (the word *provider* means sandbox backend elsewhere); credentials as `*_env` references only; adapters read `EBX_LLM_*` as fallbacks.
4. **Install**: delete `install_steps`, `npm i -g`, `curl | bash`, `POST /agents/runtimes/{name}/install` and `EBX_AGENTS_ALLOW_INSTALL`. Adapters declare `manifest` ([06](06-lazy-install.md));
   install happens lazily after authorization, explicit install is the `explicit-only` op `agents.<a>.install`; install progress maps to `agent.session.environment.pending|ready|failed`.
5. **Auth**: universal `Authorization: Bearer` / `X-Access-Token` (not an agents-only exception); `OpenAI-Beta: agents=v1` accepted and ignored.
6. **Scope vs the official API**: adopt the 47-op tiering (25 implemented, 2 reserved, 5 refusals, 15 not planned); agents CRUD <-> `agents.definitions.*` (also served at `/agents/definitions`);
   `sessions.create` requires `environment` (`self_hosted.workspace_directory` must lie inside `AgentScope.workdir`); the adapter is selected by path `/agents/<a>/v1`, header `X-EBX-Adapter`, a `model` equal to an adapter name, `agents.default`, or the only mounted adapter (real model names pass through); object names `agent`, `agent.session`, ...
7. **Session security**: session ownership per principal (+ `share_sessions`), idempotency keys namespaced by principal and bound to a request hash, journal under the state dir (`~/.local/state/easy-sandbox`, never `/tmp`).
8. **Permissions**: `AgentScope.permissions` with refusal when the CLI cannot honour a level; add the lint that path/command scopes do not confine agents.
9. **Module layout**: `agents/{runtime,store,journal,queue,wire_openai,wire_native,resolver,ops}.py` + `adapters/`; `responses_wire.py`/`sessions_wire.py` become `wire_openai.py`; the
   runtime imports only `core` and `policy`. Declarative `command` adapter schema from 05 section 6 replaces the `runtime: command` sketch.
10. **Tests**: use the real `openai` 3.29.0 SDK as the contract oracle; fake agent binaries on `EBX_TOOLS_DIR`; keep the queue/replay/idempotency semantics (they are adopted).
11. **Client Python surface** (`easy_sandbox.agents`: `Agent`, `Runner`, `Session`, `AgentHost`) stays but is implemented over `srv.agents.<adapter>.*`; `AgentHost` bootstrap uses `prepare`/lazy install instead of `install` POST.

### 9c. Worker (c): providers and credentials

* `provider` means the **sandbox backend** (E8000-E8030 are yours). The server SDK never uses the word for model endpoints (`llm:`). In-sandbox variables stay `EBX_SERVER_*`; agents may read optional
  `EBX_LLM_*`; credentials that the provider layer injects into the sandbox should use those names. No server op or policy key mentions a provider. Nothing else changes for you.

### 9d. Worker (d): repository layout

* Server layout of section 1 inside `server-sdk`; generated artefacts: `server-sdk/src/easy_sandbox/server/catalog/*` (committed), `client-sdk/src/easy_sandbox/api/server/_generated.py` and
  `models/_server_config.py` (committed, generated), `cli/src/server/generated/*` (committed, generated). Cross-package contract/drift tests live at the **repository root** (`tests/contract/`,
  `tests/gen_check/`), not inside either package, because they need both installed. One `docs/{en,zh}/design/server-sdk-v2/` set; `.agents/` ADRs per section 7; CI jobs: `gen-check`, `contract`,
  `bypass`, `oracle` (isolated venv), `compat-replay`. No hard runtime dependency from `client-sdk` on `server-sdk`; if the layout work introduces a shared package, only `catalog/` and the config schema move.

## 10. Definition of done (release gate for 0.3.0)

All WP gates green **and the repository gates** (IF-15): `make ci` (ruff check/format-check, mypy per `pyproject`, pytest not integration, both packages), `bash scripts/check-no-local-paths.sh` (`make hygiene`; this set was fixed for its 5 scratch-path hits),
`bash scripts/check-repo-health.sh`, `tests/test_packaging.py`, `tests/test_server_only_import.py`, `test_version_lockstep`, docs en/zh parity (every changed `docs/en/...` has its `docs/zh/...` twin), `make gen-check` (catalog, openapi, client `_generated.py`, server schema, parity ledger).
The existing server tests: **collected count not below the WP-A base (308)** and all green, unmodified; v1 replay fixtures green; bypass matrix and the 41 independent-security PoCs green against the real code; contract + drift green; oracle green on the pinned `openai` range;
`doctor` green on the official base image; one image built with `prepare` runs on a read-only root; every WP has its evidence file, `.agents` note (en + zh docs) and CHANGELOG entry (DoD items 3-6); security gate signed.
The independent AI-consumer run is periodic and non-blocking for 0.3.0.
