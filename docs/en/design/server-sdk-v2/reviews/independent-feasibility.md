# Independent review: feasibility, compatibility, completeness, architecture

> Reviewer: independent (did not write the design). Scope: `server-sdk-v2/` (README, 01-10, `reviews/`, `spikes/`) read against the
> in-flight design documents it must reconcile with, the pristine `HEAD` server/client code, and the **uncommitted working tree**
> (other workers were mid-edit; read-only review, no code was changed).
> Lens: feasibility, backward compatibility, completeness, architecture. Security-model questions are covered by the sibling independent
> security review and are only touched where they decide feasibility.

## 0. Method and what was verified (so the numbers can be trusted)

| Check | Result |
|-------|--------|
| Existing server tests at `HEAD` (clean export, venv with the server wheel) | **308 collected** (304 under `tests/test_server/`, 4 elsewhere), 307 pass, 1 environmental failure (`TestPackages::test_pip_returns_structure`: the venv has no `pip`). The design's "297" is stale; the gate must say "all server tests, count recorded at the base commit". |
| Legacy routes at `HEAD` | **41** `register(...)` calls, confirmed: core 3 (`/health`, `/commands`, `/commands/{name}`), upload/download/shell 3, system 7 (incl. `/capabilities`), files 9, process 5, pty 3, devtools 3, browser 8. `POST /capabilities/check`, `GET /files/watch`, `POST /process/{pid}/stdin`, `GET /process/{pid}/output`, `GET /pty/sessions/{id}`, `POST .../resize` and the PTY WebSocket are **not** v1 routes. |
| Working tree (uncommitted) | `server/__init__.py` currently fails to import (`ImportError: cannot import name 'routes_agents' ... circular import`). There is no green baseline right now (finding IF-09). The working tree already holds ~12.6k lines of server code and a 48-entry endpoint catalog (41 legacy + 7 new endpoints) in `policy.py`. |
| Spikes shipped with the design | `tests_proto.py`, `tests_catalog.py`, `tests_round4.py`: all pass (36 + catalog). They test the *prototype* in `spikes/ebxp`, not the package, so they say nothing about the 308 tests. |
| Demonstrated by experiment | A package `ops/` next to a module-level attribute `ops` (10 section 1 + section 2) breaks the public `ops` tree as soon as `ops/files.py` is imported (IF-03). |
| Repo hygiene gate (`scripts/check-no-local-paths.sh`) | 16 findings today, 5 of them inside `server-sdk-v2/` (scratch-path literals in 05, 06, round-2 review, spikes). Fix before the set is promoted (IF-15). |

Severity scale: **Blocker** = the plan cannot meet a stated requirement as written; **High** = will cause rework or a regression if not fixed
before the affected WP starts; **Medium** = fix in the design/plan, no code risk yet; **Low** = hygiene.

## 1. Findings summary

| Sev | Count | IDs |
|-----|-------|-----|
| Blocker | 2 | IF-01, IF-08 |
| High | 12 | IF-02, 03, 04, 09, 10, 12, 13, 17, 20, 21, 22, 31 |
| Medium | 14 | IF-05, 06, 11, 14, 15, 18, 19, 23, 24, 26, 27, 28, 29, 30 |
| Low | 3 | IF-07, 16, 25 |
| **Total** | **31** | |

## 2. Findings

### 2.1 Backward compatibility

**IF-01 - Blocker - 04 section 1, 10 sections 2/6.1/6.3, WP-5 gate - "legacy preset" modelled as an immutable policy snapshot.**
*Problem.* The 308 tests (and real user scripts such as the template `commands.py` pattern) depend on behaviour that a frozen preset cannot give:
(a) the `RouteTable` is **live**: tests call `table.route(...)`, `enable_group/disable_group` *after* the server object exists and expect the next request to see it;
(b) `EBX_SERVER_*` variables (`BASE_DIR`, enabled groups, token) are read **per request** by the legacy code and tests set them with `monkeypatch` after construction, so "realpath at construction" and "snapshot at start" change observable behaviour;
(c) `SandboxRequestHandler` is wired by attributes on the `HTTPServer` instance (duck typing) and tests build handlers/servers directly, bypassing `SandboxServer.__init__`;
(d) tests import and call handler helpers (`_resolve_safe_path`, `handle_upload`, ...) with the legacy `ServerRequest` type and assert **exact messages** (`"Path escapes base directory"`).
10 section 6.3 promises "shims", but a shim over a different dispatcher cannot keep (a)-(c) true; the plan has no work item that proves it before WP-1 rewrites the dispatcher.
*Fix.* Adopt a **strangler order**: the v1 dispatcher (`app.py`, `router.py`, `routes*.py`) stays untouched and keeps serving until the v2 pipeline passes the 308 tests on its own. Stage 1 = the in-flight `PolicyEngine` (it already wraps a live `RouteTable` per route and is the only design that coexists with (a)-(d)); stage 2 = ops registered *as* route-table entries (a route is an op binding), pipeline order enforced inside the existing dispatch; stage 3 = optional extraction to `core/`. The compat WP becomes a **gate on every WP**, not a late WP (IF-02).

**IF-02 - High - 10 WP-5/M2, section 10 - compat gate is late and the count is wrong.**
*Problem.* WP-0..WP-4 can merge while the 308 tests are red, since the gate is at WP-5 (M2). WP-5 also "owns the existing tests (moved, unchanged)": moving them changes import paths and conftest discovery, i.e. it is not "unmodified". The number 297 is stale (308 collected at the base commit).
*Fix.* Gate every WP merge on `pytest server-sdk/tests` at the recorded base count (do not move files; add new tests beside them); record the base commit and count in the plan; list the one environment-dependent test explicitly (needs `pip` in the venv).

**IF-03 - High - 10 section 1 + section 2 - `ops/` subpackage collides with the public `ops` tree.**
*Problem.* `easy_sandbox.server.ops` is both a package (built-in op modules) and the exported `OpRef` tree (`from easy_sandbox.server import ops; ops.files.list`). Importing any submodule sets the package attribute `ops` to the module, silently replacing the tree (reproduced). The client side (`easy_sandbox.ops`, generated) has no such package and is unaffected, but the contract test that compares both trees would pass on a broken server tree only if it imports the module path, so test the public import.
*Fix.* Rename the subpackage to `builtin/` (or `modules/`), keep `ops` for the tree only; add an import test (`from easy_sandbox.server import ops; ops.files.list` after importing every submodule).

**IF-04 - High - 04 section 1, 03 section 11 - claims about v1 behaviour that are false, and fixtures come too late.**
*Problem.* 04 says a legacy path violation keeps `400 ValueError` "message containing `traversal`". At `HEAD` the message is `Path escapes base directory` (asserted by tests), and devtools has two other messages (`Path traversal ('..') is not allowed...`). The v1 renderer is described, not specified; the recorded v1 replay fixtures (R2) are produced "in CI" later.
*Fix.* Generate the v1 fixtures **now** from `HEAD` (one request/response per legacy binding, including all error branches the 308 tests touch: 400/401/403/404/405/413/500 bodies, `{"error", "type"}` shape, header casing, SSE framing) and make them WP-1's acceptance gate, before any renderer is written. Correct the "traversal" sentence.

**IF-05 - Medium - 04 section 10, 02 grammar - `custom.<name>` cannot represent every legacy command name.**
*Problem.* `CommandRegistry.command(name)` accepts any string at `HEAD` (hyphens, dots, upper case). Op IDs are lowercase identifier segments. The design also reserves `list` and `describe`; a legacy command called `list` or `describe` currently works through `POST /commands/list`.
*Fix.* Deterministic mangling (`Hello-World.v2` -> `custom.hello_world_v2`, collision -> numeric suffix, logged), the wire alias `POST /commands/{name}` resolves by the **original** name through an alias table, and reserved words only reserve `custom.list`/`custom.describe` as IDs, not the wire name. Add the legacy-name cases to the compat suite.

**IF-06 - Medium - 10 section 6.7, `.agents` ADR 2026-09-03 - decision conflict and version jump.**
*Problem.* The implemented ADR "No Backward Compatibility for the Capability Model" states the project is pre-release with zero installed base and forbids compat shims/legacy modes ("this decision would not hold once real templates exist"). v2 introduces `presets.legacy()`, a `compat/` package, `EBX_SERVER_LEGACY_DISPATCH` and a `2.0.0` jump while all packages are at `0.3.0` (lockstep test covers both). Either the ADR no longer holds (then say so with a superseding ADR) or most of the compat machinery is unnecessary.
*Fix.* Decide explicitly in an ADR. Recommendation: keep *route and body compatibility of the 41 bindings* (cheap, they are bindings of ops) and drop the rollback dispatcher, the two-minor alias window and the separate `compat/` package. Keep the lockstep scheme; pick the version in the release PR (`0.4.0` unless a real 1.0 decision exists).

**IF-07 - Low - 07 section 5 - `Sandbox.server` vs the declarative `sandbox.server.start(...)`.**
*Problem.* Two unrelated objects are both spelled `sandbox.server` (client attribute vs decorator namespace in `declarative/decorator.py`), and `easy_sandbox.server` is the server package import path. Docs and AI consumers will conflate them.
*Fix.* Document the distinction in the card, or name the client attribute `Sandbox.server_api`/`Sandbox.srv` (keep `server` as alias only if the decorator namespace is renamed).

### 2.2 Plan: ordering, ownership, completeness

**IF-08 - Blocker - 10 sections 1, 3, 9 - no work package migrates the in-flight code; the target layout is incompatible with it.**
*Problem.* The working tree already contains: `policy.py` (830 lines, `ServerPolicy`, scopes, `endpoints{}` rules, 5 presets), `runtime.py` (708, `PolicyEngine` over `RouteTable`), `guard.py` (230, `PathGuard`), `contract.py`, `__main__.py` (4 subcommands), `agents/` (~3.6k lines incl. runtime 1.4k, store, adapters for codex/claude_code/qwen_code/cursor/command, `provider:` spec, `EBX_AGENTS_*`), routes for 7 extra endpoints, plus client-side `models/server.py` (427 lines, pydantic), `api/server_capabilities.py`, error classes E9000-E9005 and their tests. 10 section 9 says "absorbed" and forbids `policy.py`/`guard.py`/`runtime.py`, but no WP owns the port, WP-2/3/6 each start from empty directories, and all of that code is a *different model* (scope strings, per-endpoint rules, flat names). Result: duplicated implementations and ~16k lines either thrown away or running in parallel.
*Fix.* Add **WP-A "baseline and port"** before WP-0: (1) commit the in-flight state as the baseline with green tests (IF-09); (2) per-file decision from the reconciliation table in section 4 (keep/rename/delete/merge); (3) each later WP *starts from* the ported file rather than from nothing. Prefer extending `policy.py`/`guard.py`/`runtime.py` in place and splitting them into packages only after behaviour is stable (rename = pure move commit).

**IF-09 - High - working tree - no green baseline.**
*Problem.* `import easy_sandbox.server` raises a circular-import error (`routes_agents`), so no WP can measure "unchanged" and the 308-test gate cannot run.
*Fix.* The baseline commit in WP-A must import and pass the legacy suite; the agents group must be imported lazily from `enable_builtin`/`serve`, never from `__init__`.

**IF-10 - High - 07 section 4, in-flight `errors.py`, `fine-grained-capabilities.md` section 7 - three different error ranges and attribute names.**
*Problem.* The capability doc says E8000-E8005; the working-tree client already moved to **E9000-E9005** (`ServerAPIError`, `ServerAuthError`, `PolicyDeniedError`, `FilePolicyDeniedError`, `EndpointNotAvailableError`, `PayloadTooLargeError`, `RateLimitedError`; module docstring documents `E9xxx = in-sandbox server API errors`); v2 mandates **E3100-E3111** and 07 states the attributes `.code/.op/.status/.request_id/.details`. `SandboxError.code` is already the `E....` string, so `.code` as the dotted server code (`policy.path_not_allowed`) would overwrite it. The in-flight classes use `status_code/error_type/error_code/endpoint`, which avoid the clash.
*Fix.* Keep **E9xxx** (already implemented, own category, no overlap with execution errors; extend to E9006-E9011 for install/agent/unavailable/internal/contract), keep the attribute names `error_code`/`endpoint`, add `op`, `request_id`, `details`; update 07 section 4 and the docs list. One mapping table (server `code` prefix -> class) shared by Python and the Node CLI.

**IF-11 - Medium - 07 section 4/1 - `EasySandboxError` does not exist; "no pydantic" contradicts existing client style.**
*Problem.* 07 makes `ServerAPIError` subclass `EasySandboxError`; the base class is `SandboxError`. 07 section 1 promises `TypedDict` results with "no pydantic", but the client's models are pydantic (`extra="ignore"`) and 427 lines of server result models (`ShellResult`, `ProcessOutput`, `PtySessionInfo`, ...) already exist.
*Fix.* Use `SandboxError`; keep the existing pydantic result models for the 48 known endpoints (generation can emit them), and let the dynamic fallback return plain dicts. Decide once and document.

**IF-12 - High - 10 section 3 - file ownership is not disjoint.**
*Problem (concrete overlaps).*
(1) `__init__.py`: WP-0 owns it, WP-5 edits it for compat re-exports, WP-4* add exports.
(2) `guards/urls.py` is in WP-4d, `guards/*` is exclusively WP-3.
(3) `cli/gen_client.py` template files: WP-9 owns `cli/*`, WP-10 owns "templates".
(4) `install/manifests/<tool>*` (WP-7a-e) vs `install/*` (WP-8); `tests/fakes/*` (WP-11) vs the fakes of WP-7.
(5) `pyproject.toml` (WP-0): WP-8 (package data), WP-9 (console script), WP-4d (extras) all need edits.
(6) Generated, committed artifacts (`catalog/*`, client `_generated.py`, TS files, docs tables, `groups.json`) change whenever *any* op WP merges, so every WP touches files owned by WP-0/WP-2/WP-10: guaranteed merge conflicts.
(7) `CHANGELOG.md`, `AGENTS.md`, `llms.txt` are owned by WP-12 but edited "rolling" by all.
(8) The existing `tests/test_server/*` move (WP-5) while WP-1/2/4 need them.
*Fix.* Declare an **integrator** role that alone runs `make gen` and merges generated files (WPs commit sources only; CI regenerates and fails on drift but does not commit). Give shared files a PR queue (one owner per file, others send patches). Move `urls.py` to WP-3, manifests to their adapter WP with WP-8 owning only `install/*.py` and `install/drivers/`. Do not move existing tests (IF-02).

**IF-13 - High - 10 section 3 - missing work packages (client-side build path).**
*Problem.* Nothing owns:
- `models/template.py` `server:` field and compile of `template.yaml server:` into the generated `server.json` plus the Dockerfile/`COPY` step. `SandboxTemplate` ignores unknown keys (`extra="ignore"`), so today a `server:` block would be **silently dropped** (see IF-31).
- `api/docker_builder.py`: `inject_sdk_wheel`/`_download_release_wheel` (wheel injection, the `COPY *.whl` pattern), `build_and_register_official` (base-image path), Dockerfile `USER`/PEP 668 handling, copying `server.json`/manifest locks, running `easy-sandbox-server prepare` at build time (IF-22).
- `api/deploy.py::resolve_llm_env` (`EBX_LLM_*`) and the `llm:` block of agents; `agent/builtin.py` template `codex-agent-api` migration (only mentioned as an example in WP-12).
- `declarative/decorator.py` (`sandbox.register.upload()`, `sandbox.server.start(...)`, which call `enable_builtin`) - 04 lists `ops/declarative.py` but no client-side owner.
- `Sandbox.server`, `Sandbox.start_server`, `server_at`, and re-implementation of `Sandbox.custom`/`list_commands` over `srv.custom.*` (07 section 5) - none of these exist yet (no `api/server_client.py`; `server_capabilities.py` imports it only under `TYPE_CHECKING`).
- The planned `easy_sandbox.agents` surface (`Agent`, `Runner`, `AgentHost`) that 10 section 9b.11 says "stays": it exists only in `agents-api.md`, not in code.
- Node CLI (`cli/`): separate package and release train (IF-28).
- `docs/zh` twins, CHANGELOG, `.agents` ADR files as deliverables with owners and Status lifecycle (`proposed/` first).
*Fix.* Add WP-10b (template/build integration: `models/template.py`, `api/template.py`, `docker_builder.py`, `deploy.py`, `declarative/decorator.py`, `agent/builtin.py`), WP-10c (`Sandbox.server*` + `ServerClient`, split from codegen), WP-10d (Node CLI). Each with a gate: a template with `server:` builds a Docker context whose `server.json` equals the golden file; unknown `server:` key fails the build.

**IF-14 - Medium - 10 section 3 - dependency and gate gaps.**
*Problem.* (a) WP-13 (security gate) depends on WP-2, 3, 6, 8 but not on WP-1 (pipeline order, size caps, auth extraction: the most security-critical code), WP-5 (the legacy preset is the widest exposure) or WP-10 (client token handling). (b) WP-6 needs WP-1 streaming (SSE/NDJSON) and `WP-9 serve`; WP-9 `serve` needs WP-1. (c) WP-10 waits for WP-4* and WP-9, so the client mirror and the contract test only start at M5; yet the catalog of the 48 existing endpoints is stable now and the client models already exist. (d) M2 (compat) after M1 means M1 ships dispatcher changes without compat verification.
*Fix.* Re-draw edges: WP-1 -> WP-6/WP-9/WP-13; WP-5 -> WP-13; start the client mirror at M1 against the 48-entry catalog and extend per op WP; contract-test case coverage grows with each op WP.

**IF-15 - Medium - 10 sections 5/10 - release gates omit the repo's own gates.**
*Problem.* Not listed: `ruff` + `mypy --strict`, `scripts/check-no-local-paths.sh` and `scripts/check-repo-health.sh` (currently red on the v2 set), `test_packaging`/`test_server_only_import` (server wheel installs and imports without the client; shared `easy_sandbox` namespace package has no `__init__.py` in the server wheel), `test_version_lockstep`, docs en/zh parity, `Makefile` targets (`gen`, `gen-check`). 10 section 7 says "every docs/en file has a zh twin" and then schedules zh for 6 of 12 files only.
*Fix.* Add them to the DoD; either translate everything (as the repo rule requires) or file the exception in an ADR; clean the 5 hygiene hits (replace scratch-path literals with `$EBX_...` variables or placeholders).

**IF-16 - Low - 10 section 7 - process hot spots.**
*Problem.* ADRs must start in `.agents/notes/proposed/<category>/` and move on acceptance; the plan says "merged" at DoD only. A single `CHANGELOG.md` edited by every WP conflicts.
*Fix.* Per-WP changelog fragments merged by the integrator; ADRs land as `proposed` at WP start.

### 2.3 Request pipeline and transport (feasibility-relevant)

**IF-17 - High - 03 section 5, 07 section 5 - no precedence rule when `Authorization` and `X-Access-Token` both arrive.**
*Problem.* The client sends both headers; behind the platform gateway `X-Access-Token` may be the **platform** token while the server token travels as Bearer (or the reverse). The design accepts either "per transport" and does not say what happens when both are present and differ; the in-flight client documents "ambiguous credentials" as a `ServerAuthError` (400/401). Without a rule, a valid platform token can mask a wrong server token (or vice versa), and legacy clients that send only `X-Access-Token` change behaviour.
*Fix.* Specify: if both present and equal -> accept; if different -> try `Authorization` first (the explicit server credential), then `X-Access-Token`, never "any"; log which header matched; test matrix with gateway-injected header.

**IF-18 - Medium - 03 section 5 - failed-auth rate limit "per source address" is unusable behind the gateway.**
*Problem.* In the platform every request arrives from the gateway/loopback, so one source address means one global bucket: an attacker (or a misconfigured poller) locks every caller out of the server (DoS); or, if the limiter is lenient, brute-force protection is moot.
*Fix.* Key on a fingerprint of the presented credential plus a coarse global bucket; honour `X-Forwarded-For` only from configured `trusted_proxies`.

**IF-19 - Medium - 03 section 9 - `max_connections=64 -> 503` can starve readiness probes.**
*Problem.* Long SSE/agent streams plus 64 slots: the platform `ready_cmd`/liveness `core.health` calls get 503 and the sandbox is declared unhealthy.
*Fix.* Reserve slots (or a separate tiny accept path) for `core.health`/`healthcheck`; count stream ops separately.

### 2.4 Lazy install (06) on the Alibaba Cloud agent-sandbox base image

Feasibility verdict: **works only if** installs are baked at build time (`prepare`) or the tools dir is writable and egress to the manifest hosts exists. As written, lazy-as-default is wrong for that platform (IF-21) and three concrete defects break the read-only/no-network case (IF-20, 22, 23, 24).

**IF-20 - High - 06 section 6 steps 1-2 - the lock is taken before the marker is checked.**
*Problem.* `fcntl.flock` needs an open (creatable) lock file in `.locks/`. On a read-only tools dir (`/opt/easy-sandbox/tools` prepared at build time and mounted read-only) opening the lock fails with `EROFS`/`EACCES` **before** the "already installed" check, so a prepared image cannot start any agent, contradicting section 10 ("used read-only at runtime when prepared").
*Fix.* Lock-free fast path first: read marker + manifest digest + `verify` result without taking a lock; take the lock (in a writable dir: the next entry of the tools-dir chain or the runtime dir) only when an install is needed; if no writable dir exists return `install.read_only` with the list of directories tried.

**IF-21 - High - 06 sections 5/4 - lazy as default and `install.wait=true` (10 min) fit neither ephemeral sandboxes nor gateway timeouts.**
*Problem.* On an ephemeral per-sandbox filesystem every cold sandbox repeats the download (agent CLI plus Node runtime plus `npm ci`, and a Playwright Chromium of hundreds of MB for `browser.*`). The first request blocks inside one HTTP request for up to 10 minutes while platform gateway/FC request timeouts are unknown (R7 admits it). The design only maps progress to `agent.session.environment.pending` for agents; `browser.*` and `devtools` have no async path.
*Fix.* Default `install.wait` to a short bound (for example 20-30 s) after which the op returns `202`/`install.pending` with a job id and `Retry-After`, plus a read op `install.status` (or reuse `core.describe`); recommend `prepare` at image build for FC as *the* supported path in the template UX (08) and have `doctor` say so; keep lazy as the dev/local default.

**IF-22 - High - 06 section 9, 08 section 4 - `RUN pip install easy-sandbox-server` fails on the target image and ignores `docker_builder`.**
*Problem.* The official base image has an externally managed (PEP 668, Python 3.13) interpreter and runs as non-root `user`; plain `pip install` aborts. The existing `base-image-and-server-sdk.md` uses `PIP_BREAK_SYSTEM_PACKAGES`/`COPY *.whl`, and `docker_builder.inject_sdk_wheel` already puts a wheel in the build context for unreleased/pinned versions; v2 documents neither, so templates built from the v2 docs fail or pull an unpinned package. The version pin (lockstep) is also missing from the line.
*Fix.* One canonical snippet in 06/08: `USER root` + wheel from the build context (version pinned by the builder) + `pip install --no-cache-dir --break-system-packages` (or a venv at a fixed path with a console script on `PATH`), then `RUN easy-sandbox-server prepare --config /etc/easy-sandbox/server.json` and `USER user`; the builder, not the template author, writes it (WP-10b).

**IF-23 - Medium - 06 sections 5/10 - `noexec` mounts and permissions are not handled.**
*Problem.* Writable runtime directories on FC-style sandboxes are often tmpfs or volumes mounted `noexec`; installed binaries then fail at `verify`, reported as a generic `install.failed`. Build-time `prepare` runs as root: tools must be world-readable/executable for `user`, and `HOME` is overridden to staging during install.
*Fix.* `doctor` checks writability **and** exec capability per candidate dir (probe by exec of a tiny script); skip non-exec dirs in the chain; set modes in `prepare`; map `EACCES` on exec to `install.noexec` with the remedy.

**IF-24 - Medium - 06 sections 6/7 - no-network behaviour is slow and ambiguous.**
*Problem.* With egress blocked, the first agent call waits for connect timeouts (15 s x manifests x retries) before failing; `pip-hashes`/`npm ci` also need an index. `offline` mode must be chosen manually.
*Fix.* One cached reachability probe per manifest host set (`doctor --network` result stored in the runtime dir), fail fast with `install.network_unreachable` and the exact `prepare` remedy; auto-select `offline` when the probe fails.

**IF-25 - Low - 09/03 - readiness path imports the whole server.**
*Problem.* `healthcheck` as a CLI subcommand starts a Python interpreter per probe; with the new package size this grows.
*Fix.* Keep `healthcheck` a stdlib-only fast path in `__main__` (the in-flight `__main__.py` already does this; assert it in a test: no import of `core`, `policy`, `agents`).

### 2.5 Client/server alignment and codegen

**IF-26 - Medium - 02 section 7, in-flight `server_capabilities.py` - two discovery bodies.**
*Problem.* v2 `/capabilities` returns `api`, `ops`, `revision`, `principal`; the working-tree client parses `api_version`, `endpoints{<flat_name>: {allowed, scopes, limits, params, paths}}`, `identity{scopes}`, `policy{preset, revision, configured}`, `groups`, `warnings`. Neither side states which wins; 07 section 3 says legacy servers are recognised by the absence of `ops` while the in-flight client recognises them by the absence of `endpoints`.
*Fix.* Define one body (v2 keys) and serve a compat projection (`endpoints` keyed by the **alias** names, `identity`, `policy`) for two minors; the client detects `ops` first, then `endpoints`, then legacy `groups`. Golden test for each of the three shapes.

**IF-27 - Medium - 04 section 13.6, 07 section 6 - "complete" is asserted, not checkable.**
*Problem.* 07 section 6 lumps `browser.*`, `agents.*`, `system.*`, `core.*` into one "server-only by design" row, so a missing client method for an individual op cannot fail a test. 04 section 13.6 requires a justified asymmetry entry per op.
*Fix.* Commit the per-op ledger of section 5 below as `tests/contract/client_parity.json` (op -> client method | asymmetry reason) and fail CI if a catalog op is absent from it.

**IF-28 - Medium - 07 section 7, WP-10 - Node CLI is a separate package/release train.**
*Problem.* The CLI lives in its own tree (`package.json`, separate lockfile and `AGENTS.md`), is versioned independently and is currently being edited by another worker. WP-10 claims `cli/src/server/*` and a drift check against a pinned wheel, which makes the Python release block on the CLI and vice versa; the catalog "release asset" is not produced by any WP.
*Fix.* Treat the CLI as a downstream consumer: the Python repo publishes `operations.json` as a release asset (WP-0 deliverable) and the CLI repo owns its generation job and drift check; Python gate only validates the asset schema. Record the cross-repo order in the release checklist.

**IF-31 - High - 08 section 2, `models/template.py` - fail-open on unknown `server:` keys.**
*Problem.* `SandboxTemplate` uses `extra="ignore"`: a typo (`prset:`, `paths: ...` at the wrong level) in `template.yaml server:` is dropped silently and the sandbox boots the **legacy default** server (shell, files, `/env` set exposed) - the opposite of what the author asked for. The plan's `models/_server_config.py` is a validator, but nothing says the template loader must call it strictly, and the Node CLI parses `template.yaml` too.
*Fix.* `server:` is validated with `extra="forbid"` (suggestion on near-miss keys), failing `template build/deploy`; the generated `server.json` carries a schema version; the server refuses unknown keys at start with `config.invalid` (the in-flight policy loader already does this, keep it). Add the same strictness to the Node CLI.

### 2.6 Over-engineering

**IF-29 - Medium - 04 section 11, 05 section 3 - 90 per-adapter ops multiply the catalog.**
*Problem.* 18 ops x 5 adapters (152 total) produce 90 near-identical catalog rows, client methods, TS types, docs tables, golden entries and contract cases, for a distinction (the adapter) that is a *parameter* in every other surface (`model: <adapter>[/<model>]`).
*Fix.* Keep one family `agents.run|cancel|install|sessions.*|turns.*|...` with an `adapter` argument and put the adapter restriction in the scope (`AgentScope(adapters=[...])`/`Narrow`). If per-adapter selectors are wanted, generate them as *selector sugar* (`agents.codex.**` = `agents.**` with `adapter=codex`), not as 90 catalog operations.

**IF-30 - Medium - README, 10 - first-release scope is larger than the stated requirements.**
See section 6 for the cut list.

## 3. Work-package review (ordering, ownership, gates)

| WP | Verdict | Required change |
|----|---------|-----------------|
| (new) WP-A baseline and port | **missing** | IF-08, IF-09: first, blocks all |
| WP-0 core model | ok after rename | `ops/` -> `builtin/` (IF-03); do not own `__init__.py`/`pyproject.toml` exclusively (IF-12) |
| WP-1 dispatch/HTTP | risky | gate = v1 fixtures + 308 tests (IF-02, IF-04); strangler, not rewrite (IF-01); depends-on edges to WP-6/9/13 (IF-14) |
| WP-2 policy | ok | start from `policy.py`/`runtime.py` (IF-08); preset names reconciled (table R4) |
| WP-3 guards | ok | owns `guards/urls.py` (IF-12); port `guard.py`; replay spikes attack1-3 |
| WP-4a-d ops | ok | "new" ops (files.watch, process.stdin/output, terminal.get/resize) already exist as in-flight routes: port, do not rewrite |
| WP-5 compat | wrong shape | becomes a standing gate, not a late WP (IF-01, IF-02, IF-06) |
| WP-6 agents runtime | ok | starts from the 1.4k-line `agents/runtime.py`; `provider:` -> `llm:` rename is a migration, not green-field |
| WP-7a-e adapters | ok | 3 of 5 exist in the tree; `qoder` stays experimental (README R6) |
| WP-8 lazy install | needs design fixes | IF-20..24 |
| WP-9 CLI | ok | in-flight CLI has 4 subcommands; 12 is a goal, ship `serve/healthcheck/check-config/describe/prepare/doctor` first (section 6) |
| WP-10 codegen + mirror | too big | split into 10 (codegen), 10b (template/build), 10c (client), 10d (Node CLI) (IF-13, IF-28) |
| WP-11 test infra | ok | fakes ownership vs WP-7 (IF-12) |
| WP-12 docs | ok | list incl. zh parity, CHANGELOG fragments (IF-15, IF-16) |
| WP-13 security gate | incomplete deps | add WP-1, WP-5, WP-10 (IF-14) |

Order that works (strangler): baseline (A) -> WP-3 + WP-0 (parallel) -> WP-2 on top of the ported engine -> WP-1 changes behind the 308-test gate -> ops WPs (port) -> WP-8 -> agents (6/7) -> client mirror (grows from M1) -> docs/security gate. Parallel streams that really are independent today: WP-3, WP-8, the client mirror for the 48 known endpoints, docs.

## 4. Reconciliation table (old clause -> v2 clause -> action)

Actions: **keep** (old stays as is), **rename** (same idea, new name; old kept as alias where noted), **delete**, **merge** (combine into the v2 construct). "Old" = in-flight design docs and the working-tree code.

| # | Old clause (source) | v2 clause | Action | Notes |
|---|---------------------|-----------|--------|-------|
| 1 | Flat endpoint IDs `files_list`, `shell`, `pty_detail` ... (`fine-grained-capabilities.md` 3.1, `policy.py` `ENDPOINT_CATALOG`, `server_capabilities.ENDPOINT_GROUPS`) | 02 section 2 dotted IDs; 10 section 9a.1 mapping | rename | Mapping in 9a.1 is correct for all 48 names; add `capabilities_check`->`core.check`, `pty_connect`->`terminal.connect`, `list_commands`->`custom.list`. Keep aliases (policy files, client `ENDPOINT_GROUPS`) |
| 2 | Scope strings `files:read`, `process:run`, `terminal:use`, `devtools:run`, `browser:evaluate` (`policy.py` `scope_granted`, token `scopes`) | 03 effects + ID selectors | merge | Scopes become sugar compiled to effect/selector rules; token `scopes` map to `role:`; delete `Identity.scopes` as a primitive (keep as claim) |
| 3 | `endpoints{}` rule schema `enabled/scopes/paths/limits/params/audit` (`policy.py` `_RULE_KEYS`) | 03 rules (allow/deny + `PathScope`/`Limits`) | merge | The loader accepts both and normalises to rules; rejects unknown keys (keep, IF-31) |
| 4 | Presets `default`, `transfer-only`, `read-only`, `hardened`, `locked` (`policy.py` `PRESETS`) | 03 presets `minimal`, `readonly`, `download_only`, `workspace_jail`, `ci_runner`, `agent_host`, `full_access`, `legacy` | rename (not 1:1) | `default`->`legacy`; `read-only`->`readonly`; `locked`->`minimal`+`custom.*`; `hardened`->`workspace_jail`+deny list. **`transfer-only` (upload+download+stream twins) has no v2 equivalent: `download_only` is download only** -> add `transfer_only` preset |
| 5 | Groups `CapabilityGroup` on/off (`router.py`, `runtime.apply_groups`) | 04 section 12 group golden lists | keep | Group = selector; golden file already planned; note groups default-disabled `dev_tools`/`browser` |
| 6 | `POST /capabilities/check` body `{endpoint, path}` (`routes_system.py`, client `PathDecision`) | `core.check {op, args}` | rename | Accept both bodies; response keeps `allowed/code/reason`; 04's "legacy binding" label is wrong (route is new, not v1) |
| 7 | `/capabilities` body `api_version, endpoints, identity, policy, groups, warnings` | 02 section 7 `api, ops, revision, principal` | merge | IF-26: serve a union for two minors; client detection order ops -> endpoints -> groups |
| 8 | `404 endpoint_disabled` | `404 op.not_enabled` (principal-filtered) | rename | Legacy renderer keeps old string only on v1 bindings |
| 9 | Error `code` strings `path_not_allowed`, `missing_scope`, `file_exists` | 03 section 11 `policy.path_not_allowed` ... | rename | Client mapping accepts both for two minors; `file_exists` (409) needs a v2 code (`policy.overwrite_denied`) - missing in 03 |
| 10 | `PolicyDenied` exception, `PolicyConfigError` (`policy.py`) | `OpError`/server error family (`core/errors.py`) | merge | Keep `PolicyConfigError` as `config.invalid` |
| 11 | `PathGuard.resolve/check_resolved/open_checked` (`guard.py`) | 03 section 6 `resolve_path` + `open_beneath` | merge | Port into `guards/paths.py`; re-run spikes attack1-3 against it; v2 states open-then-verify with `O_TRUNC` is unsafe - audit `open_checked` for that |
| 12 | `PolicyEngine` over `RouteTable`: `EffectiveRule`, rate/concurrency buckets, audit, discovery (`runtime.py`) | 02 section 6 pipeline + 03 engine | merge | This is the strangler stage 1 (IF-01); extract `limits.py`/`audit.py` later |
| 13 | `__main__.py` subcommands `serve healthcheck check-config version` | 06 section 9 twelve subcommands | keep + extend | Ship the 4 + `describe`, `prepare`, `doctor` first; others later (section 6) |
| 14 | `contract.py` constants (ports, `POLICY_FILE`, `START_COMMAND`, `READY_COMMAND`) | 10 section 9a.9 `/etc/easy-sandbox/server.json` | rename | `server-policy.json` auto-read as `{"policy": ...}`; keep constants as single source |
| 15 | `server-policy.json`, `EBX_SERVER_POLICY[_FILE]` | `server.json`, `EBX_SERVER_CONFIG`, `_PRESET`, ... | rename | Keep old names as read-only aliases |
| 16 | Request pipeline: route match -> auth -> group gate (`app._dispatch`, capability doc section 5) | 02 section 6 (auth before 404, principal-filtered mounted check, policy before existence) | merge | HEAD matches route first (404 for unknown path before auth); the v2 order changes status for unauthenticated unknown paths - covered by the legacy renderer, **needs a v1 fixture** (IF-04) |
| 17 | Path scoping by canonicalise-then-open | 03 section 6 | delete | Replace; keep legacy `BASE_DIR` as `PathScope(roots=BASE_DIRS)` on legacy preset |
| 18 | Command scoping by glob args (`allow_commands`/`deny_commands` params) | 03 section 7 typed tokens, allowlist-first | rename | Old params compile to `CommandScope` with a lint warning |
| 19 | `/commands` + `custom commands` named `server.commands.*` (`client-server-alignment.md`) | `custom.*`; `commands.run` is the shell op | rename | Client: `srv.custom.<name>`, `srv.commands.run`; keep `Sandbox.custom`/`list_commands` signatures (IF-05 name mangling) |
| 20 | Client exceptions E8000-E8005 (`fine-grained-capabilities.md` 7) | 07 section 4 E3100-E3111 | **merge into E9xxx** | Working tree uses E9000-E9005; v2's E3100-E3111 is a third scheme. Pick E9xxx (IF-10); update docs |
| 21 | `ServerAPIError(status_code, error_type, error_code, endpoint)` | 07 attributes `.code/.op/.status/...` | keep old names + add | `.code` would shadow the E-code (IF-10) |
| 22 | `EndpointNotAvailableError(ServerAPIError, CapabilityNotSupportedError)` | `OperationNotEnabledError` | rename | Keep old class as alias; 07's `CommandNotFoundError` dual inheritance stays |
| 23 | `FilePolicyDeniedError(PolicyDeniedError, PermissionDeniedError)` | `PolicyDeniedError` subclasses `PermissionDeniedError` | merge | v2 has one class; keep `FilePolicyDeniedError` as subclass for path denials |
| 24 | `PayloadTooLargeError` E9004, `RateLimitedError` E9005 | `LimitExceededError`, `RateLimitedError` | rename | Keep both names |
| 25 | `ServerCapabilities` (`can/limit/paths/require`, `check_path`) | 07 section 3 `discover()` returning caps, `check(op, **args)` | merge | Keep class; rename `check_path` -> `check`, keep alias; no hidden traffic rule stays |
| 26 | Pydantic result models `models/server.py` (48 endpoints) | 07 section 1 TypedDict "no pydantic" | keep | IF-11; generated client may emit these models |
| 27 | `ServerClient` (type-checked only, file missing) | 07 generated `ServerClient` | merge | Implementation does not exist yet; build once, generated |
| 28 | `base-image-and-server-sdk.md` Dockerfile contract (`COPY *.whl`, `PIP_BREAK_SYSTEM_PACKAGES`, `start_cmd`/`ready_cmd`) | 06 section 9 `RUN pip install easy-sandbox-server` | keep (old) | The old snippet is the one that works on the PEP 668 image (IF-22) |
| 29 | `check-config` command text (base image doc) | 06 section 9 subcommand table | merge | Keep the name `check-config`; replace the prose with the 06 table; confirm 06 lists the same name |
| 30 | `--commands` flag | `--load` | rename | `--commands` stays an alias |
| 31 | Agents: routes `/agents/...`, group `agents` coarse | 05 section 3 `agents.<adapter>.*`, alias resolver | merge | Coarse group becomes `agents.**` (golden list) |
| 32 | Agents `provider:` model endpoint, `ProviderSpec` (`agents/config.py`) | `llm:` | rename | `provider` means the sandbox backend elsewhere (providers doc E8xxx) |
| 33 | Agents `install_steps`, `npm i -g`, `curl | bash`, `POST /agents/runtimes/{name}/install`, `EBX_AGENTS_ALLOW_INSTALL` | 06 manifests + `agents.<a>.install` explicit-only | delete | `ProviderSpec`/runtime code paths that install must go |
| 34 | `EBX_AGENTS_*` variables, state dir, dedicated port 9100 instance (`agents-api.md`) | one server on 9000; `EBX_AGENTS_STATE_DIR` | merge | Drop the 9100 dedicated-instance recipe (or document as optional deployment) |
| 35 | Agents auth exception (separate token) | universal Bearer/`X-Access-Token` | delete | IF-17 precedence rule needed |
| 36 | Adapter names `claude-code`, `qwen-code` | `claude_code`, `qwen_code`; hyphenated only as wire alias | rename | Existing tree uses hyphen or underscore inconsistently; normalise |
| 37 | Adapters in tree: codex, claude_code, qwen_code, cursor, command (`agents/adapters`) | 05 section 6 five adapters + `command` + `qoder` | keep + add | `qoder` experimental (R6) |
| 38 | `agents-api.md` "47-op" tiering vs `/v1/responses` | 05 section 3 | merge | v2 table omits `/v1/responses` ops that `agents-api.md` lists; reconcile in 05 |
| 39 | Agent sessions config `agents:` vs `agent:` keys (`agents-api.md`, 05 section 11) | one key | rename | v2 itself is inconsistent; choose `agents:` for server config, `agent:` for the per-template profile, document both |
| 40 | `repository-layout.md` layout | 10 section 9d layout | merge | Cross-package tests at repo root (`tests/contract`) are new; add to layout doc |
| 41 | Template mechanism A `custom_commands:` (envd side) | 08 `server:` mechanism B | keep both | 08 says unchanged; add a template validator error when the same name exists in both |
| 42 | `provider` backends E8000-E8030 (`providers-and-credentials.md`) | 07 section 4 note | keep | No server symbol may use the word |
| 43 | `declarative.sandbox.register.*` -> `enable_builtin` | `Policy` + `ops/declarative.py` | merge | Needs an owner (IF-13); keep decorator API |
| 44 | Alignment doc `server.process.shell`, `server.pty` names | `commands.run`, `terminal.*` | rename | Superseded banner (9a.10) |
| 45 | Capability doc section 11 resolutions (review history) | - | keep | History only; add the banner |
| 46 | PTY on port 9001 started by `start_pty_server` | `terminal.connect` stream `ws` | keep | Lazy listener stays; ensure policy decision happens on the HTTP upgrade path and on 9001 (policy on 9001 is easy to miss) |
| 47 | `/etc/easy-sandbox/server-policy.json` root-owned | `/etc/easy-sandbox/server.json` | rename | Same permissions note: user `user` cannot write it, good; document |
| 48 | Version `0.3.0` lockstep (`_version.py`, `test_version_lockstep`) | server/client `2.0.0` | merge | IF-06: do not jump without an ADR |

## 5. Client/server alignment table

Legend. **Client today** = what exists in the client SDK now (envd plane `sandbox.<module>` unless noted; "srv" = the server plane, which has no `ServerClient` yet, only discovery/result models in the working tree). **Gap**: `none` = client counterpart exists; `planned` = in 07 as generated `srv.*`; **`NO CLIENT`** = no counterpart anywhere and not in the asymmetry table; `asym` = deliberate asymmetry (envd-only or server-only).

### 5.1 Core, files, commands, process, terminal, system, devtools, browser, custom/ext

| v2 op | Legacy/in-flight HTTP binding | Usage (method) | Client today (envd / srv) | Gap |
|-------|------------------------------|----------------|---------------------------|-----|
| `core.health` | `GET /health` (v1) | readiness, version | none public (`mcp_http` has its own `/health`); srv planned | planned |
| `core.capabilities` | `GET /capabilities` (v1) | discovery | `ServerCapabilities` (working tree) | none (body mismatch IF-26) |
| `core.describe` | `GET /ops` (new) | list ops | none; planned `srv.describe()` | planned |
| `core.check` | `POST /capabilities/check` (in-flight) | dry-run policy | `ServerCapabilities.check_path` | none (rename `check`) |
| `core.openapi` | `GET /openapi.json` (new) | schema | none | **NO CLIENT** (docs-only asset; add to asymmetry list) |
| `core.reload` | `POST /admin/reload` (new) | admin | none | **NO CLIENT** (intentional, admin; list as asym) |
| `files.list` | `GET /files/list` | list dir | `files.list` (envd) | none |
| `files.stat` | `GET /files/stat` | metadata | `files.get_info`, `exists` | none |
| `files.mkdir` | `POST /files/mkdir` | mkdir | `files.make_dir` | none |
| `files.delete` | `DELETE /files` | remove | `files.remove` | none |
| `files.move` | `POST /files/move` | rename/move | `files.rename`, `files.move` | none |
| `files.search` | `POST /files/search` | find | none | **NO CLIENT** (server-only convenience; add asym or envd twin) |
| `files.upload` | `POST /upload` (v1) | base64 upload | `files.write`, `files.upload` | none |
| `files.upload_stream` | `POST /files/upload-stream` | chunked upload | none (envd `upload_url`) | **NO CLIENT** on server plane |
| `files.download` | `GET /download` (v1) | base64 download | `files.read/read_bytes/download` | none |
| `files.download_stream` | `GET /files/download-stream` | chunked download | none | **NO CLIENT** on server plane |
| `files.archive` | `POST /files/archive` | tar/zip | none | **NO CLIENT** |
| `files.watch` | `GET /files/watch` (SSE, in-flight) | change events | `files.watch` (envd) | none (srv planned) |
| `commands.run` | `POST /shell` (v1) | one-shot | `commands.run` | none |
| `commands.stream` | `POST /shell/stream` | SSE | `commands.stream` | none |
| `process.start` | `POST /process/start` | background | `commands.start` | none |
| `process.list` | `GET /process/list` | list | `commands.list` | none |
| `process.get` | `GET /process/{pid}` | status | none (envd `connect`-style via handle) | **NO CLIENT** (server-only; asym) |
| `process.signal` | `POST /process/{pid}/signal` | signal | `commands.kill/send_signal` | none |
| `process.stdin` | `POST /process/{pid}/stdin` (in-flight) | stdin | `commands.send_stdin/send_input` | none |
| `process.output` | `GET /process/{pid}/output` (in-flight) | long-poll | none | **NO CLIENT** (asym) |
| `terminal.create` | `POST /pty/sessions` | PTY | `get_terminal` (envd) | none |
| `terminal.list` | `GET /pty/sessions` | list | none | **NO CLIENT** |
| `terminal.get` | `GET /pty/sessions/{id}` (in-flight) | info | none | **NO CLIENT** |
| `terminal.resize` | `POST /pty/sessions/{id}/resize` (in-flight) | resize | terminal handle `resize` (envd) | none |
| `terminal.delete` | `DELETE /pty/sessions/{id}` | close | terminal handle | none |
| `terminal.connect` | WebSocket on the PTY port | stream | terminal handle (envd WS) | none (policy on 9001: see row 46) |
| `system.info` | `GET /system/info` | OS/CPU | none | **NO CLIENT** (envd `metrics` is platform plane; asym) |
| `system.metrics` | `GET /system/metrics` | metrics | `sandbox.metrics` (platform) | asym |
| `system.env.get` | `GET /env` | read env | none | **NO CLIENT** |
| `system.env.set` | `POST /env` | set env | none (envd takes env per command) | **NO CLIENT** |
| `system.ports` | `GET /ports` | listening ports | none | **NO CLIENT** |
| `system.packages` | `GET /packages` | pip/apt list | none | **NO CLIENT** |
| `devtools.code.run` | `POST /code/run` | run snippet | `code.run` (port 49999 engine) | asym (different engine) |
| `devtools.git.status` | `GET /git/status` | git | none | **NO CLIENT** |
| `devtools.git.diff` | `GET /git/diff` | git | none | **NO CLIENT** |
| `browser.navigate` / `screenshot` / `content` / `click` / `type` / `evaluate` / `pdf` / `console` (8) | `POST|GET /browser/*` | Playwright | none | **NO CLIENT** (8 ops; only a generic `srv.call`) |
| `custom.list` | `GET /commands` (v1) | list named commands | `Sandbox.list_commands()` | none |
| `custom.<name>` | `POST /commands/{name}` (v1) | run named command | `Sandbox.custom(name, **kw)`, declarative `register` | none (name mangling IF-05) |
| `ext.<handler>` | arbitrary `RouteTable.route` | extension | none (only generic `srv.call`) | **NO CLIENT** (dynamic; covered by `call`) |

### 5.2 Agents

| v2 op(s) | HTTP | Client today | Gap |
|----------|------|--------------|-----|
| `agents.list`, `agents.doctor`, `agents.models.list` | native routes | none (the `Agent/Runner/AgentHost` surface exists only in `agents-api.md`) | planned (design only; IF-13) |
| `agents.definitions.{create,get,update,list,delete}` | `/agents/definitions`, `/v1/agents` | none | planned |
| `agents.environments.{create,get,list}`, `agents.sessions.list` | `/v1/environments`, `/v1/sessions` | none | planned |
| `agents.<a>.run`, `.cancel` | `/v1/responses` family (see 05; ops for `/v1/responses` missing in the table) | none | planned; table gap in 05 |
| `agents.<a>.install` (explicit-only) | `POST` | none | planned (bootstrap uses `prepare`) |
| `agents.<a>.sessions.{create,get,update,delete,send,events,items}` (7) | `/v1/sessions...` incl. SSE | none | planned; `srv.agents.openai_client()` for the official SDK |
| `agents.<a>.turns.{list,get}`, `.turn_items.list`, `.artifacts.{list,get,content,delete}`, `.traces.list` (8) | `/v1/...` | none | planned |
| (x5 adapters = 90 ops) | | | see IF-29: model as a parameter |

### 5.3 Legacy route -> op (all 41 v1 routes; none lacks an op)

| Route(s) | Op |
|----------|----|
| `GET /health` | `core.health` |
| `GET /capabilities` | `core.capabilities` |
| `GET /commands`, `POST /commands/{name}` | `custom.list`, `custom.<name>` |
| `POST /upload`, `GET /download` | `files.upload`, `files.download` |
| `POST /shell`, `POST /shell/stream` | `commands.run`, `commands.stream` |
| `GET /files/list`, `GET /files/stat`, `POST /files/mkdir`, `DELETE /files`, `POST /files/move`, `POST /files/search`, `POST /files/upload-stream`, `GET /files/download-stream`, `POST /files/archive` | `files.list/stat/mkdir/delete/move/search/upload_stream/download_stream/archive` |
| `POST /process/start`, `GET /process/list`, `GET /process/{pid}`, `POST /process/{pid}/signal` | `process.start/list/get/signal` |
| `POST /pty/sessions`, `GET /pty/sessions`, `DELETE /pty/sessions/{id}` | `terminal.create/list/delete` |
| `GET /system/info`, `GET /system/metrics`, `GET /env`, `POST /env`, `GET /ports`, `GET /packages` | `system.info/metrics/env.get/env.set/ports/packages` |
| `POST /code/run`, `GET /git/status`, `GET /git/diff` | `devtools.code.run`, `devtools.git.status`, `devtools.git.diff` |
| `POST /browser/{navigate,screenshot,click,type,evaluate,pdf}`, `GET /browser/{content,console}` | `browser.*` (8) |

Total: 41 routes -> 41 op bindings (the `custom.<name>` row is one route for N ops). The 7 non-v1 endpoints in the working tree (`files.watch`, `process.stdin`, `process.output`, `terminal.get`, `terminal.resize`, `terminal.connect`, `core.check`) are the "new" ops of 04 and **already exist as routes**.

### 5.4 Client-only features (no server op, by design)

Sandbox lifecycle (create/connect/kill/list/pause/resume/timeout), `network`, `metrics`, `templates`/`deploy`/`docker_builder`/ACR, `session` manager, `files.upload_url/download_url` (signed envd URLs), code-interpreter contexts (`create/list/restart/remove_context`), `Sandbox.custom` mechanism A (envd-side commands), `agent/` MCP server (`mcp.py`, `mcp_http.py`), `agent/infer.py` and the Qwen codegen, provider (EPP) layer, `compat/` (E2B shape), `utils` async bridge. None needs a server op; each should appear in the 07 section 6 table under "platform plane only" so the ledger of IF-27 can distinguish "deliberately client-only" from "forgotten".

### 5.5 Gap summary

- Server ops with **no client counterpart at all and no asymmetry entry**: `core.describe`, `core.openapi`, `core.reload`, `files.search`, `files.upload_stream`, `files.download_stream`, `files.archive`, `process.get`, `process.output`, `terminal.list`, `terminal.get`, `system.info`, `system.env.get`, `system.env.set`, `system.ports`, `system.packages`, `devtools.git.status`, `devtools.git.diff`, `browser.*` (8), `ext.*`, and all `agents.*` (design only). That is 18 named built-in ops plus `browser.*` and agents.
- Either add an entry per op to the parity ledger (IF-27) or generate the `srv.*` methods (07 does promise this): until `ServerClient` exists, **only** `Sandbox.custom`/`list_commands` and the discovery helpers talk to the server plane.
- Mismatches to fix first: discovery body (IF-26), error family (IF-10), `check_path` vs `check`, the E-code vs `.code` attribute (IF-10).

## 6. Over-engineering check: what to cut or defer for a first release

The stated requirements (fine-grained per-op/path/command permissions, download-only style policies, lazy install of agent CLIs, OpenAI-compatible agent hosting, client and CLI alignment, unchanged legacy behaviour) are met by a smaller set.

| Item | Cut/defer | Why it is safe |
|------|-----------|----------------|
| Per-adapter op families (90 ops) | collapse to one family with an `adapter` argument (IF-29) | Same policy power through `AgentScope`/`Narrow`; catalog 152 -> ~62 |
| Five adapters | ship codex + claude_code + one declarative `command` adapter; qwen_code/cursor/qoder follow | Requirement is "hosting coding agents", not five; qoder is unverified (R6); 3 adapters already exist in the tree |
| Python/TS/OpenAPI codegen of all three | generate Python + `operations.json` first; TS and OpenAPI as release assets later | Node CLI can use the dynamic `GET /ops` fallback (07 section 2) until its generator lands |
| 12 CLI subcommands | `serve healthcheck check-config describe prepare doctor`; add `init explain lock sbom gen-client` later | In-flight CLI has 4; the rest are tooling |
| 5 config layers + hot reload (`core.reload`, `EBX_SERVER_POLICY_RELOAD`) | file + env + template block; no reload in 1st release | Sandboxes are short-lived; restart is cheaper than a reload security surface |
| Hooks (`policy` callables), `Narrow`, per-principal roles beyond one admin token | keep static rules + token roles; hooks later | Hooks are the biggest bypass surface; requirements do not need them |
| Compat rollback (`EBX_SERVER_LEGACY_DISPATCH`), `compat/` package, 2-minor alias window | drop (IF-06) | Pre-release ADR; keep v1 bindings as plain ops |
| `files.watch`/`process.stdin|output`/`terminal.get|resize` | already implemented; keep, do not re-spec | No new work |
| Five install manifest types | `tarball` + `npm-lock` + `system` (check-only) first; `pip-hashes`, `playwright-browser` later | Agent CLIs are npm/tarball; browser is default-off |
| `UrlScope` DNS-resolution logic | schemes + literal-host allowlist first | DNS-rebinding is already documented as a platform limit |
| `.pyi` generation, `describe --markdown` docs tables, `sbom` | later | Nice-to-have; drift test on `operations.json` covers the risk |
| AI-consumer independent runs S1-S8 as a *release gate* | keep as periodic, not blocking | Valuable but nondeterministic; keep bypass matrix as the blocking gate |

## 7. What held up

- **Catalog completeness vs v1**: every one of the 41 legacy routes has exactly one op binding; the 9a.1 name mapping covers all 48 in-flight endpoint names (the three extra aliases noted in table row 1 are the only additions needed).
- **Stdlib-only runtime**: the design keeps `core/policy/guards/install/agents` stdlib-only and `websockets` lazily imported; the in-flight code obeys this; `pyproject.toml` already depends on `websockets` only.
- **Lockstep versioning and shared namespace package** are respected by the layout (server wheel has no `easy_sandbox/__init__.py`).
- **Authenticate-before-404 and principal-filtered `mounted?`** are sound and testable (the spikes demonstrate them); they are the right pipeline invariants.
- **Dotted IDs, effects and default-deny with explicit-only ops** give the requested "download only from these directories" policy with a small surface (the example policy in 03 section 1 is implementable with the prototype).
- **Never installing at `serve` start** (06 section 10) and `prepare` at build time are the correct response to FC cold start and to read-only roots; only the lock ordering (IF-20) and defaults (IF-21) need fixing.
- **Contract/drift tests generated from the catalog** are the right way to keep Python, TS and docs aligned; the plan's per-op case-coverage test is worth keeping.
- **Single `guards/` module with a bypass matrix** and replayed spike attacks is the correct response to three divergent path-handling implementations.
- The spike suite and catalog test run green and are cheap to keep in CI as prototype parity tests until the package replaces them.
